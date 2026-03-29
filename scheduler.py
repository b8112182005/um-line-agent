import logging
from datetime import datetime

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import LINE_CHANNEL_ACCESS_TOKEN, LINE_BOSS_USER_ID
from query_wms import get_low_stock
from query_money import get_monthly_summary

logger = logging.getLogger(__name__)

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


async def _push_message(text: str):
    """推播訊息給老闆"""
    if not LINE_BOSS_USER_ID or LINE_BOSS_USER_ID == "請填入":
        logger.warning("LINE_BOSS_USER_ID 未設定，跳過推播")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    body = {
        "to": LINE_BOSS_USER_ID,
        "messages": [{"type": "text", "text": text}],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(LINE_PUSH_URL, json=body, headers=headers)
        if resp.status_code != 200:
            logger.error(f"推播失敗：{resp.status_code} {resp.text}")


async def daily_stock_alert():
    """每天 08:00 — 低庫存警報"""
    try:
        result = await get_low_stock()
        if "⚠️" in result:
            await _push_message(f"🔔 每日庫存警報\n\n{result}")
    except Exception as e:
        logger.error(f"庫存警報失敗：{e}")


async def weekly_finance_summary():
    """每週一 08:30 — 上月收支摘要"""
    try:
        now = datetime.now()
        if now.month == 1:
            year, month = now.year - 1, 12
        else:
            year, month = now.year, now.month - 1
        result = await get_monthly_summary(year, month)
        await _push_message(f"🔔 週報提醒\n\n{result}")
    except Exception as e:
        logger.error(f"週報推播失敗：{e}")


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Taipei")
    scheduler.add_job(daily_stock_alert, "cron", hour=8, minute=0, id="daily_stock")
    scheduler.add_job(weekly_finance_summary, "cron", day_of_week="mon", hour=8, minute=30, id="weekly_finance")
    return scheduler
