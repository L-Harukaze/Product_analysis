/**
 * Mock 内存状态库：14 端点行为语义的状态机实现。
 * - 执行推进：按时间计算 phase（方法间并发模型），轮询可见 R1→R2 递增
 * - 409 闭环：缺数清空 → ready + 生成数据冲突 → execute 被拒 → 裁决落库 → 放行
 * - 打回：按 payload 内容判定（market_share 字符串 → 行/字段级错误）
 * - 失败停顿（Owner 微调 2026-09-16）：方法 failed 且未处置（重试/跳过）时，
 *   不推进 assembling——留给用户看清楚哪里错了再决定
 * - 重试：注入上轮错误经验重跑（去失败标记、重置该方法时钟）→ 成功
 * - 恢复：reroute / execute 重放 / reassemble
 */

import type {
  DataError,
  DiagnosisDetail,
  DiagnosisSummary,
  DxStatus,
  L2Conflict,
  MissingItem,
  ProgressMethod,
  ReportResponse,
  SubmissionRecord,
} from '../api/types';
import {
  ASSEMBLING_MS,
  buildPrompt,
  k80Activation,
  k80ArchiveRows,
  k80Conflict,
  k80ExecPlan,
  k80Fingerprint,
  k80Missing,
  k80Report,
  type ExecMethodPlan,
} from './fixtures';

export interface MockDx {
  id: string;
  product: string;
  category: string;
  status: DxStatus;
  createdAt: number;
  updatedAt: number;
  /** 产品背景信息（Owner 微调：路由补充输入 + 采集 prompt 注入） */
  background?: string;
  fingerprint?: typeof k80Fingerprint;
  activation?: typeof k80Activation;
  missing?: MissingItem[];
  archive?: { table: string; name: string; rows: number }[];
  /** 档案库行数据（表 ID → 行数组；冲突行标红定位用） */
  archiveRows?: Record<string, Record<string, unknown>[]>;
  conflicts: L2Conflict[];
  conflictVerdicts: Record<string, string>;
  qcOwnerVerdicts: Record<string, '维持' | '修正'>;
  submissions: SubmissionRecord[];
  rejectionNote?: string;
  exec?: {
    startedAt: number;
    plan: ExecMethodPlan[];
    /** 重试时钟偏移：method → 偏移量（该方法从"现在"重新起跑） */
    retried?: Record<string, number>;
    /** 失败处置标记：method → retried | skipped */
    handled?: Record<string, 'retried' | 'skipped'>;
  };
  report?: ReportResponse;
  claimEval?: import('../api/types').ClaimEvaluation[];
  pendingClaims?: import('../api/types').PendingClaimVerdict[];
  claimVerdicts: { cid: string; verdict: string; at: string }[];
  created: boolean; // 由用户现场创建（区别于种子）
}

const store = new Map<string, MockDx>();
let seq = 0;

function seed(id: string, product: string, category: string, status: DxStatus): MockDx {
  const now = Date.now();
  const dx: MockDx = {
    id,
    product,
    category,
    status,
    createdAt: now,
    updatedAt: now,
    conflicts: [],
    conflictVerdicts: {},
    qcOwnerVerdicts: {},
    submissions: [],
    claimVerdicts: [],
    created: false,
  };
  store.set(id, dx);
  return dx;
}

/** 初始档案 = 数据清单中已采集的表 */
function initialArchive(missing: MissingItem[]): { table: string; name: string; rows: number }[] {
  return missing
    .filter((m) => m.status === 'archived')
    .map((m) => ({ table: m.table, name: m.name, rows: m.rows ?? 0 }));
}

/** 种子：SU7 done / 三只松鼠 ready / iPhone17 failed_at(routing) */
export function initSeeds(): void {
  if (store.size > 0) return;
  const su7 = seed('dx-su7', '小米 SU7', '汽车', 'done');
  su7.report = k80Report; // 同构复用（演示数据）
  const song = seed('dx-song', '三只松鼠', '零食', 'ready');
  song.missing = k80Missing.map((m) => ({ ...m, status: 'archived' as const, rows: m.rows ?? 6 }));
  song.archive = initialArchive(song.missing);
  const ip17 = seed('dx-ip17', 'iPhone 17', '手机', 'failed_at(routing)');
  void ip17;
}

initSeeds();

