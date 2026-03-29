from api_client import money_get


async def get_monthly_summary(year: int, month: int) -> str:
    """查指定月份收支摘要（透過 PnL API）"""
    month_str = f"{year}-{month:02d}"
    data = await money_get("/api/reports/pnl", params={"month": month_str})

    revenue = data.get("revenue", 0) or 0
    cost = data.get("cost", 0) or 0
    other_income = data.get("other_income", 0) or 0
    other_expense = data.get("inventory_expense", 0) or 0
    net = data.get("net_profit", 0) or 0
    gross = data.get("gross_profit", 0) or 0

    return (
        f"📊 {year}年{month}月 收支摘要\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 營收：${revenue:,.0f}\n"
        f"💸 成本：${cost:,.0f}\n"
        f"📈 毛利：${gross:,.0f}\n"
        f"📋 其他收入：${other_income:,.0f}\n"
        f"📋 其他支出：${other_expense:,.0f}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💵 淨利：${net:,.0f}"
    )


async def get_expense_by_category(year: int, month: int) -> str:
    """查指定月份支出明細（進項發票 + 其他支出）"""
    month_str = f"{year}-{month:02d}"

    # 進項發票
    inv_data = await money_get("/api/invoices/in", params={"month": month_str})
    invoices = inv_data if isinstance(inv_data, list) else inv_data.get("invoices", inv_data.get("data", []))

    # 其他支出
    exp_data = await money_get("/api/expenses")
    expenses = exp_data if isinstance(exp_data, list) else exp_data.get("expenses", exp_data.get("data", []))
    # 篩選當月
    expenses = [e for e in expenses if str(e.get("expense_date", "")).startswith(month_str)]

    if not invoices and not expenses:
        return f"{year}年{month}月 無支出紀錄"

    lines = [f"📊 {year}年{month}月 支出分類"]

    if invoices:
        # 按 category 分組
        cats = {}
        for inv in invoices:
            cat = inv.get("category", "未分類") or "未分類"
            cats[cat] = cats.get(cat, 0) + (inv.get("total", 0) or 0)
        lines.append("\n【進項發票】")
        for cat, total in sorted(cats.items(), key=lambda x: -x[1]):
            lines.append(f"  • {cat}：${total:,.0f}")

    if expenses:
        cats = {}
        for exp in expenses:
            cat = exp.get("category", "未分類") or "未分類"
            cats[cat] = cats.get(cat, 0) + (exp.get("amount", 0) or 0)
        lines.append("\n【其他支出】")
        for cat, total in sorted(cats.items(), key=lambda x: -x[1]):
            lines.append(f"  • {cat}：${total:,.0f}")

    return "\n".join(lines)


async def get_recent_expenses(days: int = 7) -> str:
    """查最近支出"""
    exp_data = await money_get("/api/expenses")
    expenses = exp_data if isinstance(exp_data, list) else exp_data.get("expenses", exp_data.get("data", []))

    if not expenses:
        return "目前沒有支出紀錄"

    # 取最近的筆數
    expenses.sort(key=lambda x: x.get("expense_date", ""), reverse=True)
    recent = expenses[:15]

    total = sum(e.get("amount", 0) or 0 for e in recent)
    lines = [f"💸 最近支出（共 {len(recent)} 筆，合計 ${total:,.0f}）："]
    for e in recent:
        lines.append(
            f"• {e.get('category', '未分類')} ${e.get('amount', 0):,.0f} — "
            f"{e.get('expense_date', '')} {e.get('description', '')}"
        )
    return "\n".join(lines)


async def get_ar_ap_status() -> str:
    """查應收/應付帳款狀態（透過 dashboard API）"""
    data = await money_get("/api/dashboard")

    ar = data.get("ar_outstanding", 0) or 0
    ap = data.get("ap_outstanding", 0) or 0
    revenue = data.get("monthly_revenue", 0) or 0
    cost = data.get("monthly_cost", 0) or 0
    net = data.get("net_profit", 0) or 0

    lines = [
        f"📊 帳款與本月概況",
        f"━━━━━━━━━━━━━━━",
        f"應收帳款餘額：${ar:,.0f}",
        f"應付帳款餘額：${ap:,.0f}",
        f"━━━━━━━━━━━━━━━",
        f"本月營收：${revenue:,.0f}",
        f"本月成本：${cost:,.0f}",
        f"本月淨利：${net:,.0f}",
    ]

    # 即將到期
    due_soon = data.get("due_soon", [])
    if due_soon:
        lines.append(f"\n⏰ 7 天內到期（{len(due_soon)} 筆）：")
        for d in due_soon[:5]:
            lines.append(f"  • {d.get('name', '')} ${d.get('balance', 0):,.0f} — 到期 {d.get('due_date', '')}")

    return "\n".join(lines)
