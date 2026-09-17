/**
 * Mock 路由分发（FRONTEND.md §7）：实现契约全部 14 端点。
 * 行为语义=状态机（stateStore）；延迟 250ms 模拟网络。
 * 409 = 状态守卫拒绝 / L2 conflict（11.3）——抛 ApiError 由调用方 catch。
 */

import { ApiError } from '../api/client';
import type {
  ClaimsResponse,
  CreateDiagnosisRequest,
  CreateDiagnosisResponse,
  DataResponse,
  DiagnosisDetail,
  DiagnosisSummary,
  EvaluationResponse,
  ReportResponse,
} from '../api/types';
import { SAMPLE_CLAIMS } from './fixtures';
import { acceptSubmission, addSubmission, createDiagnosis, forceStatus, get, judgePayload, listAll, promptFor, removeDiagnosis, retryMethod, skipMethod, startExec, toDetail, toSummary } from './stateStore';

const DELAY = 250;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** dev 面板直接调用（绕过 HTTP 语义） */
export const mockDev = { forceStatus, listAll };

export async function mockRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  await sleep(DELAY);
  const seg = path.split('/').filter(Boolean); // ['diagnoses', id?, ...]
  if (seg[0] !== 'diagnoses') throw new ApiError(404, { reason: 'not found' });
  const id = seg[1];
  const action = seg[2];

  /* GET /diagnoses 列表 */
  if (!id && method === 'GET') {
    return listAll().map(toSummary) as unknown as T;
  }

  /* POST /diagnoses 创建（事务 A 同步；background=Owner 微调新增的产品背景信息） */
  if (!id && method === 'POST') {
    const req = (body ?? {}) as CreateDiagnosisRequest;
    const dx = createDiagnosis(req.product_name ?? '', req.category_hint, req.background);
    const res: CreateDiagnosisResponse = {
      diagnosis_id: dx.id,
      status: dx.status,
      fingerprint: dx.fingerprint!,
      activation_matrix: dx.activation!,
      missing_data: dx.missing!,
      collection_prompt: promptFor(dx),
    };
    return res as unknown as T;
  }

  const dx = get(id!);
  if (!dx) throw new ApiError(404, { reason: 'diagnosis not found' });

  /* —— 单资源 —— */
  if (!action && method === 'GET') {
    return toDetail(dx) as unknown as T;
  }

  /* DELETE /diagnoses/:id —— Owner 契约增量：列表管理（执行/装配中不可删，防后台任务资源泄漏） */
  if (!action && method === 'DELETE') {
    if (dx.status === 'executing' || dx.status === 'assembling') {
      throw new ApiError(409, {
        reason: '执行中/装配中的诊断不可删除（后台任务运行中）',
        expected_states: ['created', 'routed', 'ready', 'done', 'failed_at(routing)', 'failed_at(data)', 'failed_at(executing)', 'failed_at(assembling)'],
        current: dx.status,
      });
    }
    removeDiagnosis(id!);
    return { accepted: true } as unknown as T;
  }

  /* GET collection-prompt（守卫 routed） */
  if (action === 'collection-prompt' && method === 'GET') {
    if (dx.status !== 'routed') throw new ApiError(409, { reason: '状态守卫拒绝', expected_states: ['routed'], current: dx.status });
    return { prompt: promptFor(dx) } as unknown as T;
  }

  /* POST data（事务 B：L1 校验循环；守卫 routed） */
  if (action === 'data' && method === 'POST') {
    if (dx.status !== 'routed') throw new ApiError(409, { reason: '状态守卫拒绝', expected_states: ['routed'], current: dx.status });
    const payload = String((body as { payload?: string })?.payload ?? '');
    const judged = judgePayload(dx, payload);
    let tableId = 'D';
    let rows = 0;
    try {
      const parsed = JSON.parse(payload) as { tables?: Record<string, unknown[]> };
      tableId = Object.keys(parsed.tables ?? {})[0] ?? 'D';
      rows = parsed.tables?.[tableId]?.length ?? 0;
    } catch { /* 解析失败走打回 */ }
    if (!judged.accepted) {
      addSubmission(dx, false, tableId, rows, judged.errors);
      return judged as unknown as T;
    }
    acceptSubmission(dx, tableId, rows || 6);
    addSubmission(dx, true, tableId, rows || 6);
    const res: DataResponse = {
      accepted: true,
      archive_summary: dx.archive!,
      missing_data: dx.missing!,
    };
    return res as unknown as T;
  }

  /* POST execute（事务 C；守卫 ready + L2 无未裁决 conflict） */
  if (action === 'execute' && method === 'POST') {
    const pending = dx.conflicts.filter((c) => !dx.conflictVerdicts[c.id]);
    if (dx.status === 'failed_at(executing)') {
      startExec(dx); // 3.4：基础设施失败重放=全重跑
      return { task_started: true } as unknown as T;
    }
    if (dx.status !== 'ready') {
      throw new ApiError(409, { reason: '状态守卫拒绝', expected_states: ['ready'], current: dx.status });
    }
    if (pending.length > 0) {
      throw new ApiError(409, { reason: 'L2 conflict 未裁决（触发被拒，11.3）', conflicts: pending });
    }
    startExec(dx);
    return { task_started: true } as unknown as T;
  }

  /* POST conflicts/:cid/verdict（裁决落库幂等；seg=[diagnoses,id,conflicts,cid,verdict]）
   * ⚠️ 2026-09-17 标注：真实行为已扩展——「手动更改」改数不再走这个端点，
   * 而是前端生成**整表修正稿**预填提交区，由 Owner 走 POST /data 提交（8.3 按表覆盖）；
   * 本端点现在只在"未修改数据、确认即维持"时被调用。此流程 mock 不覆盖，以真实行为为准。 */
  if (action === 'conflicts' && seg[4] === 'verdict' && method === 'POST') {
    dx.conflictVerdicts[seg[3]!] = String((body as { note?: string })?.note ?? '维持官方口径');
    dx.updatedAt = Date.now();
    return { accepted: true } as unknown as T;
  }

  /* POST reroute（failed_at(routing) 重放事务 A） */
  if (action === 'reroute' && method === 'POST') {
    if (dx.status !== 'failed_at(routing)') throw new ApiError(409, { reason: '状态守卫拒绝', expected_states: ['failed_at(routing)'], current: dx.status });
    dx.status = 'routed';
    dx.fingerprint = dx.fingerprint ?? (await import('./fixtures')).k80Fingerprint;
    dx.activation = dx.activation ?? (await import('./fixtures')).k80Activation;
    dx.missing = dx.missing ?? (await import('./fixtures')).k80Missing.map((m) => ({ ...m }));
    dx.archive = dx.archive ?? [{ table: 'A', name: '销量序列', rows: 12 }];
    dx.updatedAt = Date.now();
    return { accepted: true } as unknown as T;
  }

  /* POST reassemble（failed_at(assembling)/done 重放事务 D） */
  if (action === 'reassemble' && method === 'POST') {
    if (dx.status !== 'failed_at(assembling)' && dx.status !== 'done') {
      throw new ApiError(409, { reason: '状态守卫拒绝', expected_states: ['failed_at(assembling)', 'done'], current: dx.status });
    }
    dx.status = 'assembling';
    dx.exec = dx.exec ?? { startedAt: Date.now() - 99999, plan: (await import('./fixtures')).k80ExecPlan };
    dx.exec.startedAt = Date.now() - 99999; // 立即过执行期，2s 后 done
    dx.updatedAt = Date.now();
    return { accepted: true } as unknown as T;
  }

  /* GET report（守卫 done） */
  if (action === 'report' && method === 'GET') {
    if (dx.status !== 'done') throw new ApiError(409, { reason: '状态守卫拒绝', expected_states: ['done'], current: dx.status });
    return (dx.report ?? (await import('./fixtures')).k80Report) as unknown as T;
  }

  /* POST qc/:qid/verdict（11.4 落库幂等；seg=[diagnoses,id,qc,qid,verdict]） */
  if (action === 'qc' && seg[4] === 'verdict' && method === 'POST') {
    const v = (body as { verdict?: '维持' | '修正' })?.verdict ?? '维持';
    dx.qcOwnerVerdicts[seg[3]!] = v;
    dx.updatedAt = Date.now();
    return { accepted: true } as unknown as T;
  }

  /* POST claims（事务 E：三层对照） */
  if (action === 'claims' && !seg[3] && method === 'POST') {
    if (dx.status !== 'done') throw new ApiError(409, { reason: '状态守卫拒绝', expected_states: ['done'], current: dx.status });
    const claims = ((body as { claims?: unknown[] })?.claims ?? SAMPLE_CLAIMS) as { 论断: string }[];
    const c = claims.length > 0 ? claims : SAMPLE_CLAIMS;
    dx.claimEval = [
      { claim_id: 'CLM-01', 对照档: 'covered', detail: `「${c[0]?.论断 ?? '—'}」已被 D2 定价机制结论覆盖（阶梯升级率与性价比档位论证）` },
      { claim_id: 'CLM-02', 对照档: 'conflict', detail: '「K80 一年期保值率低于同档均值」与 M09 结论方向相反——外部为抽样报价，我方为序列口径' },
      { claim_id: 'CLM-03', 对照档: 'increment', detail: '「天玑屏减配」外部未见对应——我方 D6 信息结构诊断未覆盖该维度（增量发现）' },
    ];
    dx.pendingClaims = [
      {
        cid: 'CLM-02',
        mine: 'M09：K80 一年期保值率 78%，高于同档均值 2.1pp（序列口径，第三方）',
        theirs: '外部：保值率低于同档均值（二手报价抽样）',
        detail: '口径差异：序列均值 vs 抽样报价；裁决留痕（CONF-01 判例：共识可能是错的）',
      },
    ];
    dx.updatedAt = Date.now();
    const res: ClaimsResponse = { evaluation: dx.claimEval, pending_verdicts: dx.pendingClaims };
    return res as unknown as T;
  }

  /* POST claims/:cid/verdict（seg=[diagnoses,id,claims,cid,verdict]） */
  if (action === 'claims' && seg[4] === 'verdict' && method === 'POST') {
    const v = String((body as { verdict?: string })?.verdict ?? '我方正确');
    dx.claimVerdicts.push({ cid: seg[3]!, verdict: v, at: new Date().toISOString() });
    dx.pendingClaims = dx.pendingClaims?.filter((p) => p.cid !== seg[3]);
    dx.updatedAt = Date.now();
    return { accepted: true } as unknown as T;
  }

  /* POST progress/:method/retry —— Owner 微调新增（2026-09-16）：方法失败人肉断点，重试时注入上轮错误经验 */
  if (action === 'progress' && seg[4] === 'retry' && method === 'POST') {
    retryMethod(dx, seg[3]!);
    dx.updatedAt = Date.now();
    return { accepted: true } as unknown as T;
  }

  /* POST progress/:method/skip —— Owner 微调新增：跳过失败方法（报告中登记为降级） */
  if (action === 'progress' && seg[4] === 'skip' && method === 'POST') {
    skipMethod(dx, seg[3]!);
    dx.updatedAt = Date.now();
    return { accepted: true } as unknown as T;
  }

  /* GET evaluation */
  if (action === 'evaluation' && method === 'GET') {
    if (dx.status !== 'done') throw new ApiError(409, { reason: '状态守卫拒绝', expected_states: ['done'], current: dx.status });
    const res: EvaluationResponse = {
      evaluation: dx.claimEval ?? [],
      pending_verdicts: dx.pendingClaims ?? [],
      verdicts: dx.claimVerdicts,
    };
    return res as unknown as T;
  }

  throw new ApiError(404, { reason: `mock 未实现：${method} ${path}` });
}

/* 兼容引用（避免 tree-shake 误删类型导入） */
export type { DiagnosisDetail, DiagnosisSummary, ReportResponse };
