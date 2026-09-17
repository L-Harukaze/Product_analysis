/**
 * 14 个契约端点（ARCHITECTURE 13.1）——src/api 每个函数只调用契约中存在的端点，
 * 字段名与契约逐字一致（FRONTEND.md 验收标准）。
 */

import { request } from './client';
import type {
  ClaimsResponse,
  CreateDiagnosisRequest,
  CreateDiagnosisResponse,
  DataResponse,
  DiagnosisDetail,
  DiagnosisSummary,
  EvaluationResponse,
  ReportResponse,
} from './types';

export const api = {
  /** 列表（13.1） */
  listDiagnoses: () => request<DiagnosisSummary[]>('GET', '/diagnoses'),

  /** 创建 + 事务 A（13.2：同步返回指纹/矩阵/缺数/prompt） */
  createDiagnosis: (req: CreateDiagnosisRequest) =>
    request<CreateDiagnosisResponse>('POST', '/diagnoses', req),

  /** 详情快照 + 轮询端点（10.2） */
  getDiagnosis: (id: string) => request<DiagnosisDetail>('GET', `/diagnoses/${id}`),

  /** 删除诊断（列表管理：仅删诊断级数据，产品档案与已采集数据保留） */
  deleteDiagnosis: (id: string) => request<{ accepted: true }>('DELETE', `/diagnoses/${id}`),

  /** 最新版采集 prompt（6.1：打回后自动携带拒绝原因） */
  getCollectionPrompt: (id: string) =>
    request<{ prompt: string }>('GET', `/diagnoses/${id}/collection-prompt`),

  /** 事务 B：数据提交（L1 校验循环） */
  submitData: (id: string, payload: string) =>
    request<DataResponse>('POST', `/diagnoses/${id}/data`, { payload }),

  /** 事务 C：触发执行（409=L2 conflict 未裁决，11.3） */
  execute: (id: string) => request<{ task_started: boolean }>('POST', `/diagnoses/${id}/execute`),

  /** L2 conflict Owner 裁决：维持落库幂等（11.3） */
  conflictVerdict: (id: string, cid: string, note?: string) =>
    request<{ accepted: true }>('POST', `/diagnoses/${id}/conflicts/${cid}/verdict`, {
      verdict: '维持',
      note,
    }),

  /** 重放事务 A（failed_at(routing)） */
  reroute: (id: string) => request<{ accepted: true }>('POST', `/diagnoses/${id}/reroute`),

  /** 重放事务 D（failed_at(assembling)/done） */
  reassemble: (id: string) => request<{ accepted: true }>('POST', `/diagnoses/${id}/reassemble`),

  /** 报告（聚合式，一次拿全） */
  getReport: (id: string) => request<ReportResponse>('GET', `/diagnoses/${id}/report`),

  /** L3 QC 条目 Owner 裁决（11.4，落库幂等） */
  qcVerdict: (id: string, qid: string, verdict: '维持' | '修正', note?: string) =>
    request<{ accepted: true }>('POST', `/diagnoses/${id}/qc/${qid}/verdict`, { verdict, note }),

  /** 方法失败重试（Owner 微调 2026-09-16 新增）：携带上轮错误经验重跑该方法——
   *  mock 先行，联调时需与后端补契约（13.1 扩展项） */
  retryMethod: (id: string, method: string) =>
    request<{ accepted: true }>('POST', `/diagnoses/${id}/progress/${method}/retry`),

  /** 跳过失败方法（Owner 微调 2026-09-16 新增）：报告中显式登记为降级——联调时补契约 */
  skipMethod: (id: string, method: string) =>
    request<{ accepted: true }>('POST', `/diagnoses/${id}/progress/${method}/skip`),

  /** 事务 E：提交 claim 集 */
  submitClaims: (id: string, claims: { 论断: string; 依据: string; 来源: string; 立场: string }[]) =>
    request<ClaimsResponse>('POST', `/diagnoses/${id}/claims`, { claims }),

  /** 评测冲突档 Owner 裁决 */
  claimVerdict: (id: string, cid: string, verdict: '外部正确' | '我方正确') =>
    request<{ accepted: true }>('POST', `/diagnoses/${id}/claims/${cid}/verdict`, { verdict }),

  /** 评测结果 */
  getEvaluation: (id: string) => request<EvaluationResponse>('GET', `/diagnoses/${id}/evaluation`),
};
