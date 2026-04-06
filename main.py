import hashlib
import hmac
import base64
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException

from config import LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN, LINE_BOSS_USER_ID
from intent import parse_intent
from chat import humanize
from customer import handle_customer
from query_wms import get_stock, get_low_stock, get_recent_transactions, get_orders_summary
from query_money import (
    get_monthly_summary,
    get_expense_by_category,
    get_recent_expenses,
    get_ar_ap_status,
)
from scheduler import setup_scheduler
from user_db import init_db, get_role, add_pending, get_latest_pending, approve_user, block_user, list_approved, list_pending
from push import push_message, get_display_name

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
    "💰 帳款狀態 —「應收應付」\n"
    "\n👥 白名單管理：\n"
    "「名單」— 查看已開通用戶\n"
    "「待審」— 查看待審核用戶\n"
    "「通過」— 開通最近一位待審核用戶\n"
    "「不要」— 拒絕最近一位待審核用戶"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(LINE_BOSS_USER_ID)
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


async def handle_boss_admin(text: str) -> str | None:
    """處理老闆的白名單管理指令，非管理指令回傳 None"""
    if text == "通過":
        pending = get_latest_pending()
        if not pending:
            return "目前沒有待審核的用戶"
        approve_user(pending["user_id"])
        # 通知被開通的用戶
        await push_message(
            pending["user_id"],
            "你好～已開通客服權限，有什麼可以幫你的嗎？😊"
        )
        return f"已開通 {pending['display_name']} 的客服權限 ✓"

    if text == "不要":
        pending = get_latest_pending()
        if not pending:
            return "目前沒有待審核的用戶"
        block_user(pending["user_id"])
        return f"已拒絕 {pending['display_name']} ✓"

    if text == "名單":
        users = list_approved()
        if not users:
            return "目前沒有已開通的用戶"
        lines = ["👥 已開通用戶："]
        for u in users:
            lines.append(f"  {u['display_name']}")
        return "\n".join(lines)

    if text == "待審":
        users = list_pending()
        if not users:
            return "目前沒有待審核的用戶"
        lines = ["⏳ 待審核用戶："]
        for u in users:
            lines.append(f"  {u['display_name']}")
        return "\n".join(lines)

    return None


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


async def handle_unknown_user(user_id: str, reply_token: str):
    """處理未知用戶：建立 pending、通知老闆、回覆用戶"""
    display_name = await get_display_name(user_id)
    add_pending(user_id, display_name)

    # 回覆用戶
    await reply_line(reply_token, "你好～目前瑀墨助理僅限受邀用戶使用，已通知負責人，請稍候。")

    # 推播通知老闆
    await push_message(
        LINE_BOSS_USER_ID,
        f"有人想使用客服：\n  暱稱：{display_name}\n\n回覆『通過』就開通"
    )


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

        role = get_role(user_id)

        if role == "boss":
            # 先檢查是否為管理指令
            admin_response = await handle_boss_admin(text)
            if admin_response:
                await reply_line(reply_token, admin_response)
            else:
                response = await handle_query(text)
                await reply_line(reply_token, response)

        elif role == "approved":
            response = await handle_customer(text)
            await reply_line(reply_token, response)

        elif role == "pending":
            await reply_line(reply_token, "正在等老闆審核中，請稍候～")

        elif role == "blocked":
            await reply_line(reply_token, "目前無法使用此服務，如有需要請直接聯繫瑀墨塗料。")

        else:
            # 全新用戶
            await handle_unknown_user(user_id, reply_token)

    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}
