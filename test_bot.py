"""部署前驗證腳本 — push 前跑一次確認核心功能正常

用法：python test_bot.py
"""
import sys
import os

# 確保 import 不會因為缺環境變數而爆
os.environ.setdefault("LINE_CHANNEL_SECRET", "test")
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test")
os.environ.setdefault("LINE_BOSS_USER_ID", "U_test_boss")
os.environ.setdefault("LINE_ENGINEER_USER_ID", "U_test_engineer")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("WMS_API_URL", "http://localhost")
os.environ.setdefault("MONEY_API_URL", "http://localhost")
os.environ.setdefault("API_USERNAME", "test")
os.environ.setdefault("API_PASSWORD", "test")

passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        print(f"  ✓ {name}")
        passed += 1
    else:
        print(f"  ✗ {name}")
        failed += 1


def test_imports():
    """確認所有模組可以 import"""
    print("\n[1] Import 檢查")
    try:
        import main
        check("main.py", True)
    except Exception as e:
        check(f"main.py — {e}", False)
    try:
        import customer
        check("customer.py", True)
    except Exception as e:
        check(f"customer.py — {e}", False)
    try:
        import intent
        check("intent.py", True)
    except Exception as e:
        check(f"intent.py — {e}", False)
    try:
        import chat
        check("chat.py", True)
    except Exception as e:
        check(f"chat.py — {e}", False)
    try:
        import push
        check("push.py", True)
    except Exception as e:
        check(f"push.py — {e}", False)
    try:
        import user_db
        check("user_db.py", True)
    except Exception as e:
        check(f"user_db.py — {e}", False)
    try:
        import scheduler
        check("scheduler.py", True)
    except Exception as e:
        check(f"scheduler.py — {e}", False)


def test_db():
    """確認 DB 初始化 + CRUD 正常"""
    print("\n[2] 資料庫檢查")
    import user_db
    import tempfile, os
    tmp = os.path.join(tempfile.gettempdir(), "test_users.db")
    if os.path.exists(tmp):
        os.remove(tmp)
    user_db.DB_PATH = tmp
    user_db.init_db()
    check("init_db 成功", True)

    # 種子資料：至少各有一位 engineer 與 boss
    roles = {u["role"] for u in user_db.list_all_users()}
    check("種子含 engineer 角色", "engineer" in roles)
    check("種子含 boss 角色", "boss" in roles)

    # 待審 → 通過 流程（用不與種子衝突的測試 ID）
    user_db.add_pending("U_new", "測試用戶")
    check("add_pending", user_db.get_role("U_new") == "pending")

    pending = user_db.get_latest_pending()
    check("get_latest_pending", pending and pending["user_id"] == "U_new")

    user_db.approve_user("U_new")
    check("approve_user", user_db.get_role("U_new") == "approved")

    user_db.set_note("U_new", "油漆師傅")
    approved = {u["user_id"]: u for u in user_db.list_approved()}
    check("set_note + list_approved", approved.get("U_new", {}).get("note") == "油漆師傅")

    found = user_db.find_user_by_name("測試用戶")
    check("find_user_by_name", any(u["user_id"] == "U_new" for u in found))

    user_db.remove_user("U_new")
    check("remove_user", user_db.get_role("U_new") is None)

    # boss/engineer 不可移除（用種子裡實際存在的 boss）
    boss_id = next(u["user_id"] for u in user_db.list_all_users() if u["role"] == "boss")
    user_db.remove_user(boss_id)
    check("boss 不可移除", user_db.get_role(boss_id) == "boss")

    all_users = user_db.list_all_users()
    check("list_all_users", len(all_users) >= 2)

    # 群組待審 → 允許
    user_db.add_pending_group("G_test", "測試群組")
    check("add_pending_group", user_db.get_group_status("G_test") == "pending")

    user_db.approve_group("G_test")
    check("approve_group", user_db.get_group_status("G_test") == "allowed")

    groups = user_db.list_allowed_groups()
    check("list_allowed_groups", any(g["group_id"] == "G_test" for g in groups))


def test_keyword_fallback():
    """確認關鍵字 fallback 正常"""
    print("\n[3] 意圖 Fallback 檢查")
    from intent import _keyword_fallback

    r = _keyword_fallback("缺貨")
    check("「缺貨」→ low_stock", r["intent"] == "low_stock")

    r = _keyword_fallback("虹牌庫存")
    check("「虹牌庫存」→ search_product", r["intent"] == "search_product")

    r = _keyword_fallback("最近進出貨")
    check("「最近進出貨」→ transactions", r["intent"] == "transactions")

    r = _keyword_fallback("3月收支")
    check("「3月收支」→ pnl", r["intent"] == "pnl")

    r = _keyword_fallback("應收應付")
    check("「應收應付」→ dashboard", r["intent"] == "dashboard")


def test_customer_limit():
    """確認客服每日限額"""
    print("\n[4] 客服限額檢查")
    from customer import _check_limit, _remaining, DAILY_LIMIT

    test_user = "U_limit_test"
    check(f"初始剩餘 = {DAILY_LIMIT}", _remaining(test_user) == DAILY_LIMIT)

    for i in range(DAILY_LIMIT):
        _check_limit(test_user)
    check("用完後被擋", not _check_limit(test_user))
    check("剩餘 = 0", _remaining(test_user) == 0)


if __name__ == "__main__":
    print("=" * 40)
    print("瑀墨助理 — 部署前驗證")
    print("=" * 40)

    test_imports()
    test_db()
    test_keyword_fallback()
    test_customer_limit()

    print(f"\n{'=' * 40}")
    print(f"結果：✓ {passed} 通過  ✗ {failed} 失敗")
    print(f"{'=' * 40}")

    sys.exit(1 if failed else 0)
