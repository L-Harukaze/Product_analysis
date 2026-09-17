/**
 * 契约类型（ARCHITECTURE.md 第 13 章，逐字对齐——联调验收基准）。
 * 前端不发明枚举（FRONTEND.md 铁律 5）；本文件类型即契约的 TS 投影。
 */

/* ———— 状态机（3.2）———— */
export type DxStage = 'routing' | 'data' | 'executing' | 'assembling';
export type DxBaseStatus = 'created' | 'routed' | 'ready' | 'executing' | 'assembling' | 'done';
export type DxStatus = DxBaseStatus | `failed_at(${DxStage})`;

export function isFailed(s: DxStatus): s is `failed_at(${DxStage})` {
  return s.startsWith('failed_at');
}
export function failedStage(s: DxStatus): DxStage | null {
  return isFailed(s) ? (s.slice('failed_at('.length, -1) as DxStage) : null;
}

/* ———— 13.1 端点的请求/响应 ———— */

/** POST /diagnoses 请求 */
export interface CreateDiagnosisRequest {
  product_name: string;
  category_hint?: string;
  known_facts?: { price?: number };
  /** 产品背景信息（Owner 微调 2026-09-16 新增）：用户粘贴的完整产品介绍，
   *  作为路由判断的补充输入注入事务 A prompt，并随采集 prompt 下发帮助取数 */
  background?: string;
}

/** 指纹维度（来源标注 = 三级漏斗 7.1 的 UI 化） */
export interface FingerprintItem {
  dimension: 'F1' | 'F2' | 'F3' | 'F4' | 'F5' | 'F6';
  label: string;
  value: string;
  source: 'L1 规则' | 'L2 定量·查表' | 'L3 仲裁';
  /** L3 仲裁留痕（演示亮点位） */
  detail?: { reason: string; precedents: string[]; confidence: number };
}

export interface ActivationEntry {
  domain: string; // D1..D7（含名称）
  method: string | null; // null = 不适用（显式登记）
  form: string;
  reason: string;
}

export interface MissingItem {
  table: string; // 表 ID（A-G）
  name: string;
  status: 'archived' | 'missing';
  rows?: number; // 已入档行数
}

/** POST /diagnoses 响应 201（事务 A 同步返回） */
export interface CreateDiagnosisResponse {
  diagnosis_id: string;
  status: DxStatus;
  fingerprint: FingerprintItem[];
  activation_matrix: ActivationEntry[];
  missing_data: MissingItem[];
  collection_prompt: string;
}

/** 列表条目（结构为 13.5 期望项，FRONTEND.md §9） */
export interface DiagnosisSummary {
  diagnosis_id: string;
  product_name: string;
  category: string;
  status: DxStatus;
  stage_hint: string; // 后端组装，前端不推算
  pending_conflicts_n: number;
  updated_at: string;
}

/** POST /data 响应（打回=11.2 结构） */
export interface DataError {
  table: string;
  row_index: number;
  field: string;
  error: string;
}
export interface DataAccepted {
  accepted: true;
  archive_summary: { table: string; name: string; rows: number }[];
  missing_data: MissingItem[];
}
export interface DataRejected {
  accepted: false;
  errors: DataError[];
}
export type DataResponse = DataAccepted | DataRejected;

/** L2 冲突（11.3） */
export interface L2Conflict {
  id: string;
  invariant: string; // 不变式类型
  detail: string;
  rows: string[]; // 涉及档案行
}

/** POST /execute 响应：202 或 409+冲突清单 */
export interface ExecuteConflictResponse {
  reason: string;
  conflicts: L2Conflict[];
}

/** 进度（10.2）——错误结构逐字契约 */
export interface MethodError {
  timeout: string; // 超时值
  retries: number; // 重试次数
  split_record: string; // 拆轮记录
  raw: string; // 原始报错
}
/** phase：契约 10.2 为 `pending|running(Rn)|done|failed`（Rn=方法轮次实例）；QC 同构卡的进行态标注为 running(k/n) */
export type MethodPhase = 'pending' | 'done' | 'failed' | `running(${string})`;
export interface ProgressMethod {
  method: string;
  phase: MethodPhase;
  error?: MethodError;
  /** 前端展示扩展（Owner 微调 2026-09-16，非契约枚举）：
   *  失败方法的用户处置标记——retried=已重试（注入上轮错误经验后重跑）、skipped=用户选择跳过 */
  handled?: 'retried' | 'skipped';
}
export interface Progress {
  methods: ProgressMethod[];
  done_n: number;
  total_n: number;
}

