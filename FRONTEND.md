# FRONTEND.md — AIAC产品研判系统 前端需求文档 v1.2

> 本文件是前端生成的唯一需求源。数据契约 = `ARCHITECTURE.md` 第 13 章；
> 布局基线 = `code.html` 线框草图（布局可重设计，状态机映射与功能分布以本文件为准）。
> 三者冲突时：**契约 > 本文件 > 草图**。
> 术语 = 架构词汇表：指纹 F1-F6 / 问题域 D1-D7 / 方法 M01-M09+S4 / QC 层 L1-L4。
> **禁止发明契约中不存在的状态、枚举、字段、图表语义**（v1.0 的教训，见 10）。

## 0. v1.1 变更摘要（相对 v1.0）

1. 页面架构按状态机重构：新增**数据工作台**（routed/ready 长停留态，人肉断点 1+2），
   执行页与工作台分离；首页与列表页合并（Owner 决策 1/3）。
2. 砍掉 React Flow 拓扑图（决策 2）：方法间是并发（P-1），非串行 DAG，
   回边不成立；改为方法卡片网格 + 轻量管道条。
3. 轮询边界修正：覆盖 executing + assembling，终态停止（同步回填 ARCHITECTURE 13.4，决策 4）。
4. 删除全部发明内容：needs_input / upstream_timeout 等错误四分类 /
   "实现度雷达图"等评分图表 / progress.trace 实时仲裁（契约中均不存在，决策 6）。
5. 补全评测区（claims 三层对照）、恢复回路 UI（reroute / execute 重放 / reassemble）、
   指纹仲裁留痕 Drawer。
6. Token 层补全：状态徽标浅底系 / warning 三档 / 间距与字号 scale / 图表色板（决策 5）/
   AntD 整合方案 / ECharts 主题注入机制。

## 0.1 v1.2 变更摘要（Owner 参考图二轮定稿）

全局视觉从"暖米浅底"切换为**出版物式深色低饱和体系**：

1. 底色四层：页面底漆黑 #161823 → 卡片紺蝶 #2C2F3B → 凹槽瑾瑜 #1E2732 → 浮层苍黑 #395260；
2. 状态色降饱和为"亮字档"（苍葭/芸黃/唇脂/暮山紫），徽标底与描边改 **color-mix 同色派生**；
3. 字体三族：**衬线中文标题**（Noto Serif SC，本地打包分片加载）/ Inter+系统黑体正文 /
   JetBrains Mono（eyebrow 与代码）；
4. **组件质感规范**（§3.7）：卡片描边+顶缘微亮+一点点扩散微光；说明框内嵌凹槽；按钮柔光阴影；
5. **中英结合**：卡片头 eyebrow 英文小标签（等宽拉字距）+ 中文衬线标题；
6. P0 首页补两侧结构小字（顶部品牌导航 + hero 底部 meta 行）；
7. 图表五色同步低饱和化（挼蓝/苍翠/昏黄/棠梨/苍青）。

试色页 v2（/__tokens）为 v1.2 的评审载体，Owner 确认后才施工页面。

## 1. 定位与铁律（最高优先级，违反任何一条即返工）

1. **前端是纯消费者**：所有语义判断（指纹判定、激活矩阵、缺数清单、QC 结论、
   冲突仲裁、阶段提示文案）在服务端完成。前端只渲染 API 响应，
   禁止在前端推算任何业务结果。
2. **失败必须可见 + 恢复必须可达**（T6 + 3.4）：failed / 409 冲突 / QC-warn / QC-fail /
   weak 域降级，每种状态都有明确 UI；三个恢复回路必须有可见入口——
   failed_at(routing)→`POST /reroute`、failed_at(executing)→重放 `POST /execute`、
   failed_at(assembling)→`POST /reassemble`。不许静默吞掉，不许只做成功路径。
