# 事务C–E 施工需求 · 交接文档（2026-09-17 更新 · T2 收口）

> **给新窗口的接力说明**：本文件自包含。读完「接力速览」+ 本文件正文 + 开工必读清单即可开工，**不需要考古任何聊天记录**。

---

# 接力速览（2026-09-17 快照 · 新窗口从这里开始）

## 一句话现状

后端事务 C/D/E 的规格化施工进行到 **T2 收口**：

| 事务 | 状态 |
|---|---|
| **T1**（M1 QC 裁决 + D1/D2） | ✅ 完成并留档（2026-09-16 全量冒烟 12 步全绿） |
| **T2**（M2 L2 冲突闭环） | ✅ 代码/文档/验证全部完成，**只等 Owner 跑前端校验卡**（§3 T2 末尾，6 步） |
| **T3**（M3 分轮收口，1 天，核心） | ⏳ 未开始 ← **Owner 确认 T2 后的下一个动作** |
| **T4/T5/T6**（M4 装配 / M5 QC / M6 文档终审） | ⏳ 未开始 |

**全量冒烟留档的诚实标注**：`backend/smoke_out.log` 最后一次全量是 **09:12 跑的，早于 2026-09-17 的 S26 三处修复**。S26 只**减少** L2 检出、不新增阻断（未在 `--fast` 覆盖范围的是步骤 11 的真实管道），判断风险低，但严格的全量留档要等 T6 代码冻结后重跑。

**S27-S29 批次验证（2026-09-17 12:34 本轮）**：`--fast` 冒烟全绿（含步骤 12 新断言：error 档详情 `blocking_errors=1 条`、含行引用）；`tsc --noEmit` 零错误；`vite build` 通过（21.17s）。全量留档仍需 T6 重跑（同上）。

## 硬性工作方式（§0，违反=返工）

1. **一次只做一个事务**；做完立刻停，交 Owner 自己到后端/前端校验；**等确认再动下一个**。
2. **每次交付必须给三样**：①改了哪些文件/哪个函数（一句话一条）②自动验证结果（跑到哪一步、哪步绿/红、原始输出片段）③**尚未验证的部分 + 需要 Owner 看什么**（诚实标注，不许写"已完成"了事）。
3. **不要为了推进度同时改多个事务的代码**——出问题不好归因。

## 2026-09-17 本轮新增（别重做）

| 编号 | 内容 | 落点 |
|---|---|---|
| **S25** | 「修数」路径形同关闭（三缺陷叠加）→ 已修：①入档改**按表覆盖**（提交体=该表全量快照）②`merge_with_verdicts` 只保留"已裁决且未复现"的条目 ③前端 A 方案：抽屉生成**整表修正稿**预填提交区走 `/data` | `routers/diagnoses.py::submit_data::_write_accept`／`services/invariants.py::merge_with_verdicts`／`ArchiveDrawer.tsx`+`WorkspacePage.tsx` |
| S25③附带 | 提交区原本只在 `routed` 渲染 → 修数发生在 `ready` 态根本够不着 → 扩为 `routed \|\| ready` | `WorkspacePage.tsx` |
| **S26** | K80 预建档主线"点执行没反应"（三处叠加）→ 已修：①碰撞分组键加 `period`（原把时序表跨期差异误判成"同指标不一致"，2 条 error 误报永久阻断）②年份正则改非捕获组 `(?:19\|20)\d{2}`（原 findall 只返回"20"）③时窗错位收窄为只检"单行起止倒挂"（原判据对时序表必然误报）④前端 `execute` 失败全部可见（error 档 409 无 conflicts 时也要弹 reason） | `services/invariants.py` ×3／`WorkspacePage.tsx::execute.onError` |
| 工具 | 分层冒烟 **`--fast`**（~2 分钟，跳过最慢的步骤 11）；冒烟**步骤 13 自清理**（只删自己创建的诊断，列表页不再越跑越脏）；`scripts/_q.py` 恢复为 §7 校验工具（**勿删**） | `scripts/smoke.py` |
| **S27** | 前端类型错误挂 build：`AnalysisHistoryCard.tsx` 类型谓词修 `string \| null` → `tsc --noEmit` 零错误 + `vite build` 通过（本 IDE 需 `--emptyOutDir=false` 绕 safe-delete） | `AnalysisHistoryCard.tsx` |
| **S28** | L2 error 档"可见但不可操作"（message 草率 + 档案库在 error 档不可达/不可编辑）→ 已修：详情暴露 `blocking_errors` + 常驻阻断卡片 + 档案库 error 行可编辑 + 无修改确认分叉守卫 | `invariants.py::blocking_errors`／`diagnoses.py`／`models.py`／`WorkspacePage.tsx`／`ArchiveDrawer.tsx`／`smoke.py` 步骤 12 |
| **S29** | ready 态提交区常驻（按表覆盖下的无声覆盖入口）→ 收紧为"有修数动机才显示"（冲突待处理 / error 档；普通 ready 隐藏） | `WorkspacePage.tsx` |
| 清理 | 列表页 32 → **4 条**（2 条红米K80 ready + 小米SU7 + 冒烟测试新品X1） | `data/app.db` |

## 下一个动作（严格按序）

1. **等 Owner 跑完 T2 最终校验卡**（§3 T2 末尾 **8 条 + 小项**，含 S27-S29 新增位）：冲突闭环两条路（修数 / 维持）→ **error 档红色卡片 + 修数闭环**（S28）→ 反向确认"不提交就不入档" → 列表 stage_hint。
2. Owner 确认 T2 收口后 → **T3（M3 收口）**：真机跑通分轮（M03/M04 三轮、M02/M06 两轮，`intermediate_tables.round` 按轮落库）+ **M03 回归基准实跑**（先入档 SU7 七表档案 → `python -m scripts.m03_regression`，比对冻结签发版数据锚）+ 数值级差异登记缺陷日志（**下一个空号 = S30**）。
3. T3 完成后再停。**T3/T4 可共用一次失败注入**（§9：改坏 `executor.model`）——一次验「方法级清桶」（T1/T2 两轮都没验到）+「装配失败不传染」（T4 第 3 条），省一轮 26 分钟。

## 开工必读（按序）

