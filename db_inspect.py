import sqlite3
import json
from config import WMS_DB_PATH, MONEY_DB_PATH


def inspect(path, name):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    result = {}
    for t in tables:
        cur.execute(f"PRAGMA table_info({t})")
        cols = [{"col": r[1], "type": r[2]} for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        count = cur.fetchone()[0]
        result[t] = {"columns": cols, "row_count": count}
    conn.close()
    return result


if __name__ == "__main__":
    wms = inspect(WMS_DB_PATH, "WMS")
    money = inspect(MONEY_DB_PATH, "UMmoney")
    report = {"wms": wms, "money": money}
    with open("schema_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("=== WMS (paint.db) ===")
    for t, info in wms.items():
        print(f"\n{t} ({info['row_count']} rows):")
        for c in info["columns"]:
            print(f"  {c['col']} ({c['type']})")
    print("\n=== ACCOUNTING (accounting.db) ===")
    for t, info in money.items():
        print(f"\n{t} ({info['row_count']} rows):")
        for c in info["columns"]:
            print(f"  {c['col']} ({c['type']})")
    print(f"\nSchema 已寫入 schema_report.json")