3. **轮询纪律**（P-4 / 13.4）：status ∈ {executing, assembling} 时以 2s 间隔轮询
   `GET /diagnoses/{id}`（executing→assembling→done 自动过渡，中断轮询将等不到 done）；
   到达终态（done / failed_at）立即停止。routed / ready 不轮询。
   页面刷新不丢状态——由 GET /diagnoses/{id} 恢复（T5）。
4. **样式纪律**：颜色、圆角、间距、字号一律引用语义 token（§3），
   禁止硬编码色值 / 魔法数字；禁止直接引用 tokens.css 的 --cc-* 原始变量。
   色值唯一例外：`src/theme/chartPalette.ts`（ECharts canvas 无法消费 CSS 变量，见 3.4）。
5. **术语纪律**：UI 文案与代码命名使用 §1 开头的架构词汇表与 13 章契约枚举，
   状态徽标、错误结构、按钮文案（维持/修正）与契约逐字对齐。

## 2. 技术栈

- Vite + React 18 + TypeScript
- UI 组件库：Ant Design 5（ConfigProvider + cssVar 模式注入语义 token，见 3.3）
- 数据图表：ECharts 5（**自封装 ~30 行 `<EChart option/>` 组件**：init / resize 监听 /
  dispose；不用 echarts-for-react——维护停滞且封装层无附加价值）
- 数据请求：TanStack Query v5（轮询用 refetchInterval 函数式条件）
- 路由：React Router v6
- Mock：本地 mock 模块 + VITE_USE_MOCK 环境变量切换
- ~~@xyflow/react~~（v1.1 移除：DAG 暗示了不存在的串行依赖）

## 3. 设计 Token

### 3.1 颜色语义层（v1.2 深色低饱和体系）

全部出自 cathycolor.css，命名语义化；层次用 color-mix 派生（§3.4），不再为状态设固定浅底色。

```css
:root {
  /* 底色四层(深) */
  --surface:          #161823; /* 漆黑:页面底 */
  --surface-raised:   #2C2F3B; /* 紺蝶:卡片/组件底(浮起) */
  --surface-inset:    #1E2732; /* 瑾瑜:说明框/代码框(inset 凹槽) */
  --surface-elevated: #395260; /* 苍黑:浮层/下拉/hover 亮一档 */

  /* 文字四档(深底上由亮到暗) */
  --text-main:     #C9CFC1; /* 餘白:正文 */
  --text-sub:      #BDCBD2; /* 影青:辅助/说明 */
  --text-disabled: #75878a; /* 苍色:禁用/L3 缺席 */
  --text-faint:    #50616d; /* 墨色:eyebrow/水印/最弱级 */

  /* 线 */
  --border:        #50616d; /* 墨色:实色 token,透明度由组件层 color-mix 调 */

  /* 主色(低饱和青蓝) */
  --primary:        #6E9BC5; /* 挼蓝:按钮/链接/激活态/图表系列1 */
  --primary-strong: #3271AE; /* 青冥:hover/强调/选中 */

  /* 状态色(低饱和亮字档;徽标底=同色 color-mix 派生,见 §3.4) */
  --success:        #A8BF8F; /* 苍葭:done 文字 */
  --success-strong: #519a73; /* 苍翠:图表/强调 */
  --warning:        #C89B40; /* 昏黄:警示底基准(Alert/触发被拒) */
  --warning-text:   #D2A36C; /* 芸黃:warning 场景徽标文字 */
  --danger:         #C25160; /* 唇脂:failed/QC-fail 文字 */
  --danger-strong:  #B15A43; /* 棠梨:图表/强调 */
  --ready:          #A4ABD6; /* 暮山紫:ready(区别 routed 暖金系) */

  /* 深色 hero(P0;与 surface 同源,语义独立保留) */
  --hero-bg: #161823;
  --hero-fg: #C9CFC1; /* 餘白 */

  --radius: 8px;
  --radius-lg: 12px;
}
```

状态徽标总表（P0 列表 / 方法卡 / 诊断壳通用，**AntD Tag 自定义映射，禁止预设色**）。
深色版做法：**亮字档 + 同色低透明底/描边**（`color-mix(字色 14%, transparent)` 底、
`30%` 描边），实现见 `src/components/StatusTag.tsx`：