/* ———— stage_hint（后端组装，前端不推算——mock 模拟后端职责）———— */
export function stageHint(dx: MockDx): string {
  const s = dx.status;
  if (s === 'done') return '报告已生成';
  if (s === 'executing') {
    const p = computeProgress(dx);
    return p ? `分析进行中 · ${p.done_n}/${p.total_n} 个方法完成` : '执行中';
  }
  if (s === 'assembling') return '报告装配中';
  if (s === 'ready')
    return dx.conflicts.some((c) => !dx.conflictVerdicts[c.id])
      ? `${dx.conflicts.filter((c) => !dx.conflictVerdicts[c.id]).length} 处数据冲突待处理`
      : '档案齐备 · 待触发执行';
  if (s === 'routed') {
    const miss = dx.missing?.filter((m) => m.status === 'missing').length ?? 0;
    return miss > 0 ? `待采集 ${miss} 项数据` : '数据齐备';
  }
  if (s.startsWith('failed_at')) {
    if (s === 'failed_at(routing)') return '产品分析失败 · 可重试';
    if (s === 'failed_at(data)') return '数据环节异常（系统问题）';
    if (s === 'failed_at(executing)') return '执行中断（系统问题）';
    return '报告装配失败（可重新装配）';
  }
  return '创建中';
}

/* ———— 执行推进（时间驱动，轮询端点调用）———— */

/** 方法自身时钟：重试过的方法从重试时刻起跑 */
function methodClock(dx: MockDx, p: ExecMethodPlan, elapsed: number): number {
  const off = dx.exec?.retried?.[p.method] ?? 0;
  return elapsed - off - p.staggerMs;
}

/** 是否存在"已失败且未被用户处置"的方法（推进阻断条件） */
function hasUnhandledFailure(dx: MockDx): boolean {
  if (!dx.exec) return false;
  const elapsed = Date.now() - dx.exec.startedAt;
  return dx.exec.plan.some((p) => {
    if (p.failAfterRounds === undefined) return false;
    const rel = methodClock(dx, p, elapsed);
    if (rel < 0) return false;
    const roundsDone = Math.floor(rel / p.roundMs);
    return roundsDone >= p.failAfterRounds && !dx.exec!.handled?.[p.method];
  });
}

export function computeProgress(dx: MockDx): { methods: ProgressMethod[]; done_n: number; total_n: number } | null {
  if (!dx.exec) return null;
  const elapsed = Date.now() - dx.exec.startedAt;
  const methods: ProgressMethod[] = dx.exec.plan.map((p) => {
    const rel = methodClock(dx, p, elapsed);
    const handled = dx.exec?.handled?.[p.method];
    if (rel < 0) return { method: p.method, phase: 'pending' as const };
    const roundsDone = Math.floor(rel / p.roundMs);
    if (p.failAfterRounds !== undefined && roundsDone >= p.failAfterRounds) {
      return { method: p.method, phase: 'failed' as const, error: p.error, handled };
    }
    if (roundsDone >= p.rounds) return { method: p.method, phase: 'done' as const, handled };
    return { method: p.method, phase: `running(R${roundsDone + 1})` as `running(R${number})`, handled };
  });
  // QC 逐方法批量（方法终态后排队→执行，演示同构卡）
  const settled = methods.filter((m) => m.phase === 'done' || m.phase === 'failed').length;
  const qcPhase: ProgressMethod =
    settled === 0
      ? { method: 'QC（deepseek）', phase: 'pending' }
      : settled < methods.length
        ? { method: 'QC（deepseek）', phase: `running(${settled}/${methods.length})` }
        : { method: 'QC（deepseek）', phase: 'done' };
  return { methods: [...methods, qcPhase], done_n: settled, total_n: methods.length };
}

/** 终态推进：executing → assembling → done（在每次读详情时检查）。
 *  Owner 微调：存在未处置的失败方法时不推进——人肉断点，用户处置（重试/跳过）后才继续 */
export function tick(dx: MockDx): void {
  if (dx.status === 'executing' && dx.exec) {
    if (hasUnhandledFailure(dx)) return;
    const elapsed = Date.now() - dx.exec.startedAt;
    const totalMs = Math.max(...dx.exec.plan.map((p) => (dx.exec!.retried?.[p.method] ?? 0) + p.staggerMs + p.rounds * p.roundMs));
    if (elapsed > totalMs + 1000) {
      dx.status = 'assembling';
      dx.updatedAt = Date.now();
    }
  }
  if (dx.status === 'assembling' && dx.exec) {
    const elapsed = Date.now() - dx.exec.startedAt;
    const totalMs = Math.max(...dx.exec.plan.map((p) => (dx.exec!.retried?.[p.method] ?? 0) + p.staggerMs + p.rounds * p.roundMs));
    if (elapsed > totalMs + 1000 + ASSEMBLING_MS) {
      dx.status = 'done';
      dx.report = dx.report ?? k80Report;
      dx.updatedAt = Date.now();
    }
  }
}

