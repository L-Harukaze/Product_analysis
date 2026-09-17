/**
 * 图表色唯一入口（FRONTEND.md §3.4，grep 验收豁免文件之一，另一为 tokens.ts）。
 *
 * ECharts 是 canvas 渲染，CSS 变量无法穿透，图表色板必须落为具体色值。
 * v1.2：五色换为低饱和亮字档（深底优化），全部出自 cathycolor.css。
 * >5 系列：同色相明度递减循环，禁止引入新色相。
 */

import { palette } from './tokens';

/** 图表系列色（蓝→青绿→金→赭→灰蓝，低饱和、深底可辨） */
export const chartPalette = [
  '#6E9BC5', // 挼蓝(与主色同源)
  '#519a73', // 苍翠
  '#C89B40', // 昏黄(暖金)
  '#B15A43', // 棠梨(暖赭)
  '#7397ab', // 苍青(灰蓝)
] as const;

/** 图表中性色：从语义 token 派生（轴线/网格/图例文字；网格取卡片内更暗一档） */
export const chartNeutrals = {
  axisLabel: palette.textSub,
  axisLine: palette.border,
  splitLine: palette.surfaceInset,
  legend: palette.textSub,
} as const;

/** ECharts 注册主题名（EChart 组件内使用） */
export const CHART_THEME = 'diag';