| status | 字色档 | 备注 |
|---|---|---|
| created | text-sub | 瞬时态，防御性渲染，正常不可见 |
| routed | warning-text | 人肉断点1：等你补数 |
| ready | ready | 人肉断点2：等你拍板 |
| executing | primary | + Loading 图标 |
| assembling | primary | 文案"装配中" |
| done | success | |
| failed_at(*) | danger | 列表行整行 danger 10% 淡底（color-mix 派生） |

### 3.2 非颜色 Token

```css
:root {
  /* 间距 scale(禁止魔法数字,组件 margin/padding 一律取此档) */
  --space-1: 4px;  --space-2: 8px;  --space-3: 12px; --space-4: 16px;
  --space-5: 24px; --space-6: 32px; --space-7: 48px;

  /* 字号 scale(标题衬线/正文无衬线;中文行高 1.7) */
  --font-display: 44px; /* P0 hero 标题(衬线) */
  --font-h1: 26px;      /* 页面标题(衬线) */
  --font-h2: 19px;      /* 区块标题(衬线) */
  --font-h3: 15px;      /* 卡片标题(衬线) */
  --font-body: 14px;
  --font-caption: 12px; /* 徽标/辅助/表格次要列 */
  --font-eyebrow: 11px; /* 卡片头英文小标签(等宽拉字距) */

  --font-serif: 'Noto Serif SC', 'Source Han Serif SC', 'STSong', 'SimSun', serif; /* 标题:衬线中文 */
  --font-sans: 'Inter', -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; /* 正文 */
  --font-mono: 'JetBrains Mono', Menlo, Consolas, monospace; /* eyebrow/采集 prompt/错误面板 */

  /* 层级(AntD 自管层对齐此表,自定义浮层只用这三档) */
  --z-sticky: 100;  --z-overlay: 1000; --z-toast: 1100;
}
```

### 3.3 单一来源与 AntD 整合（色值只写一处）

`src/theme/tokens.ts` 是**唯一色值源**（对象字面量）。启动时两路分发：

1. `setProperty()` 注入 `:root` CSS 变量（首帧 render 前执行，无闪烁）；
   global.css 只写非颜色 token 与组件样式（引用 `var(--*)`）。
2. `<ConfigProvider theme={{ algorithm: theme.darkAlgorithm, cssVar: true, token: {...} }}>`：
   colorPrimary/colorSuccess/colorWarning/colorError/colorBgLayout(漆黑)/
   colorBgContainer(紺蝶)/colorBgElevated(苍黑)/colorBorder(墨色)/colorText 四档/
   borderRadius。**v1.2 启用 darkAlgorithm**（AntD 组件按深色派生）；主色为中亮度
   低饱和，实底按钮文字用深字（colorTextLightSolid=漆黑）。
   AntD 自带的默认蓝在未映射处会漏出，映射表覆盖常用全集（评审项）。

ECharts 主题：`init` 时注入 `theme` 对象（色板见 3.4），后端 `charts[].option`
**不含颜色类属性**（此边界需与 chart_templates.yaml 约定，见 §9 期望清单）。

### 3.4 图表色板与派生规则

`src/theme/chartPalette.ts`（图表色唯一入口；与 `tokens.ts` 并列的两个色值文件，grep 验收豁免）：

```ts
export const chartPalette = [
  '#6E9BC5', // 挼蓝  (与主色同源)
  '#519a73', // 苍翠
  '#C89B40', // 昏黄  (暖金)
  '#B15A43', // 棠梨  (暖赭)
  '#7397ab', // 苍青  (灰蓝)
]; // >5 系列:同色相明度递减循环,禁止引入新色相
```