/* ———— 动作 ———— */

export function listAll(): MockDx[] {
  return [...store.values()].sort((a, b) => b.updatedAt - a.updatedAt);
}

export function createDiagnosis(product: string, category?: string, background?: string): MockDx {
  seq += 1;
  const id = `dx-${String(seq).padStart(2, '0')}`;
  const dx = seed(id, product.trim() || `新产品 ${seq}`, category?.trim() || '手机', 'routed');
  dx.created = true;
  dx.background = background?.trim() || undefined;
  dx.fingerprint = k80Fingerprint;
  dx.activation = k80Activation;
  dx.missing = k80Missing.map((m) => ({ ...m }));
  dx.archive = initialArchive(dx.missing);
  dx.archiveRows = JSON.parse(JSON.stringify(k80ArchiveRows)) as Record<string, Record<string, unknown>[]>;
  return dx;
}

export function promptFor(dx: MockDx): string {
  return buildPrompt(dx.product, dx.id, dx.rejectionNote, dx.background);
}

/** 打回判定：market_share 为字符串 / 缺 source_url → 行/字段级错误 */
export function judgePayload(dx: MockDx, payload: string): { accepted: true } | { accepted: false; errors: DataError[] } {
  let parsed: { tables?: Record<string, Record<string, unknown>[]> };
  try {
    parsed = JSON.parse(payload);
  } catch {
    return {
      accepted: false,
      errors: [{ table: '-', row_index: 0, field: 'payload', error: 'JSON 解析失败：请粘贴豆包返回的原文' }],
    };
  }
  const tableId = Object.keys(parsed.tables ?? {})[0];
  const rows = parsed.tables?.[tableId] ?? [];
  const errors: DataError[] = [];
  rows.forEach((row, i) => {
    if (typeof row.market_share === 'string') {
      errors.push({
        table: tableId,
        row_index: i + 1,
        field: 'market_share',
        error: `类型错误：期望数字，实际是 "${row.market_share}"（百分比请传数值，如 5.2）`,
      });
    }
    if (!row.source_url) {
      errors.push({ table: tableId, row_index: i + 1, field: 'source_url', error: '必填缺失（硬规则 1：无来源不入档）' });
    }
  });
  if (errors.length > 0) {
    dx.rejectionNote = `上次提交的拒绝原因（共 ${errors.length} 处错误）——请修正后重新提交：\n${errors
      .map((e) => `  · 第 ${e.row_index} 行 字段 ${e.field}：${e.error}`)
      .join('\n')}`;
    return { accepted: false, errors };
  }
  return { accepted: true };
}

/** 合格入档：入档当前缺失的第一项数据；清单清空 → ready + 生成数据冲突（演示 409 闭环） */
export function acceptSubmission(dx: MockDx, tableId: string, rows: number): void {
  const missingTable = dx.missing?.find((m) => m.status === 'missing');
  const t = missingTable ?? { table: tableId, name: '数据表', status: 'missing' as const };
  dx.archive = [...(dx.archive ?? []), { table: t.table, name: t.name, rows }];
  dx.missing = dx.missing?.map((m) => (m.table === t.table ? { ...m, status: 'archived' as const, rows } : m));
  dx.rejectionNote = undefined;
  if (dx.missing?.every((m) => m.status === 'archived')) {
    dx.status = 'ready';
    if (dx.conflicts.length === 0) dx.conflicts.push({ ...k80Conflict });
  }
  dx.updatedAt = Date.now();
}

export function startExec(dx: MockDx): void {
  dx.status = 'executing';
  dx.exec = { startedAt: Date.now(), plan: JSON.parse(JSON.stringify(k80ExecPlan)) as ExecMethodPlan[] };
  dx.updatedAt = Date.now();
}

/* ———— 方法失败处置（Owner 微调 2026-09-16）———— */

/** 重试：携带上轮错误经验重跑——去失败标记，该方法从"现在"重新起跑 */
export function retryMethod(dx: MockDx, method: string): void {
  if (!dx.exec) return;
  const p = dx.exec.plan.find((m) => m.method === method);
  if (!p) return;
  delete p.failAfterRounds;
  delete p.error;
  dx.exec.retried = dx.exec.retried ?? {};
  dx.exec.retried[method] = Date.now() - dx.exec.startedAt - p.staggerMs; // 从现在开始
  dx.exec.handled = dx.exec.handled ?? {};
  dx.exec.handled[method] = 'retried';
}

