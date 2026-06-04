import hashlib
import hmac
import base64
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles

from config import LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN, LINE_BOSS_USER_ID, LINE_ENG_BOSS_USER_ID, LINE_ENGINEER_USER_ID
from customer import MENU_RESPONSES, handle_customer, handle_staff, handle_image, handle_audio
from user_db import (
    init_db, get_role, add_pending, set_role,
    list_approved, list_pending, find_user_by_name, get_setting,
)
from push import leave_group

import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"

# 內部人員（boss / engineer）可在「內部同仁模式 ⇄ 客服模式」之間切換
# （以 user_id 記在記憶體，重啟後自動回到內部模式）
_staff_test_mode: set[str] = set()

# 切換指令（內部人員專用）
_CMD_TO_CUSTOMER = ("客服模式", "切換客服", "測試模式", "客服測試")
_CMD_TO_STAFF = ("內部模式", "同仁模式", "切回內部", "結束測試", "切回來", "退出測試")
_CMD_MODE_STATUS = ("目前模式", "現在模式", "我在哪個模式", "現在什麼模式")

# 內部人員審核熟客的「待確認」暫存（重啟清除）
# {內部人員 user_id: {"action": "approve"/"demote", "target": 客人 user_id, "name": 客人名}}
_pending_confirm: dict[str, dict] = {}

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
    yield


app = FastAPI(title="瑀墨助理", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")


# 僅供本機開發在「明確設定」時放行未簽章請求；正式環境一律 fail-closed
_ALLOW_UNSIGNED = os.getenv("ALLOW_UNSIGNED_WEBHOOK") == "1"


def verify_signature(body: bytes, signature: str) -> bool:
    if not LINE_CHANNEL_SECRET:
        # fail-closed：缺 secret 時拒絕，避免有人偽造 webhook 冒充老闆 user_id
        if _ALLOW_UNSIGNED:
            logger.warning("LINE_CHANNEL_SECRET 未設定，但 ALLOW_UNSIGNED_WEBHOOK=1，放行（僅限本機開發）")
            return True
        logger.error("LINE_CHANNEL_SECRET 未設定，拒絕所有 webhook 請求（fail-closed）")
        return False
    if not signature:
        logger.warning("缺少 X-Line-Signature header")
        return False
    mac = hmac.new(LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256)
    expected = base64.b64encode(mac.digest()).decode()
    ok = hmac.compare_digest(expected, signature)
    if not ok:
        logger.warning(f"Signature 驗證失敗")
    return ok


# 事件 timestamp 防重放：拒絕超過此秒數的舊事件（LINE 正常重送在數分鐘內）
_EVENT_MAX_AGE_MS = 10 * 60 * 1000


def _is_replay(event: dict) -> bool:
    ts = event.get("timestamp")
    if not isinstance(ts, (int, float)):
        return False  # 沒有 timestamp 不阻擋，交由簽章把關
    age_ms = datetime.now().timestamp() * 1000 - ts
    return age_ms > _EVENT_MAX_AGE_MS


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


async def get_line_profile(user_id: str) -> str:
    """取用戶顯示名稱，失敗回空字串。"""
    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://api.line.me/v2/bot/profile/{user_id}", headers=headers)
            if resp.status_code == 200:
                return resp.json().get("displayName", "")
    except Exception as e:
        logger.warning(f"取 profile 失敗：{e}")
    return ""


async def _bind_rich_menu(menu_id: str, user_id: str):
    """綁定 Rich Menu 到指定用戶（LINE linkRichMenuIdToUser）。"""
    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.line.me/v2/bot/user/{user_id}/richmenu/{menu_id}", headers=headers
            )
            if resp.status_code != 200:
                logger.warning(f"綁定選單失敗 {user_id[:8]}：{resp.status_code} {resp.text}")
    except Exception as e:
        logger.warning(f"綁定選單例外：{e}")