选色逻辑：低饱和亮字档（深底可辨），蓝-青绿-金-赭-灰蓝色相均匀分布，堆叠相邻可辨。
图表中性色（轴线/网格/图例文字）由 chartPalette.ts 从 tokens.ts 派生导出
（chartNeutrals，网格取瑾瑜=卡片内更暗一档）；ECharts 主题在 EChart 组件内注册注入，
调用方 option 零视觉属性。

派生规则（不算硬编码，验收允许）：`color-mix()` 从 token 派生——混 transparent
（徽标底/描边/淡底）、混纯黑/纯白（仅明度与透明度调整，不引入新色相）。深色体系下：
状态徽标底=同色 14% 透明、failed 行=danger 10%、卡片顶缘微亮=白 4%、
微光=primary 7% 透明。

### 3.5 tokens.css（555 中国色原始字典）

保留在仓库，**仅作挑色参考，禁止任何组件引用 --cc-\***。
需新增语义 token 时：先在对话中提议（给出候选 --cc-* 色），Owner 确认后进 §3.1。

### 3.6 Token 试色页（施工前置评审物）

静态页（dev 路由 `/__tokens`，不进生产构建）：v1.2 深色版平铺——hero 氛围样张
（含两侧结构小字）、徽标七态、**质感卡片×4（eyebrow+衬线标题+内嵌说明框）**、
按钮体系、Alert 三态、文字层级、图表五色实战、间距标尺、表格 failed 淡底、代码块凹槽。
**Owner 过目确认后**，才允许开始页面施工。

### 3.7 组件质感规范（Owner 参考图二轮定稿）

全局三种质感（实现 = global.css 工具类 `.cc-card` / `.cc-inset` / `.cc-eyebrow` / `.cc-serif`）：

1. **卡片**：细描边 + 顶缘一线微亮 + **一点点扩散微光**（primary 7% 透明——
   "只需要一点点光"）：`inset 0 1px 0 白4% / 0 0 0 1px 墨色22% / 0 0 18px primary7%`。
2. **说明框/代码框**：**内嵌在卡片里的凹槽效果**——底=瑾瑜（比卡片暗一档），
   `inset 0 2px 8px 黑38%` + 内描边，内容文字用影青档。
3. **按钮阴影**：主按钮柔光（primary 26% 透明扩散）、默认按钮顶缘微亮——
   内嵌高级感，禁止生硬大投影。
4. **eyebrow 中英结合**：卡片头英文小标签（JetBrains Mono 11px / 0.22em 字距 /
   全大写 / 墨色档）+ 中文衬线标题——中英双行的出版物节奏。
5. **衬线标题**：display/h1/h2/h3 用 Noto Serif SC（500/600/700 本地打包，
   unicode-range 分片按需加载）；正文 Inter+系统黑体；mono 只用于 eyebrow/prompt/错误面板。

## 4. 信息架构与路由（按状态机映射）

```
/                          P0 首页:hero + 搜索入口 + 下拉式最近诊断
/workspace/:id             P1 数据工作台:routed + ready(人肉断点 1+2)
/workspace/:id/exec        P2 执行进度:executing + assembling(唯一轮询页)
/workspace/:id/report      P3 报告与评测:done
```

/workspace/:id 三页共享**诊断壳**（嵌套路由 Layout）：顶部产品名 + 状态徽标 +
四步指示器（路由 → 数据准备 → 执行 → 报告，dot 状态由 status 驱动）+
失败横幅槽位（§4.1）。

**页面守卫**（进入页面先 GET /{id}，status 与路由不符时重定向）：

| status | 落点 |
|---|---|
| created | 瞬态：壳内骨架屏（防御性，正常不可见） |
| routed / ready | P1 数据工作台 |
| executing / assembling | P2 执行进度 |
| done | P3 报告与评测 |
| failed_at(routing / data) | P1 + 失败横幅 |
| failed_at(executing / assembling) | P2 + 失败横幅 |

刷新恢复 = GET /{id} → 按上表渲染/重定向（T5）。

### 4.1 失败横幅（诊断壳统一组件）

