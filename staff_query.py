"""內部人員打字即時查詢：解析意圖 → 呼叫 WMS / UMmoney 既有查詢模組。

設計：命中查詢意圖 → 回查詢結果字串；無法判斷(unknown) → 回 None，
交還給 main.py 的 handle_staff（小墨同仁對話）。不在這裡新寫查詢邏輯，
全部重用 query_wms.py / query_money.py。
"""
import logging
from datetime import datetime

from intent import parse_intent
import query_wms
import query_money

logger = logging.getLogger(__name__)


def _parse_month(month_str: str):
    """'YYYY-MM' → (year, month)；解析失敗回本月。"""
    now = datetime.now()
    try:
        y, m = str(month_str).split("-")[:2]
        return int(y), int(m)
    except Exception:
        return now.year, now.month


async def handle_staff_query(text: str):
    """內部人員即時查 WMS/UMmoney。
    回傳查詢結果字串（命中）或 None（無法判斷，交還 AI 對話）。"""
    try:
        result = await parse_intent(text)
    except Exception as e:
        logger.warning(f"意圖解析失敗：{e}")
        return None

    intent = (result or {}).get("intent", "unknown")
    now = datetime.now()

    try:
        if intent == "low_stock":
            return await query_wms.get_low_stock()
        if intent == "search_product":
            keyword = (result.get("keyword") or "").strip()
            if not keyword:
                return None  # 沒抓到品名 → 交還 AI，避免空查
            return await query_wms.get_stock(keyword)
        if intent == "transactions":
            return await query_wms.get_recent_transactions(int(result.get("days", 7) or 7))
        if intent == "orders":
            return await query_wms.get_orders_summary()
        if intent == "pnl":
            y, m = _parse_month(result.get("month", now.strftime("%Y-%m")))
            return await query_money.get_monthly_summary(y, m)
        if intent == "expense_category":
            y, m = _parse_month(result.get("month", now.strftime("%Y-%m")))
            return await query_money.get_expense_by_category(y, m)
        if intent == "expense_detail":
            return await query_money.get_recent_expenses()
        if intent == "dashboard":
            return await query_money.get_ar_ap_status()
    except Exception as e:
        logger.error(f"查詢執行失敗 intent={intent}：{e}")
        return "查詢時系統忙碌，請稍後再試，或直接開後台查看。"

    return None  # unknown