1. `ARCHITECTURE.md` —— 唯一施工图纸。重点：**6.2**（配方五层）/ **8.3**（按表覆盖 + 两条使用约束）/ **10**（编排）/ **11.3**（裁决三档）/ **11.4**（QC 裁决）/ **12**（分域装配）/ **13**（契约）
2. **本文件**：§0（工作方式）/ §2（已完成）/ §3（待完成 T3-T6）/ §5（代码地图）/ §6（已知坑与真机观测）/ §7（Owner 校验卡）/ §8（红线）/ §9（环境命令）
3. `缺陷日志.md` 第八节 **S20-S26** —— 全是真机踩出来的坑，开工前扫一遍能省几小时
4. `frontend/src/api/types.ts` —— 契约权威 TS 投影，后端不发明字段
5. `methods/M03/skill.md` + `methods/_shared/` —— 冻结标杆与纪律层

## 环境与命令

```powershell
# 后端（改完代码必须重启，启动命令无 --reload）
cd e:\Quan_Zhan\产品分析Agent\backend
python -m uvicorn app.main:app --port 8000

# 前端（真实联调：项目根 .env.local 写 VITE_USE_MOCK=false）
cd e:\Quan_Zhan\产品分析Agent\frontend
npm run dev

# 冒烟：快速回归（~2 分钟，改完代码先跑这个）
cd e:\Quan_Zhan\产品分析Agent\backend
python -u -m scripts.smoke --fast

# 冒烟：全量（45-60 分钟，需要留档时后台跑）
Start-Process -NoNewWindow -FilePath python -ArgumentList "-u","-m","scripts.smoke" `
  -RedirectStandardOutput smoke_out.log -RedirectStandardError smoke_err.log

# 查库看执行实况（§7 校验工具）
python scripts/_q.py                      # 最近 2 条诊断 + 最近 8 条调用留痕
python scripts/_q.py dx_xxxxxxxx          # 追加该诊断的中间表按轮落库明细
```

## 六条绝对不要做

1. **不要一次动多个事务**（§0）。
2. **不要在冒烟输出上接 `Select-Object -First N`**：管道提前关闭 → `BrokenPipeError` → 冒烟跑到一半就死，留孤儿诊断（§6.11）。
3. **不要跑冒烟不加 `-u`**：块缓冲，日志滞后 20 分钟，看着像卡死。
4. **不要把"域装配失败 / client has been closed"当装配器缺陷**：那是 `TestClient` 退出触发 `aclose()` 的关服连坐（S24）。
5. **不要删** `scripts/_q.py` / `scripts/m03_regression.py` / `scripts/smoke.py`（都是校验工具，§7 引用）。
6. **不要拿旧 409 体的行号去定位新数据**：按表覆盖后行号会漂移（ARCH 8.3 使用约束②）。

---

## 0. 工作方式（Owner 硬性要求，优先级高于一切）

> 这一节是 Owner 在第二次接力时明确提出的，违反即返工。

1. **一个事务一个事务完成。禁止一口气冲 M1→M6。**
   建议顺序：**M1 收口 → 停下 → M2 收口 → 停下 → M3 → 停下 → M4 → 停下 → M5 → 停下 → M6**。
2. **每完成一个事务，立即停下，交给 Owner 自己到后端校验。**
   - Agent 不要替 Owner 判断"应该没问题"；只负责：改完代码 → 自己跑一遍能自动验证的部分 → 把「Owner 校验卡」（本文 §7）交给 Owner → **等 Owner 确认后再动下一个事务**。
   - 校验方式由 Owner 决定（起服务点页面 / 跑冒烟 / 查库 / 看日志）。
3. **每个事务交付时，Agent 必须输出三样东西**：
   - ①改了哪些文件、哪个函数（一句话一条）
   - ②自动验证结果（冒烟跑到第几步、哪一步通过/失败、原始输出片段）
   - ③**尚未验证的部分 + 需要 Owner 看什么**（诚实标注，不许写"已完成"了事）
4. **不要为了"推进度"同时改多个事务的代码**——一次只动一个事务的范围，出问题好归因。

---

## 1. 一句话任务（更新版）

后端事务 C/D/E 的**规格化收敛**：M1/M2/M3/M4/M5 代码已落，M6 文档已回写；剩余工作 = **按事务逐个真机验证 + 收口 + 冒烟全绿留档 + 缺陷登记**。

---

## 2. 上一窗口已完成清单（含验证状态，别重做）

### 2.1 M1 走查硬门槛 —— 代码完成 ✅ / 真机全绿 ✅（T1 已收口，2026-09-16 第三次接力）

| 改动 | 文件 · 函数 | 状态 |
|---|---|---|
| 轻迁移加三列 `qc_json` / `qc_verdicts_json` / `conflicts_json` | `app/db.py::init_schema` | ✅ 已跑通（冒烟 1-9 绿） |
| QC 条目独立落库（report_json 会被 reassemble 整包重写，裁决必须独立存活） | `services/execution.py::_persist_qc_sync` | ✅ |
| **D1 修复**：`_finalize` 的 QC 一律从库读（不再依赖 pending 分支内变量） | `services/execution.py::_finalize` | ✅ 回归位已加（冒烟 11e） |
| **D2 修复**：execute 清桶 + 方法级清桶（retry 重跑=该方法产物作废重写） | `services/execution.py::start_execution` / `run_method` | ✅ 真机已验证（冒烟 11a-：哨兵中间表被清 + 进度重置 pending）；**方法级清桶（retry 路径）本轮未触发**（7/7 全绿无失败方法），属 T3 复测项 |
| `POST /diagnoses/{id}/qc/{qid}/verdict`（11.4，守卫 done + 条目存在，幂等） | `routers/diagnoses.py::qc_verdict_endpoint` | ✅ |
| `GET /report` 回显 `qc[].owner_verdict` | `routers/diagnoses.py::get_report` | ✅ |
| 冒烟：11c2（裁决落库+报告回显+幂等）、11e（reassemble 重放必须回 done） | `scripts/smoke.py` | ✅ 全绿（2026-09-16 22:27-23:12 跑完 12 步，`全部冒烟断言通过 [OK]`，留档 `backend/smoke_out.log`） |

**顺带修掉的两个硬 bug（都是"事务 C 从未跑通"级别，见缺陷日志 S20/S23）**：

- **S20（最关键）**：`routers/diagnoses.py::_get_state` 过去只返回 `{registry, assets, fp_service}`，**没有 `llm_provider`** → `POST /execute` 后后台任务第一行就 `KeyError: 'llm_provider'` → 整个管道立刻 `failed_at(executing)`、所有方法卡 pending。**这就是"冒烟步骤 10-11 从来没有全绿记录"的真根因**。已修：注入 `request.app.state.llm_provider`。修复后六个方法正常推进（M01/M02/M03/M05/M07/S4 逐轮产出中间表）。
- **S23**：删除诊断后 `GET /{id}` 返回 500（应为 404）——详情 `_read()` 判空时返回三元组、外层按四元组解包。已修，冒烟步骤 9 已绿。

### 2.2 M2 L2 冲突闭环 —— 代码完成 ✅ / 真机验证 ✅（T2 收口，2026-09-17；含 S25 修复）

| 改动 | 位置 | 状态 |
|---|---|---|
| 五类不变式检查器（算术闭合/口径混算=error，跨源碰撞=conflict，时窗错位/值越界=warn） | `services/invariants.py`（新文件） | ✅ |
| execute 三档处置：error→通用守卫体阻断；conflict→409 `{reason, conflicts}` **status 不迁移**；warn→放行落库 | `routers/diagnoses.py::execute_diagnosis` | ✅ |
| `POST /conflicts/{cid}/verdict`（ready + 未裁决冲突，幂等落库） | `routers/diagnoses.py::conflict_verdict` | ✅ |
| 详情/列表真实化：`pending_conflicts` / `pending_conflicts_n` / `stage_hint`（文案对齐 mock："N 处数据冲突待处理"） | `routers/diagnoses.py` | ✅ |
| `POST /data` 守卫扩为 `routed | ready`（11.3 修数路径）；ready 入档后维持 ready | `routers/diagnoses.py::submit_data` | ✅ |
| 冲突裁决 → 装配生成 `conflict_log` / `l2_conflict_notes` | `services/assembly.py` | ✅ |
| **S25①修复**：入档改**按表覆盖**（提交体里的表=最新快照，先作废旧行再写；历史仍由 `data_submissions` 全留痕） | `routers/diagnoses.py::submit_data::_write_accept` | ✅ 真机验证（ARCH 8.3 已补约束） |
| **S25②修复**：`merge_with_verdicts` 只保留"已裁决且未复现"的旧条目，**未裁决且未复现的丢弃**（否则 stale 冲突永久阻断） | `services/invariants.py::merge_with_verdicts` | ✅ 真机验证（ARCH 11.3 已补定） |
| **S26①修复**：碰撞分组键含 `period`（真正的跨源碰撞 = 同维度**且同期**；原判据把时序表跨期差异误判为"同指标不一致"） | `services/invariants.py::_check_source_collision` | ✅ K80 实测：2 条 error 误报清零 |
| **S26②修复**：`_parse_period_window` 正则改非捕获组（原 `(19\|20)\d{2}` 的 findall 只返回"20"，年份全变 20.0） | `services/invariants.py::_parse_period_window` | ✅ |
| **S26③修复**：时窗错位收窄为只检"单行起止倒挂"（原判据对时序表必然误报，K80 实测 9 条全表命中） | `services/invariants.py::_check_time_window` | ✅ K80 误报 9 → 0 |
| **S26④修复**：前端 `execute` 失败全部可见（error 档 409 无 conflicts → 弹 reason；非 409 → 提示查后端） | `frontend/.../WorkspacePage.tsx::execute.onError` | ✅ 类型检查通过 |

**真机验证证据（冒烟日志 smoke_m4/m5.log 步骤 10d）**：
```
10d L2 冲突闭环：C-072cdb 碰撞 → 409（status 不迁移）→ 维持裁决幂等 → 放行
```
（构造数据：某表已有两行同值，再入档一行数值=3 → 跨源碰撞检出 → 409 → verdict 维持 → pending_conflicts_n 归零 → execute 放行）

**T2 真机验证新增证据（2026-09-17）**：
```
[2] 同批提交冲突行 表A（值 1 与 3）→ 已入档
[5] execute（有冲突）→ HTTP 409；status=ready（触发被拒不迁移状态）
    409 体携带 conflicts = ['C-a5f608']