按 stage 渲染错误详情（结构=契约 10.2：`{超时值, 重试次数, 拆轮记录, 原始报错}`，
无契约外"错误分类枚举"）+ 对应恢复按钮：

| stage | 文案 | 动作 |
|---|---|---|
| routing | "路由失败"+错误详情 | 重试路由 → `POST /{id}/reroute` |
| data | "数据事务异常"(基础设施失败，非打回) | 重试提交 → 重新走 POST /data |
| executing | "执行中断(基础设施失败)" | 重放执行 → `POST /{id}/execute`(全重跑，3.4) |
| assembling | "装配失败" | 重新装配 → `POST /{id}/reassemble` |

注意：**方法级失败不是 failed_at**——不进横幅，留在 P2 方法卡上（不传染原则）。
done 态不暴露 reassemble 入口（契约允许但 UI 不引导，防误触）。

## 5. 页面规格

### P0 首页（/）——仪式感 + 唯一列表入口

布局按 Owner 参考图（单列居中堆叠，全屏 hero 氛围；背景视觉由设计稿定，
深色 `--hero-bg` 起步）：

1. **两侧结构小字**（v1.2，Owner 参考图定稿，高级感来源）：
   顶部品牌导航条——左：mark + 品牌名（衬线）+ eyebrow「DIAGNOSIS ATLAS」；
   右：方法论 / 七问体系 / 评测闭环 / 演示（V1 占位链接，caption 档）。
   hero 底部 meta 行——左「ECON PACKS M01-M09」右「LOCAL DEMO · CHINESE COLOR TOKENS」
   （eyebrow 档，最弱文字级）。
2. **标题区**（上部，居中，窄列）：eyebrow kicker 行 + 产品名大标题
   （衬线 --font-display）+ 一句话定位 + 副标题「七问诊断 · 四层溯源 · 全留痕」。
3. **搜索区**（居中，约 640px 宽，大尺寸）：产品名输入。
   下方折叠区（Collapse）：高级选项——品类提示 category_hint（可选）、
   已知事实 known_facts.price（可选，决定 F1 走 L2 查表还是 L3 仲裁；前端不强制）。
   字段名与契约 13.2 逐字一致。
4. **最近诊断区**（默认收起）：搜索框下方一个下拉把手
   （chevron 图标 +「最近诊断 N 条」），点击展开/收起面板（高度过渡动画）。
   面板内容 = `GET /diagnoses` 全量（V1 量小）：
   - 顶部状态筛选 Tabs（枚举=3.2 状态机，含 failed 汇聚项）——T6：failed 必须可筛；
   - 表格列：产品名 / 品类 / 状态徽标(§3.1 总表) / 阶段提示(后端下发，见 §9) /
     更新时间 / 操作；failed 行整行 danger 淡底，操作列内联恢复按钮
     （failed_at(routing) 行直接摆「重试路由」）；
   - 点击行 → 按守卫表跳转对应页。

**提交流**：POST /diagnoses 是同步事务 A（P-5：≤15s 含仲裁）。
等待期渲染 **staged 乐观动画**（路由中 → 指纹判定 → 差异化仲裁 → 矩阵生成，
纯前端阶段感，无实时数据——契约没有事务 A 中途进度端点，禁止虚构 trace）；
响应到达后跳转 `/workspace/:id`（routed 态：指纹/矩阵/缺数/prompt 已在响应里，
直接渲染，无需重复拉取）。等待期禁用提交按钮防重复创建。
（P-5"仲裁留痕是内容"：响应到达后留痕在工作台指纹 Drawer 展示，见 P1。）

### P1 数据工作台（/workspace/:id）—— 本产品人机协同的核心页

双栏「左看右做」（草图 Frame 2 基线，58:42），routed → ready 同页演化。

**左栏：系统想清楚了什么（信任感）**

- **指纹卡片**：六卡三列（F1-F6），每卡 = 维度名 + 判定值 + 来源标签
  （`L1 规则` / `L2 定量·查表` / `L3 仲裁`——三级漏斗 7.1 的 UI 化）。
  L3 判定卡（F3/F4）高亮可点，开 Drawer：{判定值 | 理由 | 引用先例/品类锚点 | 置信}
  （仲裁留痕 = PRD 2.3 演示亮点位，数据来自 POST /diagnoses 响应的 fingerprint）。
