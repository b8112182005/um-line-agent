import hashlib
import hmac
import base64
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles

from config import LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN, LINE_BOSS_USER_ID, LINE_ENG_BOSS_USER_ID, LINE_ENGINEER_USER_ID
from customer import MENU_RESPONSES, handle_customer, handle_staff
from scheduler import setup_scheduler
from user_db import init_db
from push import leave_group

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
        "line_id": "kenya123456789",
        "phone": "0930-691-134",
        "line_link": "line://ti/p/~kenya123456789",
    },
    "工程部門": {
        "name": "瑀墨工程部門",
        "person": "張紘瑀 Aaron｜Manager 經理",
        "card_image": f"{_BASE_URL}/assets/card_eng.jpg",
        "line_id": "0987852157",
        "phone": "0987-852-157",
        "line_link": "line://ti/p/~0987852157",
    },
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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

        # 隱藏指令：查自己的 User ID
        if text == "查我ID":
            await reply_line(reply_token, f"你的 LINE User ID：\n{user_id}")
            continue

        # 統一選單按鈕：所有用戶皆可使用，不受角色限制
        if text in CONTACTS:
            await reply_flex(reply_token, _make_contact_flex(CONTACTS[text]))
            continue
        if text in MENU_RESPONSES and text in ("產品介紹", "常見問題"):
            await reply_line(reply_token, MENU_RESPONSES[text])
            continue

        if user_id in (LINE_BOSS_USER_ID, LINE_ENG_BOSS_USER_ID, LINE_ENGINEER_USER_ID):
            response = await handle_staff(text, user_id)
        else:
            response = await handle_customer(text, user_id)
        await reply_line(reply_token, response)

    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}
