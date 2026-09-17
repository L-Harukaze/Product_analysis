"""查库看执行实况（§7 校验卡指定工具，勿删）。

用法：
    cd backend && python scripts/_q.py              # 最近 2 条诊断 + 最近 8 条调用留痕
    cd backend && python scripts/_q.py dx_xxxxxxxx  # 追加：该诊断的中间表落库明细（按方法/轮次）

PowerShell 里直接 `python -c "..."` 会因引号转义炸掉，所以用文件跑。
"""
import json
import sqlite3
import sys

c = sqlite3.connect("data/app.db")
c.row_factory = sqlite3.Row

for i in c.execute(
    "SELECT id,status,error_json,progress_json FROM diagnoses "
    "WHERE status IN ('executing','assembling','done','failed_at(assembling)') "
    "ORDER BY created_at DESC LIMIT 2"
):
    print("=" * 70)
    print(i["id"], i["status"], (i["error_json"] or "")[:400])
    pg = json.loads(i["progress_json"] or "{}")
    for m in pg.get("methods", []):
        print("   ", m["method"], m["phase"], str(m.get("error", ""))[:120])

print("-" * 70)
for x in c.execute(
    "SELECT method,round,terminal_status,created_at FROM llm_call_logs "
    "ORDER BY id DESC LIMIT 8"
):
    print(dict(x))

if len(sys.argv) > 1:
    print("-" * 70)
    for x in c.execute(
        "SELECT method,round,table_name,length(row_json) AS n FROM intermediate_tables "
        "WHERE diagnosis_id=? ORDER BY method,round",
        (sys.argv[1],),
    ):
        print(dict(x))
