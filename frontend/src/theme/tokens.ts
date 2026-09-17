/**
 * 全项目唯一语义色值源（FRONTEND.md §3.3，v1.2 深色低饱和版）。
 *
 * v1.2 视觉方向（Owner 参考图定稿）：出版物式深色系、低饱和中国色、
 * 层次用 color-mix 派生（不再为每状态设固定浅底色）。
 * 纪律不变：修改任何颜色只改这里；global.css 零色值；AntD 从此处映射；
 * 新增语义 token 先向 Owner 提议（候选色从 cathycolor.css 挑选）。
 */

export const palette = {
  // —— 底色层（深，暖冷平衡）——
  surface: '#161823', // 漆黑:页面底
  surfaceRaised: '#2C2F3B', // 紺蝶:卡片/组件底(比底亮一档,浮起)
  surfaceInset: '#1E2732', // 瑾瑜:说明框/代码框(inset 凹槽,介于底与卡之间)
  surfaceElevated: '#395260', // 苍黑:浮层/下拉/hover 亮一档

  // —— 文字层(深底上由亮到暗四档)——
  textMain: '#C9CFC1', // 餘白:正文主色
  textSub: '#BDCBD2', // 影青:辅助/说明
  textDisabled: '#75878a', // 苍色:禁用/L3 缺席
  textFaint: '#50616d', // 墨色:eyebrow 小标签/水印/最弱级

  // —— 线 ——
  border: '#50616d', // 墨色:边框实色 token(透明度由组件层 color-mix 调)

  // —— 主色(低饱和青蓝)——
  primary: '#6E9BC5', // 挼蓝:按钮/链接/激活态/图表系列1
  primaryStrong: '#3271AE', // 青冥:hover/强调/选中

  // —— 状态色(低饱和亮字档;深底上徽标底由组件层 color-mix 派生)——
  success: '#A8BF8F', // 苍葭:done 文字
  successStrong: '#519a73', // 苍翠:图表/强调
  warning: '#C89B40', // 昏黄:warning 底色基准(Alert/触发被拒)
  warningText: '#D2A36C', // 芸黃:warning 场景徽标文字
  danger: '#C25160', // 唇脂:failed/QC-fail 文字
  dangerStrong: '#B15A43', // 棠梨:图表/强调
  ready: '#A4ABD6', // 暮山紫:ready(区别 routed 的暖金系)

  // —— 深色 hero(P0;与 surface 同源,语义独立保留)——
  heroBg: '#161823',
  heroFg: '#C9CFC1', // 餘白
} as const;

export type PaletteKey = keyof typeof palette;

/** 语义 token → CSS 变量名 */
const cssVarMap: Record<PaletteKey, string> = {
  surface: '--surface',
  surfaceRaised: '--surface-raised',
  surfaceInset: '--surface-inset',
  surfaceElevated: '--surface-elevated',
  textMain: '--text-main',
  textSub: '--text-sub',
  textDisabled: '--text-disabled',
  textFaint: '--text-faint',
  border: '--border',
  primary: '--primary',
  primaryStrong: '--primary-strong',
  success: '--success',
  successStrong: '--success-strong',
  warning: '--warning',
  warningText: '--warning-text',
  danger: '--danger',
  dangerStrong: '--danger-strong',
  ready: '--ready',
  heroBg: '--hero-bg',
  heroFg: '--hero-fg',
};

/** 在首帧渲染前调用：注入全部颜色 CSS 变量 */
export function injectTokens(): void {
  const root = document.documentElement;
  for (const key of Object.keys(cssVarMap) as PaletteKey[]) {
    root.style.setProperty(cssVarMap[key], palette[key]);
  }
}
