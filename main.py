import hashlib
import hmac
import base64
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles

from config import LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN, LINE_BOSS_USER_ID, LINE_ENGINEER_USER_ID
from customer import MENU_RESPONSES
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
from user_db import (
    init_db, get_role, add_pending, get_latest_pending, approve_user, block_user,
    list_approved, list_pending, list_all_users, set_note, remove_user, find_user_by_name,
)
from push import push_message, get_display_name, leave_group

import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"

# 塗料/工程部門聯絡資訊（等老闆給 ID 後填入）
_BASE_URL = "https://um-line-agent-production.up.railway.app"
CONTACTS = {
    "塗料部門": {
        "name": "瑀墨塗料部門",
        "person": "葉采鑫 Ken｜Manager 經理",
        "card_image": f"{_BASE_URL}/assets/card_paint.jpg",
        "line_id": "TODO",        # 待填入 LINE ID
        "phone": "0930-691-134",
        "line_link": "TODO",      # 待填入 line://ti/p/~xxx
    },
    "工程部門": {
        "name": "瑀墨工程部門",
        "person": "張紘瑀 Aaron｜Manager 經理",
        "card_image": f"{_BASE_URL}/assets/card_eng.jpg",
        "line_id": "TODO",        # 待填入 LINE ID
        "phone": "0987-852-157",
        "line_link": "TODO",      # 待填入 line://ti/p/~xxx
    },
}

# 統一選單觸發文字（塗料/工程走 Flex 名片，產品/FAQ 走固定文字）
UNIVERSAL_KEYWORDS = {"塗料部門", "工程部門", "產品介紹", "常見問題"}

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
    "「不要」— 拒絕最近一位待審核用戶\n"
    "「備註 暱稱 內容」— 加備註（如：備註 王小明 油漆包商）\n"
    "「移除 暱稱」— 移除用戶\n"
    "「查 暱稱」— 搜尋用戶\n"
    "「全部」— 列出所有用戶（含角色）"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(LINE_BOSS_USER_ID, LINE_ENGINEER_USER_ID)
    scheduler = setup_scheduler()
    scheduler.start()
    logger.info("排程器已啟動")
    yield
    scheduler.shutdown()


