# AIAC产品研判系统 · 前端

Vite + React 18 + TypeScript + AntD 5（darkAlgorithm）+ ECharts + TanStack Query v5 + React Router v6。

设计规范唯一需求源：`../FRONTEND.md`（v1.2）。数据契约：`../ARCHITECTURE.md` 第 13 章。

## 开发

```bash
npm install
npm run dev        # http://localhost:5173 —— 默认走 mock，断网可跑完整演示
```

## Mock 与真实 API 切换（FRONTEND.md §7）

- **默认 mock**（未设置环境变量即 mock）——演示与走查不依赖任何后端；
- 切真实后端：项目根建 `.env.local` 写入 `VITE_USE_MOCK=false`，请求打到 `/api/*`
  （vite dev 下可配 proxy，生产由 FastAPI 同源部署）。

## 演示全流程走查（mock 下的完整闭环）

1. **P0 首页**：输入「红米 K80」（可在高级选项贴入产品背景信息）→ staged 事务 A 动画 → 自动进入工作台；
2. **P1 工作台**：看产品特征六卡（F3/F4 点开看 AI 判断依据 Drawer）→ 分析方法表 → 数据清单（7 项全展示，✓已采集/✗待采集）；
   右栏复制采集 Prompt → 演示辅助「填入示例：竞品价格带（含错误）」提交看行/字段级错误（提交框已清空，prompt 已带上错误原因）→
   「填入示例：竞品价格带（合格）」→「填入示例：生态锁定（合格）」→ 清单清空转 ready（自动生成 1 处数据冲突）；
3. **触发执行 → 冲突面板**（触发被拒=数据保护，非故障）→
   「拒绝变更」（保留现有数据，直接放行）或「手动更改」（进档案库 Drawer，冲突行标红可改数，
   确认修改回工作台）→ 再触发 → 通过进入执行；
4. **P2 执行进度**：管道条 + 方法卡随轮询推进（M02 中途失败 → **推进暂停**，卡片上出现
   「重试 / 跳过」按钮：重试=带错误经验重跑会成功、错误沉淀到系统缺陷清单；跳过=放弃并在报告登记）
   → 全部处理完 → assembling 骨架屏 → done 自动跳报告；
5. **P3 报告**：四层诊断卡（事实依据/机制解释/量化结论/行动建议，长文分段）+ 证据强度标签 + 图表 →
   弱适用/不适用占位（含原因说明）→ 诚实性区（冲突留痕/未完成方法/局限）→
   质检汇总徽标（通过/存疑/不符）点开 Drawer → warn/fail 条目「维持/修正」裁决 →
   评测区提交外部观点 → 已覆盖/有冲突/独有发现三档 + 冲突裁决「我方正确/外部正确」；
6. **失败恢复走查**：首页下拉面板里 iPhone 17（路由失败）行内「重试产品分析」；
   失败横幅提供 重试产品分析 / 重新执行 / 重新装配 三个恢复入口。

## 架构要点

- **色值单一来源**：`src/theme/tokens.ts`（语义）+ `src/theme/chartPalette.ts`（图表），
  运行时注入 `:root`，AntD ConfigProvider 同源映射（darkAlgorithm + cssVar）。
- **轮询纪律**：`src/hooks/useDiagnosis.ts` 是唯一实现点——status ∈ {executing, assembling}
  时 2s 轮询，终态自动停（P-4/13.4）。
- **页面守卫**：`DiagnosisShell` 按 status 重定向到对应子路由（T5 刷新恢复）。
- **api 层**：`src/api/diagnoses.ts` 14 个端点函数与契约 13.1 一一对应，
  mock（`src/mocks/`）与真实请求共用同一函数签名，联调时逐端点替换。
- **mock 状态机**：`src/mocks/stateStore.ts` 实现全部状态迁移语义（409 闭环/打回定位/
  时间驱动执行推进/恢复重放），fixtures 结构逐字对齐契约 JSON。

## Token 修改流程（FRONTEND.md §3.5）

语义色只改 `tokens.ts`，图表色只改 `chartPalette.ts`；新增语义 token 先向 Owner 提议
（候选色从根目录 `cathycolor.css` 挑选）。`/__tokens` 为试色页（dev-only）。

## 给下一个协作窗口的交接（HANDOFF）

> 本项目由前序会话完成 v1.2 定稿 + 四页施工。你的任务是 Owner 微调 + 完成 FRONTEND.md 任务。
> 需求源 = `../FRONTEND.md`（v1.2），契约 = `../ARCHITECTURE.md` 第 13 章，先读再动手。

### 红线（违反即返工，FRONTEND.md 铁律）

1. 视觉语言已 Owner 二轮定稿（深色低饱和 / 衬线标题 / eyebrow 中英结合 / 描边微光卡 /
   内嵌凹槽 / 按钮柔光阴影）——**微调只在 token 层进行，不许换体系**；
2. 色值单点：改色只动 `src/theme/tokens.ts`（语义）与 `src/theme/chartPalette.ts`（图表），
   新增语义 token 须先向 Owner 提议；组件层允许 color-mix 从 token 派生（混 transparent/黑/白）；