- **激活矩阵表**：`activation_matrix[]` 渲染 {域, 方法, 形态, 路由理由}；
  不触发的域显式登记"不适用+原因"（不静默缺席）。
- **缺数清单**：`missing_data[]` checklist，随每次提交动态刷新；
  清空时本栏顶部亮出「触发执行」主按钮（断点 2 的动作）。

**右栏：你要干的活（流水线）**

- **采集 Prompt 区**：`GET /{id}/collection-prompt`（打回后自动取最新版，
  内含拒绝原因与行/字段定位——6.1 第四节）。等宽深色代码块 + 复制按钮
  （message.success「已复制」）。routed 态常驻。
- **提交区**：粘贴豆包返回 JSON 原文 → `POST /{id}/data`。
  合格 → accepted + archive_summary + 缺数清单刷新；打回 → 错误定位表
  （`errors[{table, row_index, field, error}]`，逐字渲染，定位到行/字段是本页核心体验）。
- **提交历史**：历次提交卡片流（✕ 打回/✅ 入档 + 时间），历史全留痕可折叠。
- **ready 态**：右栏顶部替换为「触发执行」主按钮。
- **L2 冲突面板**（触发被拒 11.3）：点击触发执行返回 409 时，在本栏内联展开
  （Alert warning + `conflicts[]` 清单 + 两按钮：**修数**（默认，引导回提交区）
  / **维持**（ghost → `POST /{id}/conflicts/{cid}/verdict` 落库注记，再触发即放行））。
  视觉 = warning-bg，语义是"触发被拒"不是故障，与红色失败严格区分。

### P2 执行进度（/workspace/:id/exec）—— 看得见引擎在转

- **管道条**（轻量，纯 CSS/SVG 一行示意）：
  `数据档案 → [ N 个方法并行 ] → QC → 装配 → 报告`，节点随阶段点亮。
  不画 DAG（方法间无依赖，P-1 并发），不引入图形库。
- **方法卡片网格**（4 列）：节点 = **激活矩阵实际激活的方法（M 系，动态数量）**，
  每卡 = 方法名 + 状态徽标（pending / running(Rn) / done / failed——
  phase 格式逐字用契约 10.2 的 `running(Rn)`）+ 轮次进度。
  运行中 Spin；失败卡红边，展开错误面板
  （`{超时值 | 重试次数 | 拆轮记录 | 原始报错}`，含"已按声明拆轮重跑"的记录）。
  方法失败**不传染**：失败卡常驻展示，其余照常推进（3.4/K07 的可见层）。
- **QC 卡与装配卡**：作为网格内的同构卡片呈现（QC=逐方法批量·并发≤4；
  装配=全部终态后自动开始）——引擎视角的诚实，不特殊化。
- **assembling 过渡**：全部方法终态后网格淡出 → 「报告装配中…」骨架屏
  （轮询持续，见铁律 3），到 done **自动跳转** P3。
- 轮询实现：TanStack Query `refetchInterval: 2000`，函数式条件
  （status ∈ {executing, assembling} 才续），终态自动停。

### P3 报告与评测（/workspace/:id/report）—— 最重的一页，纵向长页

左侧 sticky 锚点目录（7 域 + 诚实性区 + 评测区），正文列收 ~900px 保证行宽。
顺序 = 信任链：**总览 → 逐域证据 → 自曝短板 → 外部评测**。

1. **报告头**：产品名 + 域覆盖概览 + QC 汇总徽标（pass/warn/fail 计数，
   徽标**必须可点击**开 QC Drawer——6.3：禁止可见但不可用）。
   成本行（LLM 调用次数/token）数据源不在契约内，mock 先行，真实端点见 §9。