[4] 行号定位核对：C-a5f608 rows=['表A 行 1','表A 行 2']
     '表A 行 1' → archive_rows['A'][0] = {price_official: 1}
     '表A 行 2' → archive_rows['A'][1] = {price_official: 3}   ← 1-based 引用与前端 rows[i+1] 对齐，标红可用
[7] 修数后 execute → HTTP 202（放行）
[7b] L2 重算后 pending_conflicts_n = 0（冲突已被修数清除）
[8] 库内 表A 行数 = 2（按表覆盖生效）
```
**冒烟新增用例**：10d（冲突闭环 = 拒绝变更路径）、**10e（修数闭环 = 手动更改路径，S25 回归位）**、12（error 档：份额不闭合 → 通用守卫体阻断）。

### 2.3 M3 事务 C 规格化 —— 代码完成 ✅ / 解析已验证 ✅ / 真机部分 🔶

| 改动 | 位置 | 状态 |
|---|---|---|
| 轮次表解析（表格式 M03/M04 + 散文式 M02/M06 两种声明形态；解析不到→单轮直出兜底+启动告警） | `app/registry.py::parse_rounds` + `MethodRound` | ✅ 11 包全覆盖实测 |
| `MethodRound.split_by_steps()`（按包声明的 STEP 边界拆子轮，P-2 a 分支的"合法切法"） | `app/registry.py` | ✅ |
| 系统纪律层资产加载（`_shared/discipline.md` + `contract.md`，缺失即启动失败） | `app/registry.py::Registry.shared` | ✅ |
| `MethodPackage.downgrade_flags`（flag 枚举，S4） | `app/registry.py` | ✅ |
| 分轮引擎 + **配方五层**（纪律层/资产层全文/指令层/数据层切片/中间表层） | `services/execution.py::_round_messages` + `run_method` | ✅ |
| 四项静态校验（产出齐全性 / 中间表引用完整性 S17 代码化 / flag 枚举 / 末轮四层完整性） | `services/execution.py::_validate_round` | ✅ |
| P-2 两分支（超时且本轮 ≥2 STEP → 按 STEP 边界拆子轮重跑一次；单 STEP 或仍超 → failed） | `services/execution.py::run_method` | ✅ |
| 方法级清桶 + 中间表按轮落库 | `services/execution.py` | ✅ |
| **M03 回归基准脚本**（6.2 的裁判：复跑 M03，与冻结签发版数据锚比对） | `scripts/m03_regression.py`（新文件） | ✅ 脚本就绪，🔶 需 SU7 档案入档后才能实跑 |

**轮次解析实测输出（已核对，可直接引用）**：
```
M01 1轮(单轮直出)  M02 2轮(STEP 0-1 / 2-6，散文式)  M03 3轮(STEP 0-2 / 3-5 / 6)
M04 3轮  M05 1轮  M06 2轮(散文式)  M07 1轮  M08 1轮  M09 1轮  S4 1轮
```

**真机观测（重要，写进演示素材）**：六个方法全部按轮推进，M01/M02 R1-R2/M03 R1-R2/M05/M07/S4 均成功产出中间表；**M03 R3 在真实模型上约 6 分钟未返回 → 三次尝试后 failed** → 触发失败停顿（符合 P-2 b 分支：R3=单 STEP，包没声明更细切法）。
> ⚠️ **交叉引用**：另一次真实观测（2026-09-16 22:27 全量冒烟）中 **M03 R3 成功**，7/7 方法全绿、未触发失败停顿，见 §6.2。两次都是真实结果，差异来自 LLM 耗时方差（R3 的 prompt 含 skill 全文 + R1/R2 全部中间表，体积最大）——**不要当成文档矛盾，也不要把"必失败"写进演示脚本**。

### 2.4 M4 装配规格化 —— 代码完成 ✅ / 真机未验证 🔶

| 改动 | 位置 |
|---|---|
| 分域 7 次同构装配（`_cluster` 代码归簇+占位 → 单域一次调用 → 代码后校验 → 报告落库）；单域失败回退原始四层并登记 `downgraded_methods` | `services/assembly.py`（新文件，`assemble()`） |
| 冲突**仲裁=代码规则**：官方>第三方>估算；**平局不仲裁**，整体降 conflict 档回交 Owner | `services/assembly.py::_arbitrate` |
| 代码后校验阻断项：四层完整性 / 货币化边界（跨域汇总）/ 图表引用完整性 | `services/assembly.py` |
| **QC 与装配解耦并发**（QC 后台跑，装配同步跑，落库前合并 qc 条目） | `services/execution.py::_finalize` |
| 装配失败 → `failed_at(assembling)` + error_json（可 reassemble 重放） | `services/execution.py::_finalize` |
| 图表装配（纯代码零 LLM）：模板层 `kind/stack` 锁类型，实例层只填值；未批准模板不渲染；option 零视觉属性 | `services/charts.py`（新文件） |
| `chart_templates.yaml` 增 `kind`（bar/scatter/line）与 `stack`（份额恒堆叠）——**资产层锁死选型权** | `methods/_shared/chart_templates.yaml` |

### 2.5 M5 QC 规格化 —— 代码完成 ✅ / 真机未验证 🔶

| 改动 | 位置 |
|---|---|
| per-method 批量 QC（每方法一次调用，携带该方法全部承重数字）；与装配解耦并发 | `services/execution.py::run_qc` |
| **输入白名单 + 隔离模块**（与执行引擎无公共 import，5.5 异上下文） | `services/qc_context.py`（新文件） |
| 承重数字 = 各方法 `diagnostic_items[].L1_fact` 的全部数字 | `qc_context.py::build_batches` |
| 逐条全量：输出条数必须 = 承重数字条数，缺条按 fail 处置（禁空数组偷懒通道）；五类 issue_type 封闭 | `qc_context.py::validate` / `failed_items` |

### 2.6 M6 契约回写 —— 已完成 ✅

- `ARCHITECTURE.md` 13.1：补录 `DELETE /{id}`、`retry`、`skip` 三端点（含守卫）；`data` 守卫改为 `routed/ready`；`execute` 守卫改为"无 error 档、无未裁决 conflict"
- 13.2：补 `background` 请求字段、`execute` 两种 409 体、详情增量字段（`archive_rows` / `pending_conflicts` / `handled`）、进度 phase 多轮形态 `running(Rn/N)`
- 6.2 / 12.2 / 12.3：追加"实现落点"小节（含 prompt 版本戳 `executor-v1.0-recipe5` / `assembler-v1.0-domain7` / `qc-v1.0-whitelist`、四项校验、P-2 两分支、图表 kind 资产化）
- `缺陷日志.md` 新增「八、Agent 基建施工批（S20-S23）」+ 两条连带登记（M03 R3 超时=输入侧体积上限观测；占位数据不产生假结论的判例）

---

## 3. 待完成清单（按事务，逐个交付，逐个等 Owner 校验）

> 以下每一项 = 一次交付。做完一项就停下，交 §7 校验卡给 Owner。

### T1 · M1 收口 —— ✅ 已完成并留档（2026-09-16 22:27-23:12，真实 LLM 全量跑）

**交付证据（`backend/smoke_out.log`，`全部冒烟断言通过 [OK]`）**：
```
11a- D2 清桶：旧中间表已清空 + 进度重置为 pending（8.3）
11b 管道完成：7/7 方法 done（用时 26.6 分钟）
11c 报告：7 域 · 17 张四层卡 · QC 14 条 · 图表 2 张 · 降级 0
11c2 QC 裁决 QC-01：落库 + 报告回显 + 幂等通过
11d 评测：2 条对照（covered/conflict/increment），pending 0
11e 重放装配回到 done（D1 回归通过，用时 12.0 分钟）
11e- QC 裁决 QC-01 在重放装配后仍在（11.4 一次性持久化）
11f 回归诊断已清理
12 error 档阻断通过：算术闭合：字段 share 同组（测试值）合计 1.800 ≠ 1
```
1. ✅ 冒烟 1-10d + 11 全绿（含 11c2 / 11e / 11f）
2. ✅ 冒烟 12（error 档阻断）通过
3. ✅ D2 execute 清桶**真机验证**：新增哨兵断言（execute 前塞 `__SENTINEL__` 中间表 → 202 后必须消失 + 进度重置 pending）
4. ✅ `smoke_out.log` 覆盖留档

**尚未验证（诚实标注）**：方法级清桶（retry 重跑路径）——本轮 7/7 方法全绿，无失败方法，未走到 retry；留给 T3（M3 收口会有失败/拆轮场景）。

### T2 · M2 收口 —— ✅ 验证完成 + A 方案已实施（2026-09-17），**待 Owner 最终校验（确认后才进 T3）**

1. ✅ 冒烟 10d（冲突闭环）/ 12（error 档阻断）通过；新增 **10e（修数闭环）** 作为 S25 回归位——**2026-09-17 08:15-09:12 全量冒烟 12 步全绿**（`backend/smoke_out.log`，末行 `全部冒烟断言通过 [OK]`）
2. ✅ 真机走查 409 两条路：
   - **拒绝变更**（verdict 维持 → `pending_conflicts_n` 归零 → execute 放行）—— 10d 覆盖，留档已绿
   - **手动更改**（修数走 `/data` → 冲突消失 → execute 放行）—— **原本不通，已修**。真机证据：修数后 execute **202**，L2 重算后 `pending_conflicts_n=0`，库内该表 2 行（按表覆盖生效）。根因与修复见缺陷日志 **S25**
3. ✅ 回显与定位核对：`GET /{id}` 的 `pending_conflicts`、`stage_hint`（"N 处数据冲突待处理"）、`archive_rows` 行标红定位全部核对通过（`"表A 行 2" → archive_rows['A'][1]`，1-based 与前端 `rows[i+1]` 对齐）
4. ✅ **A 方案已实施**（Owner 拍板）：见本节末「T2 待决项」。
   **改完后的自检**：后端 `--fast` 全绿（10d/10e/12）；前端 `tsc --noEmit` 全项目零错误（当时唯一报错 `AnalysisHistoryCard.tsx:52`——既有类型错误、曾使 `npm run build` 失败——已于 S27 用类型谓词修复，零新增错误）。

> **T2 最终校验卡（前端行为真机走查，需 Owner 做）**——按 §0，这一步你确认后我才动 T3：
> 1. 起后端 + 前端（`VITE_USE_MOCK=false`），造一个 ready 态诊断：入档 → 点触发执行 → 被 409 拒
> 2. 点「**手动更改**」→ 抽屉里改冲突行的数字 → 点「生成整表修正稿，填入提交区」
> 3. **核对**：提交区应出现该表的**完整 JSON**（原有全部行 + 你改的值，不是只有改动行）
> 4. 点「**提交校验**」→ 应 accepted（若被 L1 打回，说明数值类型不对，看错误定位）
> 5. 再点触发执行 → 应放行（202），L2 重跑后冲突消失
> 6. 反向确认：改数后**不点提交**直接触发执行 → 应仍被 409 拒（证明"没提交就没入档"，不制造假状态）
> 7. **无修改维持路径回归**（S28 动了确认按钮的分叉，必须回归）：沿用第 1 条的冲突诊断 → 被 409 拒后
>    → 点「手动更改」打开档案库 → **不改任何数字** → 点「确认未修改，返回工作台」→ 应走 verdict 路径
>    （网络面板可见 `POST /conflicts/{cid}/verdict`；冲突提示消失）→ 再点触发执行 → 应放行（202）
>    （报告页「人工裁决记录」区的 `Owner 裁决「维持」（已查看档案库，未修改数据）` 留痕需完整跑完装配（26 分钟）
>      才可见，本次走查不做——装配留痕是读库生成，逻辑由 T3/T4 装配轮覆盖）
> 8. **error 档修数闭环**（本轮新增 S28，走查重点）：造一个 ready 诊断，提交一份触发 L2 error 档的坏数据
>    （口径混算/份额不闭合）→ 点触发执行 → 应**不弹一闪而过的 message**，而是页面顶部出现**红色阻断卡片**
>    （逐条错误明细 + 涉及行引用）→ 点卡片上的「**手动更改**」→ 档案库中错误行标红可编辑（badge「错误数据」）
>    → 改数 → 「生成整表修正稿，填入提交区」→ 提交 → 再触发执行 → 应放行（202），卡片随之消失
>    （error 档无"维持"语义：档案库不改数点确认 = 直接返回，不产生裁决留痕，且**提交区只在有冲突/error 时才显示**）
> 9. **小项**：列表页 `stage_hint`——有未裁决冲突的诊断应显示 `N 处数据冲突待处理`（原 T2 清单第三条，顺眼看一下）
>
> 走查备注：①修数重新提交后、下次 execute 放行之前，详情页/列表仍显示旧冲突或旧 error 卡片是**正常**的
> （L2 只在 execute 时计算，§9 已记）；②若走到真实执行，单诊断 26 分钟量级——中途 `python scripts/_q.py` 查进度，
> **别把慢当坏**。

**T2 待决项 —— Owner 已拍板：选 A（2026-09-17 已实施）**：
- `ArchiveDrawer` 新增 `onApplyFix`：确认时把**整表修正稿**（`archive_rows` 当前全量行 + 本地 edits，数值字段还原成 number）交给工作台**预填提交区**，由 Owner 核对后走 `/data` 提交；未修改任何数据时走 verdict 留痕（**S28 修订**：仅当有冲突时——纯 error 档场景 error 无"维持"语义，直接返回；见下第二轮修订）。
- **实施中发现并一并修掉的阻塞点**：提交区原本只在 `status === 'routed'` 渲染，而修数发生在 `ready` 态 → UI 上根本够不着。已扩为 `routed || ready`（后端守卫本就是 routed/ready，是前端漏了；**S29 修订**：ready 态再收紧为"有修数动机才显示"，见下）。
- ⚠️ **整表提交是硬约束**（8.3 使用约束①）：只发改动行 = 未提交的行被覆盖删除。改动文件里都写了注释，将来改这个抽屉的人务必保持。
- 选项 B/C 已否决（B 污染 verdict 端点语义，C 砍掉刚修好的修数叙事）。

**2026-09-17 第二轮修订（Owner 走查反馈 + 外部评审，S27-S29）**：
- **S29 提交区显示策略收紧**：ready 态从"常驻"改为"**有修数动机才显示**"（`pending_conflicts_n > 0` 或 `blocking_errors` 非空）——堵住"普通 ready 手滑重交旧表 = 无声覆盖好档案"（按表覆盖语义下的 UX 侧数据丢失口）。**error 档场景必须保留提交区**（那是它的修数唯一出口；外部评审原建议"仅按冲突判断"漏了此场景）。
- **S28 error 档修数闭环**：详情 `blocking_errors`（契约增量，ARCH 13.2 已登记；409 体保持 13.3 通用守卫体三字段不变）→ 前端常驻红色阻断卡片（替代草率 message）→「手动更改」→ 档案库 error 行标红可编辑 → 整表修正稿 → `/data` 重交。
- **S27**：`AnalysisHistoryCard.tsx` 类型谓词修复（`tsc --noEmit` 零错误、`vite build` 通过；本 IDE `npm run build` 的 dist 清空会被 safe-delete 保护拦截，用 `npx vite build --emptyOutDir=false` 验证）。
- **走查用上面更新后的 8 条 + 小项卡**（原 6 条 + 第 7 条维持路径回归 + 第 8 条 error 档闭环）。

### T3 · M3 收口（1 天，核心）
1. 真机跑通分轮：确认 M03 三轮、M04 三轮、M02/M06 两轮的中间表按轮落库（`intermediate_tables.round`）
2. **M03 回归基准实跑**：先把 SU7 七表档案入档（豆包采集 → 事务 B 入档），再 `python -m scripts.m03_regression`，比对《M03 v1.0 冻结签发版》数据锚（21.59/24.59/29.99、136854、234479、28.57/28.27/43.16、26.06、109700/75050）
3. 数值级差异 = 配方缺陷 → 登记缺陷日志（**下一个空号 = S30**；已占用 S20-S29：S20=execute 未注入 llm_provider、S21=D1 reassemble 卡死、S22=D2 重放不清桶、S23=删除后详情 500、S24=冒烟预算误判、S25=修数路径形同关闭、S26=K80 阻断三处叠加、S27=前端类型错误挂 build、S28=error 档修数入口不可达、S29=ready 提交区常驻覆盖风险）

> **失败注入跑法（P1-2 要求）**：这次注入轮跑冒烟**不要 `--fast`**——步骤 12 前移后（顺序 1-10 → 12 → 11）的完整链路还没有过一次全量转正（现有留档跑在重排之前）。命令：`python -u -m scripts.smoke`（全量，含 11；用 `--steps` 显式声明也行——含 11 即全量模式）。顺带完成"重排后首次 11"验证：若 12 与 11 之间有未预见的数据依赖，在这里炸比拖到 T6 好。

### T4 · M4 收口（0.5 天）
1. 真机确认分域装配：报告 `domains` 数量 = 激活矩阵域数（含 weak/not_applied 占位）
2. 确认 `charts` 非空（有中间表的方法应出图）、`chart_refs` 引用合法、`conflict_log` / `l2_conflict_notes` 有内容
3. 演示一次"装配失败不传染"：临时改坏一个域的调用（如 executor model 改错），确认该域回退原始四层 + downgraded_methods 登记，其余域照常

### T5 · M5 收口（0.5 天）
1. 真机确认 per-method QC 调用数 = 完成方法数（`llm_call_logs` 里 `method='QC'` 的留痕）
2. 确认 QC 条目条数 = 承重数字条数、issue_type 五类封闭、fail 条目可见
3. 报告页 QC 裁决（维持/修正）→ `owner_verdict` 回显 → reassemble 重放后裁决仍在（11.4 幂等）
   > ✅ **第 3 条已被 T1 的 `11e-` 提前覆盖**（QC-01 维持 → 重放装配后仍在，留档 `smoke_out.log`）。T5 只需补 1、2 两条，**别重复跑那 12 分钟的装配**。

### T6 · M6 收口（0.5 天）
1. 全量冒烟 11 步 + 12 最终跑一次并留档
2. 六步演示走查（`VITE_USE_MOCK=false`，基准见 `frontend/README.md`「演示全流程走查」）
3. 缺陷日志与本文件状态同步更新

---

## 4. 开工必读（按序）

1. `ARCHITECTURE.md` —— 唯一施工图纸。重点：6.2（配方五层+实现落点）、10（编排）、11.3/11.4（裁决）、12（装配+图表实现落点）、13（契约，已回写）
2. `后端施工交接.md` —— 前端微调引入的契约增量（background / retry / skip / archive_rows / handled）
3. `frontend/src/api/types.ts` —— **契约权威 TS 投影**，后端不得发明字段/枚举
4. `frontend/src/mocks/stateStore.ts` + `handlers.ts` —— mock 行为基准（守卫/进度形状/裁决幂等）
5. `methods/M03/skill.md` + `methods/_shared/` —— 冻结标杆与纪律层；解析对象
6. 本文件 §0（工作方式）、§2（已完成）、§3（待完成）、§7（校验卡）

---

## 5. 当前代码地图（改前先定位）

```
backend/app/
  db.py                    12 表 DDL + 轻迁移（新增列照 init_schema 的 ALTER 模式加）
  registry.py              方法包加载/十条校验 + 【新】轮次表解析 parse_rounds + shared 纪律层
  llm_provider.py          三角色 + 三道防线 + 留痕（未改）
  routers/diagnoses.py     16 端点（含新增 conflicts/qc verdict、qc verdict 回显、L2 守卫）
  services/
    execution.py           分轮引擎 + 配方五层 + 四项校验 + P-2 两分支 + QC 编排 + _finalize
    assembly.py           【新】分域 7 次同构装配 + 代码仲裁 + 后校验
    charts.py             【新】图表数据装配（纯代码）
    qc_context.py         【新】QC 上下文（白名单，与 execution 无公共 import）
    invariants.py         【新】L2 五类不变式
    data_validation.py    L1 校验（未改）