app = FastAPI(title="瑀墨助理", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")


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


def _make_contact_flex(contact: dict) -> dict:
    line_id = contact["line_id"]
    phone = contact["phone"]
    line_link = contact["line_link"]
    ready = line_id != "TODO"

    # LINE ID 列：點擊複製
    line_id_value: dict = {
        "type": "text", "text": line_id if ready else "確認中...",
        "size": "sm", "flex": 5, "wrap": True, "color": "#2B5C8A" if ready else "#aaaaaa",
    }
    if ready:
        line_id_value["action"] = {"type": "clipboard", "clipboardText": line_id, "label": "複製"}

    # 電話列：點擊撥打
    phone_ready = phone != "TODO"
    phone_value: dict = {
        "type": "text", "text": phone if phone_ready else "確認中...",
        "size": "sm", "flex": 5, "color": "#2B5C8A" if phone_ready else "#aaaaaa",
    }
    if phone_ready:
        phone_value["action"] = {"type": "uri", "label": "撥打", "uri": f"tel:{phone.replace('-', '')}"}

    bubble: dict = {
        "type": "bubble",
        "size": "mega",
        "hero": {
            "type": "image",
            "url": contact["card_image"],
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
        },
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#1a1a2e",
            "paddingAll": "20px",
            "contents": [
                {"type": "text", "text": contact["name"], "color": "#C9A84C", "size": "xl", "weight": "bold"},
                {"type": "text", "text": contact.get("person", ""), "color": "#cccccc", "size": "sm", "margin": "sm"},
                {"type": "text", "text": "瑀墨塗料有限公司", "color": "#666666", "size": "xs", "margin": "xs"},
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "paddingAll": "20px",
            "contents": [
                {
                    "type": "box", "layout": "horizontal", "spacing": "md",
                    "contents": [
                        {"type": "text", "text": "LINE ID", "color": "#888888", "size": "sm", "flex": 3},
                        line_id_value,
                        *(
                            [{"type": "text", "text": "點擊複製", "color": "#C9A84C", "size": "xs", "flex": 2, "align": "end",
                              "action": {"type": "clipboard", "clipboardText": line_id, "label": "複製"}}]
                            if ready else []
                        ),
                    ],
                },
                {"type": "separator", "color": "#eeeeee"},
                {
                    "type": "box", "layout": "horizontal", "spacing": "md",
                    "contents": [
                        {"type": "text", "text": "電話", "color": "#888888", "size": "sm", "flex": 3},
                        phone_value,
                        *(
                            [{"type": "text", "text": "點擊撥打", "color": "#C9A84C", "size": "xs", "flex": 2, "align": "end",
                              "action": {"type": "uri", "label": "撥打", "uri": f"tel:{phone.replace('-', '')}"}}]
                            if phone_ready else []
                        ),
                    ],
                },
            ],
        },
    }

    if line_link != "TODO":
        bubble["footer"] = {
            "type": "box", "layout": "vertical", "paddingAll": "16px",
            "contents": [
                {
                    "type": "button",
                    "action": {"type": "uri", "label": "開啟 LINE 名片", "uri": line_link},
                    "style": "primary", "color": "#C9A84C", "height": "sm",
                }
            ],
        }

    return {"type": "flex", "altText": f"{contact['name']}聯絡資訊", "contents": bubble}


async def reply_flex(reply_token: str, flex_message: dict):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    body = {
        "replyToken": reply_token,
        "messages": [flex_message],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(LINE_REPLY_URL, json=body, headers=headers)
        if resp.status_code != 200:
            logger.error(f"LINE flex reply 失敗：{resp.status_code} {resp.text}")


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
            note_str = f"｜{u['note']}" if u['note'] else ""
            lines.append(f"  {u['display_name']}{note_str}")
        return "\n".join(lines)

    if text == "待審":
        users = list_pending()
        if not users:
            return "目前沒有待審核的用戶"
        lines = ["⏳ 待審核用戶："]
        for u in users:
            note_str = f"｜{u['note']}" if u['note'] else ""
            lines.append(f"  {u['display_name']}{note_str}")
        return "\n".join(lines)

    # 備註 暱稱 內容
    if text.startswith("備註 "):
        parts = text[3:].strip().split(" ", 1)
        if len(parts) < 2:
            return "格式：備註 暱稱 內容\n例如：備註 王小明 油漆包商"
        name, note = parts[0], parts[1]
        users = find_user_by_name(name)
        if not users:
            return f"找不到暱稱含「{name}」的用戶"
        if len(users) > 1:
            lines = [f"找到 {len(users)} 位，請用更精確的名字："]
            for u in users:
                lines.append(f"  {u['display_name']}（{u['role']}）")
            return "\n".join(lines)
        target = users[0]
        set_note(target["user_id"], note)
        return f"已為 {target['display_name']} 加備註：{note} ✓"

    # 移除 暱稱
    if text.startswith("移除 "):
        name = text[3:].strip()
        if not name:
            return "格式：移除 暱稱\n例如：移除 王小明"
        users = find_user_by_name(name)
        if not users:
            return f"找不到暱稱含「{name}」的用戶"
        if len(users) > 1:
            lines = [f"找到 {len(users)} 位，請用更精確的名字："]
            for u in users:
                lines.append(f"  {u['display_name']}（{u['role']}）")
            return "\n".join(lines)
        target = users[0]
        if remove_user(target["user_id"]):
            return f"已移除 {target['display_name']} ✓"
        return f"無法移除 {target['display_name']}（boss/engineer 不可移除）"

    if text == "全部":
        users = list_all_users()
        if not users:
            return "目前沒有任何用戶"
        role_label = {"engineer": "工程師", "boss": "老闆", "approved": "已開通", "pending": "待審核", "blocked": "已拒絕"}
        lines = [f"📋 全部用戶（{len(users)} 位）："]
        for u in users:
            label = role_label.get(u["role"], u["role"])
            note_str = f"｜{u['note']}" if u['note'] else ""
            lines.append(f"  [{label}] {u['display_name']}{note_str}")
        return "\n".join(lines)

    # 查 暱稱
    if text.startswith("查 "):
        name = text[2:].strip()
        if not name:
            return "格式：查 暱稱"
        users = find_user_by_name(name)
        if not users:
            return f"找不到暱稱含「{name}」的用戶"
        lines = [f"搜尋結果（{len(users)} 位）："]
        for u in users:
            note_str = f"｜{u['note']}" if u['note'] else ""
            lines.append(f"  {u['display_name']}（{u['role']}）{note_str}")
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
        event_type = event.get("type")
        source = event.get("source", {})
        source_type = source.get("type", "")

        # === Bot 被加入群組 → 一律自動退出 ===
        if event_type == "join" and source_type == "group":
            group_id = source.get("groupId", "")
            if group_id:
                logger.info(f"被加入群組，自動退出：{group_id}")
                await leave_group(group_id)
            continue

        # === Bot 被踢出群組 ===
        if event_type == "leave" and source_type == "group":
            group_id = source.get("groupId", "")
            logger.info(f"被移出群組：{group_id}")
            continue

        # === 群組訊息一律忽略 ===
        if source_type == "group":
            continue

        # === 一般訊息（僅限私訊）===
        if event_type != "message":
            continue
        if event["message"].get("type") != "text":
            continue

        text = event["message"]["text"].strip()
        reply_token = event["replyToken"]
        user_id = source.get("userId", "unknown")

        logger.info(f"收到訊息：「{text}」 來自：{user_id}")

        # 統一選單按鈕：所有用戶皆可使用，不受角色限制
        if text in CONTACTS:
            await reply_flex(reply_token, _make_contact_flex(CONTACTS[text]))
            continue
        if text in MENU_RESPONSES and text in ("產品介紹", "常見問題"):
            await reply_line(reply_token, MENU_RESPONSES[text])
            continue

        role = get_role(user_id)

        if role in ("boss", "engineer"):
            # 先檢查是否為管理指令
            admin_response = await handle_boss_admin(text)
            if admin_response:
                await reply_line(reply_token, admin_response)
            else:
                response = await handle_query(text)
                await reply_line(reply_token, response)

        elif role == "approved":
            response = await handle_customer(text, user_id)
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