2. **域章节**（`domains[]` 同构渲染）：
   - active：四层诊断卡（L1 事实 / L2 机制 / L3 量化 / L4 处方）逐条渲染，
     **证据强度标签（官方/第三方/估算）必显**——诚实性的可见层；
     `chart_refs` 指向的图表就地渲染。
   - weak / not_applied：占位卡 + 原因文案（如"M09 降级，原因：保值率数据不足 3 期"）
     ——**绝不静默缺席**（12.1）。L3 缺席显示"按规则缺席"说明（是内容不是缺陷）。
   - 图表：`charts[]` 的 ECharts option 直接 setOption（主题注入 §3.3），
     前端不发明图表类型与语义（v1.0 的"雷达图/评分图"已删——12.3：雷达图不入库，
     报告无评分体系）。空数据渲染「该域无数据(weak/缺席)」占位。
3. **诚实性区**（正文之后、评测之前）：冲突仲裁留痕 `conflict_log` +
   Owner 维持裁决注记 `l2_conflict_notes` + 降级方法登记 `downgraded_methods[]`
   （每项含触发原因）+ 局限汇总 `limitations`。这是面试讲述"诚实性是工程实现"的页面证据。
4. **QC Drawer**：徽标点击 → {哪个数字 | issue_type(五类枚举) | reason | basis}。
   Owner 裁决按钮（**维持/修正**，契约 6.3 术语）→
   `POST /{id}/qc/{qid}/verdict` 落库幂等生效（11.4，与 L2 conflict verdict 同构；
   修正走 2.4 人肉回路，V1 不做系统内重跑）。
5. **评测区**（PRD 10.1，演示亮点）：提交 claim 集（3-5 条 {论断|依据|来源|立场}）
   → `POST /{id}/claims` → 三层对照徽标（covered / conflict / increment）；
   conflict 档渲染裁决卡（我方主张 vs 外部论断 vs 对照详情）+
   裁决按钮 → `POST /{id}/claims/{cid}/verdict`；`GET /{id}/evaluation` 结果落位。
   前端只呈现，不提供"自动学习"入口（评测回流走 2.4 人肉回路）。

## 6. 组件映射表(AntD)

| 需求 | 组件 | 备注 |
| --- | --- | --- |
| 状态徽标 | Tag(自定义色映射 §3.1) | 禁用 AntD 预设色 |
| 最近诊断表 / 打回错误表 | Table(size=small) | failed 行 rowClassName + color-mix 淡底 |
| 失败横幅 / 冲突面板 | Alert(warning/danger) + Button | 按钮组:默认+ghost |
| 指纹/QC/评测冲突 Drawer | Drawer | 徽标与指纹卡点击触发 |
| 质感卡片 + eyebrow | 自定义(§3.7 工具类) | cc-card 微光描边 / cc-inset 说明框 / 衬线标题 |
| 新建诊断(P0 搜索即表单) | Input.Search + Collapse | 高级选项折叠 |
| 采集 Prompt | 自定义 CodeBlock(--font-mono,深色) | + Copy 按钮 |
| 执行进度 | Card 网格 + Progress/Spin | + 管道条(纯 CSS/SVG) |
| 报告锚点目录 | Anchor(sticky 左栏) | 长页导航 |
| 报告图表 | 自封装 <EChart> | 主题注入,空态占位 |
| 评测 claim 表单 | Form.List(3-5 条动态) | 字段名与契约 13.2 一致 |
| Staged 等待动画 | Steps/自绘 | P0 事务 A 等待期 |

## 7. Mock 规范（验收前不依赖任何后端）

1. `src/mocks/` 实现契约**全部 13 个端点**的 mock；`VITE_USE_MOCK=true` 时 api 层
   全走 mock，函数签名与真实请求路径一一对应，联调时逐端点替换。
2. **fixture 数据逐字对齐 `ARCHITECTURE.md` 第 13 章 JSON 示例**
   （字段名、枚举值、嵌套结构），这是联调验收基准，一个字段不许改。