/** 提交历史（data_submissions 留痕呈现，联调对齐项） */
export interface SubmissionRecord {
  n: number;
  at: string;
  accepted: boolean;
  table: string;
  rows?: number;
  errors?: DataError[];
}

/** GET /{id} —— 诊断全档案快照（status+progress+错误面板+路由结果+清单+冲突） */
export interface DiagnosisDetail {
  diagnosis_id: string;
  product_name: string;
  category: string;
  status: DxStatus;
  stage_hint: string;
  pending_conflicts_n: number;
  updated_at: string;
  /** routed/ready */
  fingerprint?: FingerprintItem[];
  activation_matrix?: ActivationEntry[];
  missing_data?: MissingItem[];
  archive_summary?: { table: string; name: string; rows: number }[];
  /** 档案库行数据（Owner 微调 2026-09-16，联调对齐项）：表 ID → 行数组，
   *  供档案库 Drawer 展示与冲突行标红定位 */
  archive_rows?: Record<string, Record<string, unknown>[]>;
  pending_conflicts?: L2Conflict[];
  /** error 档不变式检出（契约增量 2026-09-17 S28，后端详情 blocking_errors 逐字投影）：
   *  必须修数的硬伤（算术闭合/口径混算），无"维持"语义——前端据此渲染常驻阻断卡片与修数入口 */
  blocking_errors?: L2Conflict[];
  submissions?: SubmissionRecord[];
  /** executing/assembling */
  progress?: Progress;
  /** failed_at(stage)：错误面板 */
  error_detail?: MethodError & { stage: DxStage };
}

/** 500 错误体（13.3） */
export interface ApiErrorBody {
  reason?: string;
  expected_states?: string[];
  current?: string;
  error_id?: string;
}

/* ———— 报告（GET /report，聚合式）———— */
export type EvidenceStrength = '官方' | '第三方' | '估算';
export interface DiagnosticItem {
  L1_fact: string;
  L2_mechanism: string;
  L3_quantification: string;
  L4_prescription: string;
  confounder_check: string;
  evidence_strength: EvidenceStrength;
  chart_refs: string[];
  method: string;
}
export interface DomainSection {
  domain_id: string; // D1..D7
  title: string;
  status: 'active' | 'weak' | 'not_applied';
  note?: string; // weak/not_applied 的原因（不静默缺席）
  items?: DiagnosticItem[];
}
export type QCVerdict = 'pass' | 'warn' | 'fail';
export interface QCItem {
  id: string;
  number: string; // 哪个数字（承重数字标识）
  verdict: QCVerdict;
  issue_type: '溯源不符' | '来源可疑' | '量级存疑' | '口径混用' | '与常识冲突' | null;
  reason: string;
  basis: string;
  owner_verdict?: '维持' | '修正'; // 11.4 落库留痕
}
export interface ChartSpec {
  chart_id: string;
  type: string;
  option: Record<string, unknown>; // ECharts option（零视觉属性，§9 边界约定）
  note: string;
}
export interface ReportResponse {
  domains: DomainSection[];
  qc: QCItem[];
  charts: ChartSpec[];
  conflict_log: string;
  l2_conflict_notes: string;
  downgraded_methods: { method: string; reason: string }[];
  limitations: string;
}

/* ———— 评测（事务 E）———— */
export interface ClaimInput {
  论断: string;
  依据: string;
  来源: string;
  立场: string;
}
export interface ClaimEvaluation {
  claim_id: string;
  对照档: 'covered' | 'conflict' | 'increment';
  detail: string;
}
export interface PendingClaimVerdict {
  cid: string;
  mine: string; // 我方结论
  theirs: string; // 外部论断
  detail: string;
}
export interface ClaimsResponse {
  evaluation: ClaimEvaluation[];
  pending_verdicts: PendingClaimVerdict[];
}
export interface EvaluationResponse {
  evaluation: ClaimEvaluation[];
  pending_verdicts: PendingClaimVerdict[];
  verdicts: { cid: string; verdict: string; at: string; note?: string }[];
}
