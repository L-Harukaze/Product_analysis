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

/**
 * 行引用组（L2 的 `表X 行 N`，1-based）→ 可读文案——map-with-fallback：
 * 表名查得到就翻译、查不到回退原始代号（逐表补全映射，不做半吊子直出）。
 * 同一表的行合并展示：`市场结构 · 销量与份额序列（第 2、3 行）`。
 *
 * nameOf 由调用方从 `detail.missing_data` 构建——后端为每张**激活方法所需表**提供
 * 显示名（含 A-G 之外的扩展表）；L2 引用到的表必在该集合内（与 needed 同源）。
 */
export function rowsRefLabel(rows: string[], nameOf: (table: string) => string | undefined): string {
  const groups = new Map<string, number[]>();
  for (const ref of rows) {
    const m = ref.match(/表([A-Z])\s*行\s*(\d+)/);
    if (!m) continue;
    groups.set(m[1], [...(groups.get(m[1]) ?? []), Number(m[2])]);
  }
  if (groups.size === 0) return rows.join('、');
  return [...groups.entries()]
    .map(([t, ns]) => `${nameOf(t) ?? `表${t}`}（第 ${ns.join('、')} 行）`)
    .join('；');
}

/**
 * L2 不变式 → "怎么改"操作指引（展示层通用文案，五类与 `services/invariants.py` 一一对应；
 * 不含 per-方法知识——指引只说明"把值改成哪种合法形态"，不替用户决定改哪个值）。
 * 用于档案库标红行下方的黄色提示卡片（S28 走查迭代）。
 */
export const INVARIANT_FIX_HINTS: Record<string, string> = {
  '算术闭合': '把同一组份额数值调至合计 = 1',
  '口径混算': '同一分组只保留一种口径的数值——把不一致的行改成与保留口径一致的值（官方与第三方不可混算）',
  '跨源碰撞': '两个来源取值不一致——核对后改成一致值；或先在冲突面板「拒绝变更」保留其一',
  '时窗错位': '修正该行时间窗的起止（起点应早于止点）',
  '值越界': '把数值改到合理域内（份额 0-1 或 0-100；价格/量/额非负）',
};

export function fixHintOf(invariant: string): string | undefined {
  return INVARIANT_FIX_HINTS[invariant];
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
