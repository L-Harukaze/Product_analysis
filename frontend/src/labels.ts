/**
 * 人类可读标签映射（Owner 微调 2026-09-16）。
 * 纪律：数据层/契约层保留代号（F1/M01/表D），展示层统一在此翻译——
 * 标准：第一次使用本产品的人也知道它在说什么。
 */

/** 方法包代号 → 可读名 */
export const METHOD_LABELS: Record<string, string> = {
  M01: '市场结构分析',
  M02: '学习曲线',
  M03: '版本阶梯定价',
  M05: '交叉价格弹性',
  M06: '总持有成本',
  M07: '信息结构',
  M08: '政策断点分析',
  M09: '金融杠杆',
};

/** 方法徽标（支持 'M06 / M09' 组合与 QC 前缀直通） */
export function methodLabel(m: string): string {
  if (m.startsWith('QC')) return '质检';
  return m
    .split('/')
    .map((s) => s.trim())
    .map((s) => METHOD_LABELS[s] ?? s)
    .join(' + ');
}

/** 数据表代号 → 可读名（缺数清单/错误定位/提交历史共用） */
export const TABLE_LABELS: Record<string, string> = {
  A: '市场结构 · 销量与份额序列',
  B: '竞争格局 · 市场份额（第三方统计）',
  C: '竞争格局 · 市场份额（官方上险）',
  D: '竞争格局 · 竞品价格带',
  E: '成本结构 · 累计销量序列',
  F: '生态锁定 · 互联与独占功能',
  G: '用户价值 · 残值与维修成本',
};

export function tableLabel(t: string): string {
  return TABLE_LABELS[t] ?? `数据表 ${t}`;
}

/** 指纹判定来源（契约枚举）→ 可读名 */
export const SOURCE_LABELS: Record<string, string> = {
  'L1 规则': '规则直判',
  'L2 定量·查表': '定量查表',
  'L3 仲裁': 'AI 仲裁',
};

/** 状态机枚举 → 可读名（列表筛选/徽标） */
export const STATUS_LABELS: Record<string, string> = {
  created: '创建中',
  routed: '待补数据',
  ready: '待执行',
  executing: '分析执行中',
  assembling: '报告装配中',
  done: '已完成',
  'failed_at(routing)': '路由失败',
  'failed_at(data)': '数据异常',
  'failed_at(executing)': '执行中断',
  'failed_at(assembling)': '装配失败',
};

export function statusLabel(s: string): string {
  return STATUS_LABELS[s] ?? s;
}