async def _handle_staff_admin(text: str, user_id: str, reply_token: str) -> bool:
    """內部人員熟客名單管理指令。有處理回 True，否則 False。"""
    # 兩步確認的第二步：回「是/確定」
    if text in ("是", "確定", "對", "是的") and user_id in _pending_confirm:
        pc = _pending_confirm.pop(user_id)
        target, tname = pc["target"], pc["name"]
        if pc["action"] == "approve":
            set_role(target, "approved")
            vip_id = get_setting("vip_menu_id")
            if vip_id:
                await _bind_rich_menu(vip_id, target)
            await reply_line(reply_token, f"✅ 已將「{tname}」設為熟客，已開通線上備料選單。")
        else:
            set_role(target, "pending")
            reg_id = get_setting("regular_menu_id")
            if reg_id:
                await _bind_rich_menu(reg_id, target)
            await reply_line(reply_token, f"✅ 已取消「{tname}」的熟客身分。")
        return True

    # 客戶名單：列出熟客 / 非熟客
    if text in ("客戶名單", "名單"):
        vips = list_approved()
        regs = list_pending()
        lines = ["📋 客戶名單", "", "🌟 熟客（可線上備料）："]
        lines += ([f"　• {u['display_name'] or '(未命名)'}" for u in vips] if vips else ["　（目前沒有熟客）"])
        lines += ["", "👤 非熟客："]
        lines += ([f"　• {u['display_name'] or '(未命名)'}" for u in regs] if regs else ["　（目前沒有非熟客）"])
        lines += ["", "設為熟客請打：「○○○是熟客」"]
        await reply_line(reply_token, "\n".join(lines))
        return True

    # 設為熟客：「○○○是熟客」→ 兩步確認第一步
    if text.endswith("是熟客") and len(text) > 3:
        name = text[:-3].strip()
        matches = [u for u in find_user_by_name(name) if u["role"] != "approved"] if name else []
        if not matches:
            await reply_line(reply_token, f"找不到叫「{name}」的非熟客。可先打「客戶名單」確認名字。")
        elif len(matches) > 1:
            await reply_line(reply_token, "找到多位：" + "、".join(u["display_name"] for u in matches) + "\n請打更完整的名字。")
        else:
            m = matches[0]
            _pending_confirm[user_id] = {"action": "approve", "target": m["user_id"], "name": m["display_name"]}
            await reply_line(reply_token, f"您是指「{m['display_name']}」嗎？\n回「是」或「確定」我就把他設為熟客。")
        return True

    # 取消熟客：「○○○取消熟客」→ 兩步確認第一步
    if text.endswith("取消熟客") and len(text) > 4:
        name = text[:-4].strip()
        matches = [u for u in find_user_by_name(name) if u["role"] == "approved"] if name else []
        if not matches:
            await reply_line(reply_token, f"找不到叫「{name}」的熟客。")
        elif len(matches) > 1:
            await reply_line(reply_token, "找到多位：" + "、".join(u["display_name"] for u in matches) + "\n請打更完整的名字。")
        else:
            m = matches[0]
            _pending_confirm[user_id] = {"action": "demote", "target": m["user_id"], "name": m["display_name"]}
            await reply_line(reply_token, f"您是指「{m['display_name']}」嗎？\n回「是」或「確定」我就取消他的熟客身分。")
        return True

    return False



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
        # 防重放：丟棄過舊的事件（已通過簽章但可能是重送/重放）
        if _is_replay(event):
            logger.warning("丟棄過舊的事件（疑似重放）")
            continue

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

        # === 新客人加好友 → 自動歸非熟客 + 綁非熟客選單，不通知內部人員 ===
        if event_type == "follow":
            uid = source.get("userId", "")
            if uid:
                name = await get_line_profile(uid)
                add_pending(uid, name)
                regular_id = get_setting("regular_menu_id")
                if regular_id:
                    await _bind_rich_menu(regular_id, uid)
                logger.info(f"新好友：{name or uid[:8]}（已歸非熟客）")
            continue

        # === 群組訊息一律忽略 ===
        if source_type == "group":
            continue

        # === 一般訊息（僅限私訊）===
        if event_type != "message":
            continue

        msg_type = event["message"].get("type")
        reply_token = event["replyToken"]
        user_id = source.get("userId", "unknown")

        # 圖片 → Claude Vision 分析
        if msg_type == "image":
            message_id = event["message"]["id"]
            response = await handle_image(message_id, user_id)
            await reply_line(reply_token, response)
            continue

        # 語音 → Whisper 轉文字後走客服流程
        if msg_type == "audio":
            message_id = event["message"]["id"]
            response = await handle_audio(message_id, user_id)
            await reply_line(reply_token, response)
            continue

        # 影片/檔案 → 引導改打字
        if msg_type in ("video", "file"):
            await reply_line(reply_token, "您好，我目前無法處理這類訊息，方便打字說明一下需求嗎？")
            continue

        # 非文字（貼圖等）→ 忽略
        if msg_type != "text":
            continue

        text = event["message"]["text"].strip()


        logger.info(f"收到訊息：「{text}」 來自：{user_id}")

        # 隱藏指令：查自己的 User ID
        if text == "查我ID":
            await reply_line(reply_token, f"你的 LINE User ID：\n{user_id}")
            continue

        # 熟客選單「線上備料」→ 叫貨表建置中（佔位，做好後改為連結）
        if text == "線上備料":
            await reply_line(reply_token, "🛒 線上叫貨表建置中\n\n專屬熟客的線上備料系統正在準備，完成後會在這裡開放！\n目前需要備料，直接告訴小墨品項與數量即可，我會幫您轉達專員。")
            continue

        # 統一選單按鈕：所有用戶皆可使用，不受角色限制
        if text in CONTACTS:
            await reply_flex(reply_token, _make_contact_flex(CONTACTS[text]))
            continue
        if text in MENU_RESPONSES and text in ("產品介紹", "常見問題"):
            await reply_line(reply_token, MENU_RESPONSES[text])
            continue

        role = get_role(user_id)
        is_staff = (
            user_id in (LINE_BOSS_USER_ID, LINE_ENG_BOSS_USER_ID, LINE_ENGINEER_USER_ID)
            or role in ("boss", "engineer")
        )

        # 內部人員（boss / engineer）模式切換：客服模式 ⇄ 內部同仁模式
        if is_staff and text in _CMD_TO_CUSTOMER:
            _staff_test_mode.add(user_id)
            await reply_line(reply_token, "🧪 已切換至【客服模式】\n現在會以一般客人身分與小墨對話。\n輸入「內部模式」可切回內部同仁模式。")
            continue
        if is_staff and text in _CMD_TO_STAFF:
            _staff_test_mode.discard(user_id)
            await reply_line(reply_token, "✅ 已切換回【內部同仁模式】\n輸入「客服模式」可再切換成客人視角。")
            continue
        if is_staff and text in _CMD_MODE_STATUS:
            mode = "客服模式" if user_id in _staff_test_mode else "內部同仁模式"
            await reply_line(reply_token, f"你目前在【{mode}】。\n切換指令：客服模式 / 內部模式")
            continue

        # 內部人員（非客服模式）熟客名單管理：客戶名單／○○是熟客／是·確定
        if is_staff and user_id not in _staff_test_mode:
            if await _handle_staff_admin(text, user_id, reply_token):
                continue

        if is_staff and user_id not in _staff_test_mode:
            response = await handle_staff(text, user_id)
        else:
            response = await handle_customer(text, user_id)
        await reply_line(reply_token, response)

    return {"status": "ok"}