backend/scripts/
  smoke.py                 12 步冒烟（10d 冲突闭环 / 11 真实全链路含失败处置闭环 / 12 error 档）
  m03_regression.py       【新】M03 回归基准
```

**端点现状**：后端 16 个，前端声明 16 个 —— 冒烟步骤 8 的 `[PENDING]` 已清零（对照通过）。

---

## 6. 已知问题与真机观测（下窗口别踩）

1. **M03 R3 超时是真实现象，不是 bug**：R3 轮 prompt = skill 全文 + R1/R2 全部中间表 + 表G，真实模型上约 6 分钟未返回即失败；R3 是单 STEP 轮，包没声明更细切法 → P-2 b 分支 → 方法 failed → 触发失败停顿。**演示时这是亮点（失败可见 + 人肉处置），但你要能解释清楚两分支规则**。
2. **冒烟步骤 11 很慢，轮询预算必须给足**（2026-09-16 实测）：
   | 阶段 | 实测耗时 |
   |---|---|
   | 事务 C 执行（6 方法分轮 + QC） | ~14 分钟（本轮 M03 R3 成功，未触发失败停顿；**另一轮 R3 失败并触发失败停顿，见 §2.3**） |
   | 事务 D 首次装配（7 域同构） | ~12 分钟 |
   | **步骤 11 合计** | **26.6 分钟 / 35.0 分钟**（两次实测，方差 >30%） |
   | 步骤 11e 重放装配 | **12.0 / 12.1 分钟**（两次实测，很稳） |
   | 全量冒烟 1-12 步 | ~45-60 分钟 |
   轮询上限已从 200 次放宽到 **1000 次（~50 分钟）**（40 分钟版本在第二次实测 35 分钟时只剩 5 分钟余量，太危险）；11e 从 60×1s 放宽到 **600×2s（20 分钟）**。两段轮询都有**每分钟心跳打印**——看到心跳就知道是在跑，不是卡死。跑全量请后台跑，别在前台干等。
   **时长归因**：26.6 vs 35.0 分钟的差额主要来自**单个方法的重试**（某轮输出没过四项静态校验 → 三道防线重跑，每轮预算 600s）。两次都是 7/7 全绿，也意味着**方法级清桶（retry 路径）两轮都没验到**——留给 T3 的失败注入（§9）。
   **分层冒烟（省时，T3-T6 必用）**：`python -u -m scripts.smoke --fast`（或 `--steps 1-10,12`）跳过步骤 11（真实管道，占全量 ~90% 时长），**~2 分钟**跑完其余全部回归位（事务 A/B、L1/L2 冲突与修数、error 档、端点对照）。只有改了引擎/装配/QC 才需要跑全量。
3. **后台跑冒烟的坑**：① `Start-Process -RedirectStandardOutput` 会**因日志文件被上一个进程占用而静默失败**（表现为日志不更新、进程没起来）——跑之前先确认没有残留 python 进程，或用新日志文件名；② **必须加 `-u`**（`python -u -m scripts.smoke`），否则 stdout 重定向到文件时是块缓冲，日志滞后 20 分钟以上，中途根本看不到进度（上一窗口就是被这个坑骗了，以为卡死）。
4. **改完代码必须重启 uvicorn**（启动命令未带 `--reload`）；DB 新列在 `init_schema` 里，重启即生效。
5. **占位数据不会产出假结论**（已实证）：六个方法面对"测试值"档案一致输出"不可判 / 未量化+原因"，符合纪律 1。可用于演示"数据纯度决定输出纯度"。
6. **断言失败会产生误导性次生日志**：冒烟断言失败 → 异常穿出 `with TestClient(app)` → lifespan shutdown 触发 `provider.aclose()` → 在途 LLM 调用集体抛 `Cannot send a request, as the client has been closed`，日志里刷成"域装配失败，回退原始四层"。**看到这条先怀疑是不是关服连坐，别当成装配器缺陷**（详见缺陷日志 S24）。
7. **一条诊断从 execute 到 done 约 26 分钟**（真实模型）。演示要么提前跑好，要么讲清"这是 6 方法 × 多轮 × 7 域真实调用的代价"。
8. **冒烟会往列表页堆诊断**：每跑一次新建 3-4 条（SU7 / 新品X1 / 事务B回归专用* / L2error回归专用*）。**已加自动清理（步骤 13）**：冒烟结束时只删**它自己创建**的那几条（含 SU7/新品X1 各一条），不再越跑越脏。若仍有历史累积（如清理逻辑加入前留下的），用一条 `python -c` 按产品名保留最新一条即可；产品档案/固化指纹挂在 `products` 上，删诊断不影响演示数据。
11. **不要在冒烟的实时输出上接 `Select-Object -First N`**：PowerShell 提前关闭管道会把正在跑的 Python 打成 `BrokenPipeError`，冒烟**跑到一半就死**并留下孤儿诊断（特征：`updated_at == created_at`，"建完就没下文"）。要过滤就 `... | Tee-Object smoke_out.log` 或先落文件再看。（2026-09-17 事故：孤儿 `事务B回归专用c9246f` 即由此产生——属于 S24 家族：**测试工具自身制造假状态**。）
9. **断言失败先三问（S24 沉淀的通用纪律，T2-T6 通用）**：①**轮询预算够吗？**（真实 LLM 是分钟级，单诊断 26 分钟量级）②**stdout 加 `-u` 了吗？**（没加就看不到进度，容易以为卡死）③**是不是关服连坐？**（日志出现 `Cannot send a request, as the client has been closed` = `TestClient` 退出触发 `aclose()`，**不是产品缺陷**）。三问确认完，再去怀疑产品代码。
10. **删文件前先 grep 交接文档**：`scripts/_q.py` 曾被当临时脚本删掉，但它在 §7 里是校验工具——清理前 `grep -r "文件名" *.md`。

---

## 7. Owner 校验卡（每个事务交付时，把对应卡片贴给 Owner）

**通用前置**：
```powershell
# 后端（改完代码必须重启；端口 8000，路由裸挂 /diagnoses，vite proxy 剥 /api）
cd e:\Quan_Zhan\产品分析Agent\backend
python -m uvicorn app.main:app --port 8000

