import json
import re
import logging
from datetime import datetime

import anthropic

from config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是瑀墨塗料的 LINE 助理。根據用戶的訊息，判斷他想查什麼。
只回傳 JSON，不要回傳其他內容。
可用的意圖：

{"intent": "low_stock"} — 查低庫存
{"intent": "search_product", "keyword": "..."} — 查某商品庫存
{"intent": "transactions", "days": 7} — 查進出貨紀錄（預設7天）
{"intent": "orders"} — 查訂單摘要
{"intent": "pnl", "month": "YYYY-MM"} — 查月收支（沒指定就用當月）
{"intent": "expense_category", "month": "YYYY-MM"} — 支出分類
{"intent": "expense_detail"} — 支���明細
{"intent": "dashboard"} — 帳款狀態總覽
{"intent": "unknown"} — 無法判斷

今天是 {today}。

範例：
「這個月花了多少」→ {{"intent": "pnl", "month": "{current_month}"}}
「紅色底漆還有嗎」→ {{"intent": "search_product", "keyword": "���色底漆"}}
「上週出了什麼貨」→ {{"intent": "transactions", "days": 7}}
「缺什麼貨」→ {{"intent": "low_stock"}}
「3月支出分類」→ {{"intent": "expense_category", "month": "{current_year}-03"}}"""


async def parse_intent(text: str) -> dict:
    """用 Claude API 解析意圖，失敗時 fallback 到關鍵字"""
    try:
        return await _claude_parse(text)
    except Exception as e:
        logger.warning(f"Claude 意���解析失敗，降級到關鍵字：{e}")
        return _keyword_fallback(text)


async def _claude_parse(text: str) -> dict:
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY 未設定")

    now = datetime.now()
    prompt = SYSTEM_PROMPT.format(
        today=now.strftime("%Y-%m-%d"),
        current_month=now.strftime("%Y-%m"),
        current_year=now.year,
    )

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=prompt,
        messages=[{"role": "user", "content": text}],
    )
    content = message.content[0].text.strip()
    # 嘗試從回應中提取 JSON
    if not content.startswith("{"):
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            content = match.group()
    return json.loads(content)


def _keyword_fallback(text: str) -> dict:
    """關鍵字���對 fallback"""
    now = datetime.now()

    # 月份偵測
    m = re.search(r"(\d{1,2})\s*月", text)
    month = int(m.group(1)) if m else None
    y = re.search(r"(\d{4})\s*年", text)
    year = int(y.group(1)) if y else now.year

    # 天數偵測
    d = re.search(r"(\d+)\s*天", text)
    days = int(d.group(1)) if d else 7

    month_str = f"{year}-{(month or now.month):02d}"

    if any(k in text for k in ["低庫存", "缺貨", "不��", "安全庫存", "補貨"]):
        return {"intent": "low_stock"}
    elif any(k in text for k in ["庫存", "存量", "還有多少", "還有嗎"]):
        item = re.sub(r"(庫存|存量|還有多少|還有嗎|查|看|幫我|一下|的|？|\?)", "", text).strip()
        return {"intent": "search_product", "keyword": item or ""}
    elif any(k in text for k in ["進出貨", "進貨", "出貨", "入庫", "出庫"]):
        return {"intent": "transactions", "days": days}
    elif any(k in text for k in ["訂單"]):
        return {"intent": "orders"}
    elif any(k in text for k in ["支出分類", "分類支出", "花在哪"]):
        return {"intent": "expense_category", "month": month_str}
    elif any(k in text for k in ["支出", "花費", "開銷"]):
        if month:
            return {"intent": "expense_category", "month": month_str}
        return {"intent": "expense_detail"}
    elif any(k in text for k in ["收支", "損益", "營收", "月報", "花了多少"]):
        return {"intent": "pnl", "month": month_str}
    elif any(k in text for k in ["應收", "應付", "帳款"]):
        return {"intent": "dashboard"}
    return {"intent": "unknown"}
