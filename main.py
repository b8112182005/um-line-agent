import hashlib
import hmac
import base64
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException

from config import LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN
from intent import parse_intent
from chat import humanize
from query_wms import get_stock, get_low_stock, get_recent_transactions, get_orders_summary
from query_money import (
    get_monthly_summary,
    get_expense_by_category,
    get_recent_expenses,
    get_ar_ap_status,
)
from scheduler import setup_scheduler

import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"

HELP_TEXT = (
    "我可以幫你查以下資訊：\n"
    "📦 庫存查詢 —「虹牌庫存」\n"
    "⚠️ 低庫存警報 —「缺貨」\n"
    "📋 進出貨紀錄 —「最近進出貨」\n"
    "📊 月收支摘要 —「3月收支」\n"
    "💸 支出明細 —「最近支出」\n"
    "📈 支出分類 —「3月支出分類」\n"
    "💰 帳款狀態 —「應收應付」"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = setup_scheduler()
    scheduler.start()
    logger.info("排程器已啟動")
    yield
    scheduler.shutdown()


app = FastAPI(title="瑀墨 LINE Agent", lifespan=lifespan)


def verify_signature(body: bytes, signature: str) -> bool:
    if not LINE_CHANNEL_SECRET:
        return True
    if not signature:
        logger.warning("缺少 X-Line-Signature header")
        return False
    mac = hmac.new(LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256)
    expected = base64.b64encode(mac.digest()).decode()
    ok = hmac.compare_digest(expected, signature)
    if not ok:
        logger.warning(f"Signature 驗證失敗")
    return ok


async def reply_line(reply_token: str, text: str):
    if len(text) > 4900:
        text = text[:4900] + "\n...（內容過長已截斷）"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    body = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(LINE_REPLY_URL, json=body, headers=headers)
        if resp.status_code != 200:
            logger.error(f"LINE reply 失敗：{resp.status_code} {resp.text}")


async def handle_query(text: str) -> str:
    """解析意圖 → 查資料 → Claude 口語化回覆"""
    parsed = await parse_intent(text)
    intent = parsed.get("intent", "unknown")
    now = datetime.now()

    logger.info(f"意圖解析結果：{parsed}")

    try:
        raw_data = None

        if intent == "search_product":
            keyword = parsed.get("keyword", "")
            if not keyword:
                return "請告訴我要查哪個品項？例如：「虹牌庫存」"
            raw_data = await get_stock(keyword)

        elif intent == "low_stock":
            raw_data = await get_low_stock()

        elif intent == "transactions":
            days = int(parsed.get("days", 7))
            raw_data = await get_recent_transactions(days)

        elif intent == "orders":
            raw_data = await get_orders_summary()

        elif intent == "pnl":
            month_str = parsed.get("month", now.strftime("%Y-%m"))
            parts = month_str.split("-")
            year, month = int(parts[0]), int(parts[1])
            raw_data = await get_monthly_summary(year, month)

        elif intent == "expense_detail":
            raw_data = await get_recent_expenses()

        elif intent == "expense_category":
            month_str = parsed.get("month", now.strftime("%Y-%m"))
            parts = month_str.split("-")
            year, month = int(parts[0]), int(parts[1])
            raw_data = await get_expense_by_category(year, month)

        elif intent == "dashboard":
            raw_data = await get_ar_ap_status()

        else:
            return HELP_TEXT

        return await humanize(text, raw_data)

    except Exception as e:
        logger.error(f"查詢失敗：{e}", exc_info=True)
        return "系統忙碌中，請稍後再試"


@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    logger.info(f"收到 webhook 請求，body 長度={len(body)}")

    if not verify_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    data = await request.json()
    events = data.get("events", [])

    for event in events:
        if event.get("type") != "message":
            continue
        if event["message"].get("type") != "text":
            continue

        text = event["message"]["text"].strip()
        reply_token = event["replyToken"]
        user_id = event.get("source", {}).get("userId", "unknown")

        logger.info(f"收到訊息：「{text}」 來自：{user_id}")
        response = await handle_query(text)
        logger.info(f"回覆內容：{response[:100]}...")
        await reply_line(reply_token, response)

    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}