# 前端（端口 5173）+ 真实联调：项目根 .env.local 写 VITE_USE_MOCK=false
cd e:\Quan_Zhan\产品分析Agent\frontend
npm run dev

# 冒烟（TestClient，无需起服务；后台跑 + 独立日志，避免文件占用）
# ⚠️ 必须 -u：不加则 stdout 重定向到文件时是块缓冲，日志滞后 20 分钟（缺陷日志 S24）
cd e:\Quan_Zhan\产品分析Agent\backend
Start-Process -NoNewWindow -FilePath python -ArgumentList "-u","-m","scripts.smoke" `
  -RedirectStandardOutput smoke_out.log -RedirectStandardError smoke_err.log
Get-Content smoke_out.log -Tail 30 -Encoding UTF8

# 快速回归（~2 分钟）：跳过步骤 11 的真实管道，跑完其余全部秒级回归位
python -u -m scripts.smoke --fast
```

**查库看执行实况**（冒烟中途查进度很好用）：脚本已就绪于 `backend/scripts/_q.py`（**勿删**——它和 `smoke.py` 一样是校验工具，不是临时文件；内容与下面一致）。

用法：`python scripts/_q.py`（最近 2 条诊断 + 最近 8 条调用留痕）／`python scripts/_q.py dx_xxxxxxxx`（追加该诊断中间表按轮落库明细）。
PowerShell 里直接 `python -c "..."` 会因引号转义炸掉，所以用文件跑；下面代码仅在文件丢失时用于重建：
```python
import sqlite3
c = sqlite3.connect("data/app.db"); c.row_factory = sqlite3.Row
for i in c.execute("SELECT id,status,error_json,progress_json FROM diagnoses "
                   "WHERE status IN ('executing','assembling','done','failed_at(assembling)') "
                   "ORDER BY created_at DESC LIMIT 2"):
    print(i["id"], i["status"], (i["error_json"] or "")[:400]); print((i["progress_json"] or "")[:600])
print([dict(x) for x in c.execute(
    "SELECT method,round,terminal_status FROM llm_call_logs ORDER BY id DESC LIMIT 8")])
```