/** 跳过：放弃该方法（报告中显式登记为降级） */
export function skipMethod(dx: MockDx, method: string): void {
  if (!dx.exec) return;
  dx.exec.handled = dx.exec.handled ?? {};
  dx.exec.handled[method] = 'skipped';
}

export function toDetail(dx: MockDx): DiagnosisDetail {
  tick(dx);
  return {
    diagnosis_id: dx.id,
    product_name: dx.product,
    category: dx.category,
    status: dx.status,
    stage_hint: stageHint(dx),
    pending_conflicts_n: dx.conflicts.filter((c) => !dx.conflictVerdicts[c.id]).length,
    updated_at: new Date(dx.updatedAt).toISOString(),
    fingerprint: dx.fingerprint,
    activation_matrix: dx.activation,
    missing_data: dx.missing,
    archive_summary: dx.archive,
    archive_rows: dx.archiveRows,
    pending_conflicts: dx.conflicts.filter((c) => !dx.conflictVerdicts[c.id]),
    // blocking_errors：mock 不覆盖此字段（S28 契约增量）——error 档阻断卡片是真实后端能力，
    // mock 场景不造 error 档数据（字段缺省 → 卡片不渲染）；若需 mock 演示 error 档，在此补构造。
    submissions: dx.submissions,
    progress: dx.status === 'executing' || dx.status === 'assembling' ? computeProgress(dx) ?? undefined : undefined,
    error_detail: dx.status.startsWith('failed_at')
      ? {
          stage: dx.status.slice('failed_at('.length, -1) as 'routing',
          timeout: '—',
          retries: 1,
          split_record: '—',
          raw:
            dx.status === 'failed_at(routing)'
              ? 'ArbiterTimeout: AI 仲裁超过 15 秒上限，2 个维度按保守档位处理，可重试'
              : 'InfrastructureError: 后台任务中断（系统问题，详见服务端日志）',
        }
      : undefined,
  };
}

export function toSummary(dx: MockDx): DiagnosisSummary {
  tick(dx);
  return {
    diagnosis_id: dx.id,
    product_name: dx.product,
    category: dx.category,
    status: dx.status,
    stage_hint: stageHint(dx),
    pending_conflicts_n: dx.conflicts.filter((c) => !dx.conflictVerdicts[c.id]).length,
    updated_at: new Date(dx.updatedAt).toISOString(),
  };
}

export function get(id: string): MockDx | undefined {
  return store.get(id);
}

/** 删除诊断（Owner 契约增量：列表管理；调用方负责状态守卫） */
export function removeDiagnosis(id: string): void {
  store.delete(id);
}

export function addSubmission(dx: MockDx, accepted: boolean, table: string, rows: number, errors?: DataError[]): void {
  dx.submissions.unshift({ n: dx.submissions.length + 1, at: new Date().toISOString(), accepted, table, rows, errors });
  dx.updatedAt = Date.now();
}

/* ———— dev 状态切换（FRONTEND.md §7.4；面板已按 Owner 要求移除，函数保留供测试）———— */
export function forceStatus(id: string, status: DxStatus): void {
  const dx = store.get(id);
  if (!dx) return;
  dx.status = status;
  dx.updatedAt = Date.now();
  if (status === 'executing') {
    dx.exec = { startedAt: Date.now() - 3000, plan: JSON.parse(JSON.stringify(k80ExecPlan)) as ExecMethodPlan[] };
  }
  if (status === 'done') {
    dx.report = dx.report ?? k80Report;
    dx.missing = dx.missing?.map((m) => ({ ...m, status: 'archived' as const, rows: m.rows ?? 6 }));
  }
  if (status === 'routed' && !dx.fingerprint) {
    dx.fingerprint = k80Fingerprint;
    dx.activation = k80Activation;
    dx.missing = k80Missing.map((m) => ({ ...m }));
    dx.archive = initialArchive(dx.missing);
    dx.archiveRows = JSON.parse(JSON.stringify(k80ArchiveRows)) as Record<string, Record<string, unknown>[]>;
  }
  if (status === 'ready') {
    dx.missing = dx.missing?.map((m) => ({ ...m, status: 'archived' as const, rows: m.rows ?? 6 }));
    if (dx.conflicts.length === 0) dx.conflicts.push({ ...k80Conflict });
  }
}

export const ALL_STATUSES: DxStatus[] = [
  'routed',
  'ready',
  'executing',
  'assembling',
  'done',
  'failed_at(routing)',
  'failed_at(data)',
  'failed_at(executing)',
  'failed_at(assembling)',
];