3. **覆盖矩阵**（每端点 × 场景至少一条 fixture）：
   - 正常 done（完整报告，含 L2 裁决注记、QC warn+fail 各一条、weak 域+L3 缺席域）；
   - failed_at × 4 个 stage 各一条（错误结构=10.2）；
   - L2 conflict：execute 返回 409 + conflicts[]，裁决维持后再 execute 放行——
     **完整闭环流**一条；
   - routed（带 prompt）/ ready（清单已空）各一条；
   - reroute / reassemble 恢复成功流各一条；
   - assembling 瞬态一条（验证轮询不断链）。
4. **状态切换器**：dev 悬浮面板（dev-only），任意诊断强制切到任意状态，用于演示走查。
5. **轮询 mock**：executing 的 GET /{id} 每次返回 phase 递增的 progress，
   之后 assembling 一拍、再 done——验证"轮询覆盖 assembling"纪律。

## 8. 验收标准（全部满足才算外壳完成）

- [ ] 断网/无后端下，mock + 状态切换器走完演示全流程：首页搜索 → 等待动画 →
  工作台(指纹/矩阵/prompt/打回→补数→重放) → 触发执行 → 409 冲突→维持→再触发 →
  执行进度(管道条/卡片随 phase 更新) → assembling 过渡 → 报告四层 + QC Drawer +
  claim 评测 + 冲突裁决；外加失败恢复走查（reroute / execute 重放 / reassemble 各一次）。
- [ ] 覆盖矩阵全部边界状态均有对应 UI，无一静默；三个恢复回路入口可达。
- [ ] 轮询仅在 executing/assembling 发生，终态停止（代码可见 + 行为可验）。
- [ ] 全项目无硬编码色值（豁免仅限 `src/theme/tokens.ts` 与 `src/theme/chartPalette.ts`）；
  无 --cc-* 直接引用；间距/字号无魔法数字（scale 之外）。
- [ ] src/api/ 每个函数只调用契约 13.1 存在的端点（§9 期望清单中的端点除外，
  且必须标注"待 13.5 确认"），字段名与契约逐字一致。
- [ ] 术语抽查：状态枚举/错误结构/按钮文案与契约无一处自造。

## 9. 对后端契约的期望清单（13.5 受控补充的输入，待 Owner 确认）

按 13.0 纪律（从既有数据结构推导，无新语义）登记，**前端 mock 先行不阻塞**：

1. `GET /api/diagnoses` 列表响应结构（13.1 只有端点名）：
   `[{diagnosis_id, product_name, category, status, stage_hint, pending_conflicts_n, updated_at}]`。
   stage_hint（"M03 · R2/3 执行中"等）由后端从 status+progress 组装——前端不推算。
2. 报告头成本叙事的数据源：`GET /report` 响应扩展 `llm_stats: {calls, total_tokens}`
   （从 llm_call_logs 聚合），或独立 `GET /{id}/calls`（13.5 候选池已有）。
   V1 此项可缺席（mock 有、真实接口降级隐藏该行）。
3. 图表视觉边界约定：`charts[].option` 不含颜色类属性，颜色由前端主题注入——
   需回填 chart_templates.yaml 约定，避免后端模板写死色值与前端 token 脱节。

已确认：QC 裁决端点 `POST /{id}/qc/{qid}/verdict` 于 2026-09-16 补入
ARCHITECTURE 11.4 + 13.1/13.2（v1.1 评审发现的缺口，Owner 授权修订）。

## 10. 交付物

- 可运行的 Vite 项目（npm i && npm run dev 即起）
- global.css（非颜色 token + 组件样式）/ src/theme/tokens.ts（语义色值源）/
  src/theme/chartPalette.ts（图表色板 + 中性色派生）/ tokens.css（原始字典，未引用）
- Token 试色页（/__tokens，Owner 过目后才施工页面）
- src/mocks/（fixtures + 状态切换器 + 轮询 mock）
- README：mock/真实 API 切换、状态切换器用法、token 修改流程（§3.5）
