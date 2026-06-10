import logging
import httpx
from config import LINE_CHANNEL_ACCESS_TOKEN

logger = logging.getLogger(__name__)

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_PROFILE_URL = "https://api.line.me/v2/bot/profile"


async def push_message(to_user_id: str, text: str):
    """推播文字訊息給指定用戶"""
    if not to_user_id:
        logger.warning("push_message: user_id 為空，跳過")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    body = {
        "to": to_user_id,
        "messages": [{"type": "text", "text": text}],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(LINE_PUSH_URL, json=body, headers=headers)
        if resp.status_code != 200:
            logger.error(f"推播失敗：{resp.status_code} {resp.text}")


async def push_image(to_user_id: str, original_url: str, preview_url: str = ""):
    """推播圖片訊息（originalContentUrl 須為公開 HTTPS、PNG/JPEG）"""
    if not to_user_id or not original_url:
        logger.warning("push_image: 缺 user_id 或圖片 URL，跳過")
        return
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    body = {
        "to": to_user_id,
        "messages": [{
            "type": "image",
            "originalContentUrl": original_url,
            "previewImageUrl": preview_url or original_url,
        }],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(LINE_PUSH_URL, json=body, headers=headers)
        if resp.status_code != 200:
            logger.error(f"圖片推播失敗：{resp.status_code} {resp.text}")


async def push_flex(to_user_id: str, alt_text: str, flex_contents: dict):
    """推播 Flex Message 給指定用戶"""
    if not to_user_id:
        logger.warning("push_flex: user_id 為空，跳過")
        return
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    body = {
        "to": to_user_id,
        "messages": [{"type": "flex", "altText": alt_text, "contents": flex_contents}],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(LINE_PUSH_URL, json=body, headers=headers)
        if resp.status_code != 200:
            logger.error(f"Flex 推播失敗：{resp.status_code} {resp.text}")


async def get_group_name(group_id: str) -> str:
    """透過 LINE API 取得群組名稱"""
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://api.line.me/v2/bot/group/{group_id}/summary", headers=headers)
            if resp.status_code == 200:
                return resp.json().get("groupName", "未知群組")
    except Exception as e:
        logger.warning(f"取得群組名稱失敗：{e}")
    return "未知群組"


async def leave_group(group_id: str):
    """離開群組"""
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"https://api.line.me/v2/bot/group/{group_id}/leave", headers=headers)
            if resp.status_code == 200:
                logger.info(f"已離開群組：{group_id}")
            else:
                logger.warning(f"離開群組失敗：{resp.status_code}")
    except Exception as e:
        logger.error(f"離開群組錯誤：{e}")


async def get_display_name(user_id: str) -> str:
    """透過 LINE API 取得用戶顯示名稱"""
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{LINE_PROFILE_URL}/{user_id}", headers=headers)
            if resp.status_code == 200:
                return resp.json().get("displayName", "未知用戶")
    except Exception as e:
        logger.warning(f"取得用戶名稱失敗：{e}")
    return "未知用戶"