@app.get("/intro")
async def intro():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=_INTRO_HTML)


_INTRO_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>瑀墨 LINE 客服小墨</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Noto Sans TC', 'Microsoft JhengHei', sans-serif; background: #f7f7f5; color: #222; }
header { background: #1a1a2e; color: #fff; padding: 36px 40px 32px; text-align: center; }
header .logo { font-size: 48px; margin-bottom: 10px; }
header h1 { font-size: 26px; font-weight: 700; color: #C9A84C; }
header p  { font-size: 15px; color: #aaa; margin-top: 6px; }
.container { max-width: 860px; margin: 0 auto; padding: 40px 24px 60px; }
.section { margin-bottom: 36px; }
.section-label { font-size: 12px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: #888; margin-bottom: 14px; }
.grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }
@media(max-width:600px){ .grid-3,.grid-2 { grid-template-columns: 1fr 1fr; } }
@media(max-width:400px){ .grid-3,.grid-2 { grid-template-columns: 1fr; } }
.card { background: #fff; border-radius: 14px; padding: 20px 18px; border: 1.5px solid #eee; }
.card .icon { font-size: 30px; margin-bottom: 10px; }
.card h3 { font-size: 15px; font-weight: 700; margin-bottom: 6px; }
.card p  { font-size: 13px; color: #666; line-height: 1.7; }
.card.highlight { border-color: #C9A84C; background: #fffdf5; }
.card.highlight h3 { color: #886600; }
.flow { background: #fff; border-radius: 14px; padding: 24px; border: 1.5px solid #eee; }
.flow-row { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
.flow-row:last-child { margin-bottom: 0; }
.bubble { border-radius: 20px; padding: 8px 16px; font-size: 13px; font-weight: 600; }
.b-green { background: #e8fdf0; color: #1a6030; border: 1.5px solid #06C755; }
.b-blue  { background: #e6f0f8; color: #1a3a5c; border: 1.5px solid #2B5C8A; }
.b-gold  { background: #fff8e0; color: #886600; border: 1.5px solid #C9A84C; }
.b-gray  { background: #f5f5f5; color: #666;    border: 1.5px solid #ddd; }
.arr { color: #bbb; font-size: 18px; flex-shrink: 0; }
.flow-note { font-size: 12px; color: #999; }
footer { text-align: center; font-size: 12px; color: #ccc; padding-bottom: 40px; }
</style>
</head>
<body>
<header>
  <div class="logo">🤖</div>
  <h1>瑀墨 LINE 客服「小墨」</h1>
  <p>24 小時自動接待客人，重要需求立即通知專人</p>
</header>
<div class="container">
  <div class="section">
    <div class="section-label">客人可以做什麼</div>
    <div class="grid-3">
      <div class="card"><div class="icon">💬</div><h3>自由提問</h3><p>問塗料選擇、坪數估算、服務流程，小墨直接回答</p></div>
      <div class="card"><div class="icon">📦</div><h3>備料下單</h3><p>說明品項、地址、日期，小墨收集完整後通知葉經理</p></div>
      <div class="card"><div class="icon">🖼️</div><h3>傳照片詢問</h3><p>傳牆面照片，小墨自動判斷壁癌、剝落等問題並給建議</p></div>
      <div class="card"><div class="icon">💼</div><h3>查看部門名片</h3><p>點選塗料或工程部門，直接看到聯絡資訊與 LINE 名片</p></div>
      <div class="card"><div class="icon">🔧</div><h3>詢問工程服務</h3><p>施工、防水、壁癌處理等需求，自動分流通知 Aaron</p></div>
      <div class="card highlight"><div class="icon">🙋</div><h3>要求轉真人</h3><p>說「找真人」「叫老闆」等，立即推播通知對應經理</p></div>
    </div>
  </div>
  <div class="section">
    <div class="section-label">需求如何分流通知</div>
    <div class="flow">
      <div class="flow-row"><span class="bubble b-green">客人說要備料 / 叫料</span><span class="arr">→</span><span class="bubble b-gold">📲 通知 葉采鑫 Ken（塗料部門）</span></div>
      <div class="flow-row"><span class="bubble b-green">客人問施工 / 工程評估</span><span class="arr">→</span><span class="bubble b-blue">📲 通知 張紘瑀 Aaron（工程部門）</span></div>
      <div class="flow-row"><span class="bubble b-green">先問工程、後來說要自己買料</span><span class="arr">→</span><span class="bubble b-gold">📲 通知 葉采鑫 Ken（以最近訊息為準）</span></div>
      <div class="flow-row"><span class="flow-note">※ 備料需求收齊（含電話）才推播，確保通知內容完整、不重複</span></div>
    </div>
  </div>
  <div class="section">
    <div class="section-label">老闆收到的通知樣式</div>
    <div class="grid-2">
      <div class="card highlight"><div class="icon">🔔</div><h3>客人求助卡（金色）</h3><p>客人說「找真人」「有人嗎」時發送<br><br>包含：客人名稱、最後一句話、近期對話記錄</p></div>
      <div class="card" style="border-color:#2B5C8A;background:#f5f9fd;"><div class="icon">📦</div><h3 style="color:#2B5C8A;">備料需求卡（藍色）</h3><p>備料資訊收集完整後發送<br><br>包含：客人名稱、品項地址日期電話等完整清單</p></div>
    </div>
  </div>
  <div class="section">
    <div class="section-label">熟客記憶</div>
    <div class="flow">
      <div class="flow-row"><span class="bubble b-gray">第一次來 → 照常服務</span><span class="arr">→</span><span class="bubble b-gray">備料記錄存檔</span></div>
      <div class="flow-row"><span class="bubble b-green">下次再來</span><span class="arr">→</span><span class="bubble b-gold">小墨自動帶入「上次您訂的…」讓客人感受到被記住</span></div>
      <div class="flow-row"><span class="flow-note">※ 記錄永久保存，重新開機也不會消失</span></div>
    </div>
  </div>
  <div class="section">
    <div class="section-label">老闆直接問小墨（私訊）</div>
    <div class="grid-3">
      <div class="card"><div class="icon">📊</div><h3>客戶統計</h3><p>輸入「最近需求」或「客戶統計」，看近期備料記錄彙整</p></div>
      <div class="card"><div class="icon">🏠</div><h3>業務問題</h3><p>直接問塗料、報價、流程等，小墨用輕鬆同事語氣回答</p></div>
      <div class="card"><div class="icon">🔍</div><h3>查我ID</h3><p>輸入「查我ID」，取得自己的 LINE User ID</p></div>
    </div>
  </div>
</div>
<footer>瑀墨塗料有限公司 · LINE 客服小墨</footer>
</body>
</html>"""


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}
