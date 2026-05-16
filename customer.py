import logging
import time
from collections import defaultdict

import anthropic
from config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

# === 每人每日上限 ===
DAILY_LIMIT = 20
_daily_counts: dict[str, dict] = {}  # {user_id: {"date": "2026-04-08", "count": 5}}


def _check_limit(user_id: str) -> bool:
    """檢查是否超過每日上限，回傳 True = 可以繼續"""
    today = time.strftime("%Y-%m-%d")
    if user_id not in _daily_counts or _daily_counts[user_id]["date"] != today:
        _daily_counts[user_id] = {"date": today, "count": 0}
    if _daily_counts[user_id]["count"] >= DAILY_LIMIT:
        return False
    _daily_counts[user_id]["count"] += 1
    return True


def _remaining(user_id: str) -> int:
    today = time.strftime("%Y-%m-%d")
    if user_id not in _daily_counts or _daily_counts[user_id]["date"] != today:
        return DAILY_LIMIT
    return max(0, DAILY_LIMIT - _daily_counts[user_id]["count"])


# === 對話記憶（最近 5 輪）===
MAX_HISTORY = 5
_conversations: dict[str, list[dict]] = defaultdict(list)


def _get_history(user_id: str) -> list[dict]:
    return _conversations[user_id]


def _add_to_history(user_id: str, user_msg: str, assistant_msg: str):
    history = _conversations[user_id]
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": assistant_msg})
    # 只保留最近 5 輪（10 則訊息）
    if len(history) > MAX_HISTORY * 2:
        _conversations[user_id] = history[-(MAX_HISTORY * 2):]


CUSTOMER_SYSTEM_PROMPT = """你是「小墨」，瑀墨助理的客服模式。
語氣：專業但親切，像一個懂塗料的好朋友。用繁體中文回覆。

瑀墨塗料基本資訊：
- 公司：瑀墨塗料有限公司
- 地址：台中市北屯區
- 服務：塗料批發零售、工地配送、退場退料
- 姊妹公司：瑀墨工程（施工服務）

你能做的事：
1. 回答塗料相關問題（水泥漆vs乳膠漆、防水漆選擇、坪數估算、色卡建議）
2. 收集備料需求資訊（品名+數量、工地地址、進退場日期、聯絡人電話）
3. 說明服務流程（諮詢→報價→備料→配送→退場退料）

原則：
- 能回答的直接回答
- 涉及報價、排程、特殊需求，收集完資訊後說「我已經幫您記錄下來，專人會盡快跟您聯繫」
- 不確定的事不要亂講，說「這部分我幫您轉給專人確認」
- 客人問非塗料相關的事，禮貌引導回來
- 不要用 markdown 格式，LINE 不支援
- 回覆控制在 200 字以內，簡潔有力
- 絕對不要說「有問題隨時來找我」、「歡迎繼續聊」、「隨時可以再問」等鼓勵持續對話的話
- 每次對話結束時，若需要後續跟進，引導客人直接聯絡塗料部門（葉采鑫 Ken 0930-691-134）或工程部門（張紘瑀 Aaron 0987-852-157）"""

# 觸發文字 → 固定回覆
MENU_RESPONSES = {
    "產品介紹": (
        "瑀墨塗料主要產品線：\n\n"
        "🎨 室內漆\n"
        "  水泥漆、乳膠漆、壁癌防護漆\n\n"
        "🏗 室外漆\n"
        "  外牆漆、防水漆、彈性防水塗料\n\n"
        "🔧 底漆/特殊漆\n"
        "  批土、底漆、防鏽漆、地坪漆\n\n"
        "合作品牌：虹牌、得利、青葉、南寶等\n\n"
        "想了解特定產品，直接跟我說就好！"
    ),
    "我要備料": (
        "好的！請提供以下資訊，我幫您安排：\n\n"
        "1. 品名與數量（例：虹牌水泥漆 白色 5加侖 x10）\n"
        "2. 工地地址\n"
        "3. 希望送達日期\n"
        "4. 聯絡人姓名與電話\n\n"
        "如果不確定用量，告訴我坪數，我幫您估算！"
    ),
    "工程服務": (
        "瑀墨工程提供專業施工服務：\n\n"
        "🔧 服務項目\n"
        "  室內外油漆、防水工程、壁癌處理、外牆拉皮\n\n"
        "📋 服務流程\n"
        "  現場勘查→報價→排程→施工→驗收\n\n"
        "有施工需求歡迎直接聯繫：\n"
        "張老闆（瑀墨工程）"
    ),
    "常見問題": (
        "常見問題 FAQ：\n\n"
        "Q1: 水泥漆和乳膠漆差在哪？\n"
        "A: 乳膠漆較耐擦洗、色澤持久，水泥漆經濟實惠適合大面積。\n\n"
        "Q2: 一加侖可以刷多少坪？\n"
        "A: 約 4-6 坪（單層），實際依牆面狀況而定。\n\n"
        "Q3: 可以退貨嗎？\n"
        "A: 未開封可退，退場退料服務請提前告知。\n\n"
        "Q4: 有配送服務嗎？\n"
        "A: 有！台中市區免運，其他地區依數量報價。\n\n"
        "Q5: 如何選色？\n"
        "A: 可提供色卡編號，或到店面看實體色卡。"
    ),
    "聯絡方式": (
        "瑀墨塗料有限公司\n\n"
        "📍 地址：台中市北屯區\n"
        "📱 LINE：直接傳訊息給我就好\n"
        "🕐 營業時間：週一至週六 08:00-18:00\n\n"
        "歡迎隨時聯繫！"
    ),
    "服務流程": (
        "瑀墨塗料服務流程：\n\n"
        "1️⃣ 諮詢\n"
        "   告訴我們您的需求（品項、數量、工地位置）\n\n"
        "2️⃣ 報價\n"
        "   專人依需求提供報價單\n\n"
        "3️⃣ 備料\n"
        "   確認訂單後安排備貨\n\n"
        "4️⃣ 配送\n"
        "   依約定時間送達工地\n\n"
        "5️⃣ 退場退料\n"
        "   工程結束可退還未開封材料\n\n"
        "有問題隨時問我！"
    ),
}


async def handle_customer(text: str, user_id: str = "anonymous") -> str:
    """客服模式：觸發文字走固定回覆，其他走 Claude AI 對話（含記憶+限額）"""
    # 觸發文字不計入額度
    if text in MENU_RESPONSES:
        return MENU_RESPONSES[text]

    # 檢查每日上限
    if not _check_limit(user_id):
        return f"不好意思，今日的對話額度已用完（每日 {DAILY_LIMIT} 則），明天再來聊吧！\n\n如有急事請直接聯繫瑀墨塗料。"

    if not ANTHROPIC_API_KEY:
        return "目前客服系統維護中，請稍後再試。"

    try:
        # 組裝對話歷史
        history = _get_history(user_id)
        messages = history + [{"role": "user", "content": text}]

        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=CUSTOMER_SYSTEM_PROMPT,
            messages=messages,
        )
        reply = message.content[0].text.strip()

        # 記入對話歷史
        _add_to_history(user_id, text, reply)

        remaining = _remaining(user_id)
        if remaining <= 5:
            reply += f"\n\n（今日剩餘 {remaining} 則對話額度）"

        return reply
    except Exception as e:
        logger.error(f"客服 AI 回覆失敗：{e}")
        return "不好意思，系統忙碌中，請稍後再試或直接撥打電話聯繫我們。"
