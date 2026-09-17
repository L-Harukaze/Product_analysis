"""方法包注册表（ARCHITECTURE 9 章 / T2 / 8.4）。

- 启动时全量加载入内存；运行时校验一律用启动时加载的内存值（8.4）
- method_registry 表 = 启动审计快照，不是事实源（事实源 = methods/ 文件）
- 十条校验（9.2）：任一失败 → 启动失败，T6 不静默
- 零方法知识（T2）：只解析通用结构（目录名/文件/计数/引用闭包），
  不含任何 if method == "M03" 式分支
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import WORKSPACE_ROOT

logger = logging.getLogger("registry")

METHODS_DIR = WORKSPACE_ROOT / "methods"
SHARED_DIR = METHODS_DIR / "_shared"

_DIR_PATTERN = re.compile(r"^M\d{2}$|^S\d+$")
_STEP_PATTERN = re.compile(r"STEP\s?(\d+[a-z]?)", re.IGNORECASE)
_TIME_LIMIT_PATTERN = re.compile(r"time_limit[：:]\s*([0-9.]+)\s*s")
_INHERIT_PATTERN = re.compile(r"《(_shared/[^》]+)》")

# ———— 轮次表解析（6.2：执行形态由方法包第 5 节声明，引擎零方法知识）————
_SECTION5_PATTERN = re.compile(r"^##\s*5\..*?(?=^##\s*6\.|\Z)", re.MULTILINE | re.DOTALL)
_ROUND_CELL_PATTERN = re.compile(r"^R(\d+)\s*(.*)$")
_STEP_RANGE_PATTERN = re.compile(r"STEP\s?(\d+)\s*(?:[-–~]|到)\s*(\d+)", re.IGNORECASE)
_STEP_NUM_PATTERN = re.compile(r"STEP\s?(\d+)", re.IGNORECASE)
_TABLE_TOKEN_PATTERN = re.compile(r"表([A-Z])")
# 散文式轮次声明（无表格的包，如 M02/M06："R1 数据对齐轮（STEP 0-1，表G+表D切片）→ R2 …"）
_ROUND_PROSE_PATTERN = re.compile(r"R(\d+)\s*([^\s（(，,;；]{0,12}?)\s*[（(]([^）)]+)[）)]")

ABSOLUTE_TIME_LIMIT_CAP_S = 3600.0  # 绝对上限（P-2 校验边界，代码级常量而非方法知识）
DEFAULT_TIME_LIMIT_S = 600.0        # P-2：缺失 → 警告 + 缺省 600s（放行但可见）


class RegistryError(RuntimeError):
    """启动失败类错误（9.2：任一校验失败 → 启动失败）。"""


@dataclass
class MethodRound:
    """第 5 节轮次表的一行（6.2 配方任务指令层的数据源）。"""
    round: int
    label: str
    step_from: int | None
    step_to: int | None
    input_tables: list[str]   # 表 ID（A-G）
    outputs: list[str]        # 本轮产出中间表名
    note: str = ""

    @property
    def step_label(self) -> str:
        if self.step_from is None:
            return "全部 STEP"
        if self.step_to is not None and self.step_to != self.step_from:
            return f"STEP {self.step_from}-{self.step_to}"
        return f"STEP {self.step_from}"

    def split_by_steps(self) -> list["MethodRound"] | None:
        """按包声明的 STEP 边界拆成两个子轮（P-2 预算级处置 a 分支的"合法切法"）。

        单 STEP 轮或无 STEP 声明 → 不可拆（返回 None，走 b 分支 failed）。
        """
        if self.step_from is None or self.step_to is None or self.step_to <= self.step_from:
            return None
        mid = (self.step_from + self.step_to) // 2
        return [
            MethodRound(self.round, f"{self.label}·上半", self.step_from, mid,
                        list(self.input_tables), list(self.outputs), self.note),
            MethodRound(self.round, f"{self.label}·下半", mid + 1, self.step_to,
                        list(self.input_tables), list(self.outputs), self.note),
        ]


@dataclass
class MethodPackage:
    method_id: str
    version: str
    path: Path
    skill_md: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    chart: dict[str, Any]
    time_limit_s: float
    rounds: list[MethodRound] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def input_tables(self) -> dict[str, Any]:
        """input.schema.tables：表键（A_config 等）→ 定义。事务 A 数据需求并集的数据源。"""
        return self.input_schema.get("tables", {}) or {}

    @property
    def downgrade_flags(self) -> list[str]:
        """output.schema 的降级 flag 枚举（S4：引擎只认枚举，禁自拟）。"""
        run = (self.output_schema.get("output", {}) or {}).get("run", {}) or {}
        items = (run.get("downgrade_flags", {}) or {}).get("items", {}) or {}
        return list(items.get("enum", []) or [])

    def table_id(self, table_key: str) -> str:
        """表键 → 档案表 ID（A-G）：键首字符，如 A_config → A。"""
        return table_key.split("_", 1)[0]


def parse_rounds(skill_md: str, mid_tables: list[str]) -> list[MethodRound]:
    """skill.md 第 5 节轮次表 → 结构化轮次（6.2 配方任务指令层的数据源）。

    零方法知识：只识别通用记号（R{n} / STEP 范围 / 表X / 产出中间表名），
    解析不到 → 空列表（调用方按单轮直出兜底，T2 形态差异被参数化）。
    """
    sec = _SECTION5_PATTERN.search(skill_md)
    if not sec:
        return []
    text = sec.group(0)

    def _spec(no: int, label: str, body: str, note: str = "") -> MethodRound:
        ranges = _STEP_RANGE_PATTERN.findall(body)
        nums = [int(x) for a, b in ranges for x in (a, b)] or \
               [int(x) for x in _STEP_NUM_PATTERN.findall(body)]
        return MethodRound(
            no, label.strip(),
            min(nums) if nums else None, max(nums) if nums else None,
            sorted({t for t in _TABLE_TOKEN_PATTERN.findall(body)}),
            [t for t in mid_tables if t in body], note,
        )

    # ① 轮次表（M03/M04 形态：markdown 表格，首列 R{n}）
    rounds: list[MethodRound] = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells:
            continue
        m = _ROUND_CELL_PATTERN.match(cells[0])
        if not m:
            continue
        body = " ".join(cells)
        note = "；".join(
            c for c in cells[1:]
            if c and not _STEP_NUM_PATTERN.search(c) and not _TABLE_TOKEN_PATTERN.search(c)
            and not any(t in c for t in mid_tables)
        )
        rounds.append(_spec(int(m.group(1)), m.group(2), body, note))

    # ② 散文式轮次声明（M02/M06 形态：R1 …（STEP x-y，表X…）→ R2 …）
    if not rounds:
        for m in _ROUND_PROSE_PATTERN.finditer(text):
            rounds.append(_spec(int(m.group(1)), m.group(2), m.group(3)))
    return sorted(rounds, key=lambda r: r.round)


class Registry:
    def __init__(self) -> None:
        self.packages: dict[str, MethodPackage] = {}
        self.shared: dict[str, str] = {}  # 6.2 系统纪律层：_shared/discipline.md + contract.md 全文

    def get(self, method_id: str) -> MethodPackage:
        """运行时唯一接口：方法 id → {四件套内容, 版本戳, 预算字段}（9.1）。"""
        pkg = self.packages.get(method_id)
        if pkg is None:
            raise KeyError(f"方法包 {method_id} 未加载")
        return pkg

    # ———— 加载与十条校验 ————

    def load(self, referenced_method_ids: set[str]) -> None:
        """加载全部方法包并执行十条校验。

        referenced_method_ids：路由表引用的方法编号（校验 2 的输入）。
        """
        if not METHODS_DIR.is_dir():
            raise RegistryError(f"methods/ 目录不存在：{METHODS_DIR}")
        # 系统纪律层（6.2）：表述纪律 + 数据契约全文，缺一即启动失败（注入源不在则配方不完整）
        for fname in ("discipline.md", "contract.md"):
            p = SHARED_DIR / fname
            if not p.is_file():
                raise RegistryError(f"校验0 纪律层资产：_shared/{fname} 缺失（6.2 配方系统纪律层注入源）")
            self.shared[fname] = p.read_text(encoding="utf-8")

        packages: dict[str, MethodPackage] = {}
        for d in sorted(METHODS_DIR.iterdir()):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            # 校验 1：编号格式 ∈ {Mxx, S4}
            if not _DIR_PATTERN.match(d.name):
                raise RegistryError(f"校验1 编号格式：目录 {d.name} 不匹配 {{Mxx, S4}}")
            packages[d.name] = self._load_package(d)

        # 校验 2：路由表引用的方法编号必须存在（P1 教训）
        missing = referenced_method_ids - packages.keys()
        if missing:
            raise RegistryError(f"校验2 编号存在性：路由表引用了不存在的方法 {sorted(missing)}")

        self.packages = packages
        self._sync_snapshot()

    def _load_package(self, d: Path) -> MethodPackage:
        mid = d.name
        # 校验 3：四件套完整性
        for fname in ("skill.md", "input.schema.yaml", "output.schema.yaml", "chart.yaml"):
            if not (d / fname).is_file():
                raise RegistryError(f"校验3 四件套完整性：{mid} 缺 {fname}")

        skill_md = (d / "skill.md").read_text(encoding="utf-8")
        input_schema = self._load_yaml(d / "input.schema.yaml", mid)
        output_schema = self._load_yaml(d / "output.schema.yaml", mid)
        chart = self._load_yaml(d / "chart.yaml", mid)

        # 校验 4：六节骨架（skill.md 六节齐全，缺节即不合格）
        section_n = len(re.findall(r"^##\s", skill_md, flags=re.MULTILINE))
        if section_n < 6:
            raise RegistryError(f"校验4 六节骨架：{mid} skill.md 仅 {section_n} 个二级节（需 ≥6）")

        warnings: list[str] = []

        # 校验 5：预算字段（P-2：缺失 → 警告 + 缺省 600s，放行但可见）
        m = _TIME_LIMIT_PATTERN.search(skill_md)
        if m is None:
            warnings.append(f"{mid}: skill.md 未声明 time_limit，缺省 {DEFAULT_TIME_LIMIT_S:.0f}s（P-2）")
            time_limit_s = DEFAULT_TIME_LIMIT_S
        else:
            time_limit_s = float(m.group(1))
            if not (0 < time_limit_s <= ABSOLUTE_TIME_LIMIT_CAP_S):
                raise RegistryError(
                    f"校验5 预算字段：{mid} time_limit={time_limit_s}s 越界（0, {ABSOLUTE_TIME_LIMIT_CAP_S:.0f}]"
                )

        # 校验 6：flag 枚举一致（skill 第 4 节枚举表 ≡ output.schema 的 downgrade_flags 枚举）
        out_flags = self._downgrade_flags(output_schema)
        for flag in out_flags:
            if flag not in skill_md:
                raise RegistryError(f"校验6 flag 枚举一致：{mid} 的 flag {flag} 未在 skill.md 枚举表中出现")

        # 校验 7：consumed_by 完整性（input.schema 每表引用的 STEP ∈ skill 执行流程范围）
        # 归一到主步骤号：子步骤后缀（如 4c）属于主步骤（4）范围——skill 记号可能是
        # "STEP 4" 下挂 "c)" 子项，schema 记号是 STEP4c，语义同源
        skill_steps = {s.rstrip("abcdefghijklmnopqrstuvwxyz") for s in _STEP_PATTERN.findall(skill_md)}
        for tkey, tdef in (input_schema.get("tables", {}) or {}).items():
            for step in (tdef or {}).get("consumed_by", []) or []:
                step_norm = step.replace(" ", "")
                step_num = step_norm[4:] if step_norm.upper().startswith("STEP") else step_norm
                if step_num.rstrip("abcdefghijklmnopqrstuvwxyz") not in skill_steps:
                    raise RegistryError(
                        f"校验7 consumed_by 完整性：{mid} 表 {tkey} 引用 {step}，不在 skill.md 执行流程内"
                    )

        # 校验 8：轮次表完整性（9.2 原文语义：第 5 节轮次表声明的输入表 ⊆ input.schema 定义表）
        # 只解析第 5 节内的"表X"记号——skill 其他章节提及他表（跨方法引用/边界注记）不在此列
        declared_keys = set((input_schema.get("tables", {}) or {}).keys())
        out_mid_tables = set(
            ((output_schema.get("output", {}) or {}).get("intermediate_tables", {}) or {}).keys()
        )
        declared_table_ids = {tk.split("_", 1)[0] for tk in declared_keys}
        sec5 = re.search(r"^##\s*5\..*?(?=^##\s*6\.|\Z)", skill_md, flags=re.MULTILINE | re.DOTALL)
        if sec5:
            for m in re.finditer(r"表([A-G])\b", sec5.group(0)):
                if m.group(1) not in declared_table_ids:
                    raise RegistryError(
                        f"校验8 轮次表完整性：{mid} 第5节轮次表引用未声明的输入表 {m.group(0)}"
                    )

        # 校验 9：图表绑定（引用的中间表存在、模板 ∈ _shared/chart_templates.yaml）
        templates_path = SHARED_DIR / "chart_templates.yaml"
        templates: set[str] = set()
        if templates_path.is_file():
            tpl_yaml = yaml.safe_load(templates_path.read_text(encoding="utf-8")) or {}
            templates = set((tpl_yaml.get("templates", {}) or {}).keys())
        for binding in chart.get("bindings", []) or []:
            # source_table/template 兼容字符串与数组两种声明形态；
            # 模板 ID 以 T- 前缀为命名约定，仅对 T- 引用校验存在性
            # （chart.yaml 允许"表格输出（v0.1）"式占位声明，如 M01 bands：非 T- 不渲染图形）
            srcs = binding.get("source_table")
            srcs = srcs if isinstance(srcs, list) else ([srcs] if srcs else [])
            for s in srcs:
                if s not in out_mid_tables:
                    raise RegistryError(f"校验9 图表绑定：{mid} 绑定的中间表 {s} 不在 output.schema 中")
            tpls = binding.get("template")
            tpls = tpls if isinstance(tpls, list) else ([tpls] if tpls else [])
            for t in tpls:
                if templates and isinstance(t, str) and t.startswith("T-") and t not in templates:
                    raise RegistryError(f"校验9 图表绑定：{mid} 的模板 {t} 不在 _shared/chart_templates.yaml")

        # 校验 10：_shared 继承声明（头部继承声明存在且路径合法）
        for rel in set(_INHERIT_PATTERN.findall(skill_md[:2000])):
            if not (METHODS_DIR / rel).is_file():
                raise RegistryError(f"校验10 继承声明：{mid} 引用的 {rel} 不存在")

        # 轮次表解析（6.2）：解析不到 → 单轮直出兜底 + 警告（轻负载包形态，非缺陷但可见）
        rounds = parse_rounds(skill_md, list(out_mid_tables))
        if not rounds:
            rounds = [MethodRound(1, "单轮直出", None, None,
                                  sorted(declared_table_ids), list(out_mid_tables),
                                  "第 5 节未声明轮次表：按单轮直出执行（protocol.md 轻负载默认形态）")]
            warnings.append(f"{mid}: 第5节未解析到轮次表，按单轮直出执行（6.2 单轮直出包）")

        version = str(input_schema.get("version", "v0"))
        return MethodPackage(
            method_id=mid, version=version, path=d, skill_md=skill_md,
            input_schema=input_schema, output_schema=output_schema, chart=chart,
            time_limit_s=time_limit_s, rounds=rounds, warnings=warnings,
        )

    @staticmethod
    def _downgrade_flags(output_schema: dict[str, Any]) -> list[str]:
        run = (output_schema.get("output", {}) or {}).get("run", {}) or {}
        dg = run.get("downgrade_flags", {}) or {}
        items = dg.get("items", {}) or {}
        return list(items.get("enum", []) or [])

    @staticmethod
    def _load_yaml(path: Path, mid: str) -> dict[str, Any]:
        """YAML 解析失败的显式包装（T6：可读报错，不裸崩）。"""
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            raise RegistryError(f"方法包 {mid} 资产 YAML 解析失败：{path.name}\n{e}") from e

    def _sync_snapshot(self) -> None:
        """8.4：method_registry 快照（启动审计记录），对比刷新 + 告警。"""
        from . import db  # 延迟导入避免循环

        def _sync(conn) -> None:
            rows = {r["method_id"]: r for r in conn.execute("SELECT * FROM method_registry")}
            for mid, pkg in self.packages.items():
                row = rows.get(mid)
                if row is None or row["version"] != pkg.version or row["path"] != str(pkg.path):
                    if row is not None:
                        logger.warning("[registry] 快照与文件不一致，已刷新：%s（8.4）", mid)
                    conn.execute(
                        "INSERT INTO method_registry(method_id, version, path, time_limit_s) "
                        "VALUES (?,?,?,?) ON CONFLICT(method_id) DO UPDATE SET "
                        "version=excluded.version, path=excluded.path, time_limit_s=excluded.time_limit_s, "
                        "loaded_at=datetime('now')",
                        (mid, pkg.version, str(pkg.path), pkg.time_limit_s),
                    )
        db._run_sync(_sync)
        for pkg in self.packages.values():
            for w in pkg.warnings:
                logger.warning("[registry] %s", w)
