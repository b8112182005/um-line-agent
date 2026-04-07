import logging
import anthropic
from config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是瑀墨助理，用簡短親切的中文回覆老闆的問題。
數字要清楚，重點標出來。不要用 markdown 格式，LINE 不支援。
回覆控制在 500 字以內。如果資料是空的或全部為零，就直接說目前沒有資料。"""


async def humanize(question: str, raw_data: str) -> str:
    """把查詢結果轉成口語化回覆"""
    if not ANTHROPIC_API_KEY:
        return raw_data

    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"老闆問：「{question}」\n\n查詢結果：\n{raw_data}\n\n請用口語化的方式回覆老闆。",
                }
            ],
        )
        return message.content[0].text.strip()
    except Exception as e:
        logger.warning(f"Claude 回覆生成失敗，使用原始資料：{e}")
        return raw_data