3. 契约纪律：`src/api/` 端点、字段名、枚举与 ARCHITECTURE 13 章逐字一致，禁止发明枚举；
4. 轮询纪律唯一实现点 = `src/hooks/useDiagnosis.ts`（executing/assembling 2s，终态停）；
   页面守卫唯一实现点 = `src/components/DiagnosisShell.tsx`（status→子路由重定向）。

### 文件地图（改什么去哪）

| 要改的东西 | 文件 |
|---|---|
| 颜色/间距/字号/质感 token | `src/theme/tokens.ts`、`src/styles/global.css`（工具类 .cc-*） |
| 图表色与中性色 | `src/theme/chartPalette.ts` |
| 各页面布局样式 | `src/styles/app.css`（前缀：home- / ws- / exec- / rp- / arch-） |
| P0-P3 页面结构与交互 | `src/pages/HomePage|WorkspacePage|ExecPage|ReportPage.tsx` |
| 演示文案与数据（报告/指纹/图表 option） | `src/mocks/fixtures.ts` |
| 代号→人类可读标签（方法/数据表/状态） | `src/labels.ts`（Owner 微调新增） |
| mock 状态机行为（409/打回/执行推进/重试跳过/恢复） | `src/mocks/stateStore.ts`、`src/mocks/handlers.ts` |
| 契约类型 | `src/api/types.ts`（联调基准） |
| 通用组件 | `src/components/StatusTag|EChart|DiagnosisShell|StepIndicator|FailureBanner|ArchiveDrawer` |

### 设计意图（这些"看起来怪"的是故意的，别当 bug 修）

- **M02 执行失败**是演示素材：错误面板 + 推进暂停 + 重试/跳过 + 报告降级登记（K07 可见层）；
- **触发被拒（409）闭环**是刻意设计：缺数清空 → ready 自动生成 1 处数据冲突 → 触发被拒（黄色≠红色故障）→
  「拒绝变更」或「手动更改（档案库改数）」→ 再触发放行（11.3 语义）；
- 提交区的「填入示例」是**演示辅助按钮**（dev 体验用），不是产品功能；
- P0 staged 动画是前端乐观进度——契约没有事务 A 中途进度端点，**不能改成真 trace**；
- 采集 prompt 打回后自动携带拒绝原因（6.1 第四节），提交处理后输入框清空，这是核心体验不是冗余；
- QC 徽标必须可点击（6.3 禁止可见但不可用）；评测区不提供"自动学习"入口（2.4 人肉回路）。

### Owner 微调纪要（2026-09-16，已全部落地）

1. P0 高级选项新增「产品背景信息」长文本——作为路由补充输入注入事务 A，并随采集 prompt 下发（`CreateDiagnosisRequest.background`，联调需补契约）；
2. 术语全面用户语化：F1-F6/M01-M09/表A-G/L1-L4 等代号只在数据层保留，展示层经 `src/labels.ts` 统一翻译；状态徽标/筛选中文化；
3. 右下角 DEV PANEL 已按 Owner 要求移除（`stateStore.forceStatus` 函数保留供测试）；
4. 数据清单展示全部 7 项所需数据（✓已采集/✗待采集），不再只显示缺失项；
5. 冲突裁决改「手动更改（ArchiveDrawer 冲突行标红改数）」/「拒绝变更」；确认动作复用契约 verdict 端点；
6. P2 方法失败时推进暂停（人肉断点），提供「重试」（带错误经验重跑，`POST /progress/{method}/retry`）/「跳过」（`/skip`）——两端点为 mock 先行，联调需补契约；
7. 提交处理后清空「提交豆包返回」输入框（无论入档或打回）；
8. P3 四层标签改为 事实依据/机制解释/量化结论/行动建议；mock 报告内容加长并以 `\n\n` 分段（`RichText` 组件渲染）。

### 未决事项（你的工作方向）

1. **Owner 走查反馈**：四页已施工完成但 Owner 未逐页走查——微调需求以 Owner 口述为准，
   走查路线见上文「演示全流程走查」；
2. 联调对齐项（后端就绪后）：FRONTEND.md §9 期望清单（列表端点字段结构 / llm_stats /
   charts option 零视觉属性约定）；mock 的 `GET /{id}` 返回全档案（含指纹/矩阵/清单），
   契约 13.2 只写了轮询视角，联调时确认响应体丰富度；
3. 验收标准全文见 FRONTEND.md §8（grep 豁免仅限两个色值文件等）。

### 环境备忘

- dev：`cd frontend && npm run dev`（5173；dev server 可能已停，先起再改）；
- build：vite 清空 dist 会触发 IDE safe-delete 保护（字体分片>500 文件）——用
  `npx vite build --emptyOutDir=false` 或先手删 dist；
- 切真实后端：根目录 `.env.local` 写 `VITE_USE_MOCK=false`；
- 本机 C 盘空间不足：agent-browser/Chromium 装不上，自动化走查不可用。

## 里程碑

- [x] Token 体系 + 试色页（v1.2 深色低饱和，Owner 已确认）
- [x] 四页施工完成（P0 首页 / P1 工作台 / P2 执行 / P3 报告评测）
- [x] Mock 层（fixtures + 状态机语义）
- [x] Owner 微调 9 条落地（2026-09-16：术语用户语化 / 背景信息 / 冲突档案库 / 重试跳过等）
- [ ] 联调（后端 P1-P3 里程碑就绪后逐端点替换；需补契约：background / retry / skip / archive_rows）