| 事务 | Owner 看什么 | 通过标准 |
|---|---|---|
| T1 M1 | 报告页 QC 徽标 → 点"维持" → 刷新页面回显"已裁决：维持"；再把诊断 reassemble → 裁决仍在 | verdict 落库 + 幂等 + 重放不询问 |
| T1 M1 | 冒烟 11e：reassemble 后状态回到 done（**D1 回归位，曾卡死 assembling**） | 日志出现"11e 重放装配回到 done" |
| T2 M2 | ready 态点执行 → 被 409 拒（页面弹出冲突清单）、状态仍是 ready；①「拒绝变更」裁决后再执行放行；②「修数」= 回提交区**重新提交该表**（8.3 按表覆盖）→ 冲突消失 → 执行放行 | 两条路都通（冒烟 10d / 10e） |
| T2 M2 | 注意：**L2 只在 execute 时计算**（11.3 设计），所以入档后详情页 `pending_conflicts_n=0`、看不到冲突，第一次点执行被 409 拒才落库可见——不是 bug | 409 面板有冲突清单，之后详情页/列表 stage_hint 才显示 |
| T2 M2（S26→S28） | **error 档被拦必须看得见且能修**：红色阻断卡片（逐条明细 + 行引用）→「手动更改」→ 档案库错误行标红可编辑 → 修正稿提交后重新触发放行 | 卡片可见 + 修数闭环可达（不再是"只有一条 message、没处可改"） |
| T2 M2（S26） | **K80 预建档主线**：首页搜「红米K80」→ 工作台 ready（11 表已入档，跳过采集是 2.2 设计）→ 点执行应能 202 进入分析 | L2 检出 0 条（修前是 2 error + 9 warn 误报） |
| T3 M3 | 执行页方法卡显示 `running(R1/3)` 这类多轮形态；`intermediate_tables` 按 round 落库 | 分轮真的在跑，不是单轮直出 |
| T4 M4 | 报告页七域齐全（含弱适用/不适用占位）、图表区有图、冲突留痕非空 | 域数 = 激活矩阵域数 |
| T5 M5 | 报告页 QC 条目数 = 方法诊断项数；`llm_call_logs` 里 method='QC' 的调用数 = 完成方法数 | per-method 不是单次汇总 |
| T6 M6 | 全量冒烟 12 步无断言失败 + 六步走查 | `smoke_out.log` 覆盖留档 |

---

## 8. 纪律红线（保留，违反=返工）

| 红线 | 内容 |
|---|---|
| **一次一事务** | 见 §0。做完一个停下交 Owner 校验，不等确认不动下一个 |
| T2 零方法知识 | 引擎/装配器/QC 代码不得含任何方法分支；轮次表、切法、超时值都是**数据**（方法包声明） |
| T4 | DB 事务内禁 LLM 调用；写事务纯写毫秒级 |
| T6 显式失败 | 任何失败结构化落库 + 端点暴露；**asyncio 后台任务必须 try/except 落库**（D1 就是反例，已修） |
| P-2 | 编排器代码零超时常量；三类失败三种处置不可混用（网络级重试 2 次 / 预算级拆轮 1 次 / 语义级 0 次） |
| P-3 全 async | 同步 IO 会卡死 2s 轮询 |
| 契约纪律 | 字段/枚举以 `frontend/src/api/types.ts` 为权威投影，不发明；409 体 `{reason, expected_states, current}` |
| 状态机 | status 迁移只经端点守卫；conflict 触发被拒**不迁移状态** |
| 前端不动 | 前端已定稿；除联调发现的后端 bug 外不改前端；若激活新方法包代号需同步 `frontend/src/labels.ts` METHOD_LABELS |

---

## 9. 环境与命令（不变）

**LLM key**（`backend/.env`，启动时校验非空）：`LLM_EXECUTOR_KEY` / `LLM_ARBITER_KEY`（百炼 qwen）/ `LLM_QC_KEY`（DeepSeek，强制异模型）。角色配置 `backend/config/llm.yaml`。

**演示技巧（走查"方法失败停顿"的真机复现）**：临时把 `llm.yaml` 的 `executor.model` 改成不存在的型号 → 方法级 failed（不传染）→ 前端停顿 → 演示 skip（登记降级）或改回型号后 retry（成功推进）。**不要为此写 mock 后门**。
> **省时提示（T3/T4 共用一次注入）**：这一改坏能同时验证两件事——①**方法级清桶**（T1 遗留未验证项：retry 重跑时旧中间表作废重写）②**装配失败不传染**（T4 第 3 条：单域失败回退原始四层 + 登记 `downgraded_methods`）。一次注入验两条，省一轮 26 分钟。
> **演示纪律（冲突闭环，S25③ A 方案落地后；S29 修订提交区策略）**：「手动更改」会生成**整表修正稿**填入提交区（ready 态仅在**有冲突待处理 / error 档待修**时显示提交区），必须**核对后点「提交校验」**才真正入档——演示时别跳过这一步，否则会出现"改了数却没生效"。提交后再触发执行，系统会重跑 L2，问题消失即放行。
> **L2 残留窗口（可解释，非 bug）**：L2 只在 execute 时计算——修数重新提交后、下次触发执行放行之前，详情页/列表仍显示旧冲突或旧 error 卡片是**设计使然**；重新触发后即以新结果刷新。演示时可主动说明："系统只在触发时做一致性检查，避免每次写库全量扫描"。

---

## 10. 验收定义（拆到事务级）

1. T1：冒烟 11 全绿（含 11c2/11e）+ 步骤 12 通过 + D1/D2 回归位绿
2. T2：409 两条路真机走通 + 详情/列表冲突字段真实
3. T3：分轮真机成立 + M03 回归基准跑出命中清单（数值级差异登记缺陷日志）
4. T4：分域装配 + 图表 + 冲突仲裁真机成立，不传染特性演示成功
5. T5：per-method QC + 裁决幂等（含 reassemble 后仍生效）
6. T6：全量冒烟留档 + 六步走查 + 文档/缺陷日志同步

> 冒烟是幂等的：用一次性 uuid 产品承载副作用，测完 DELETE，不污染 SU7 / 新品X1 的演示语义。
