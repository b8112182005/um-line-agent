import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import LINE_BOSS_USER_ID
from query_wms import get_low_stock
from query_money import get_monthly_summary
from push import push_message

logger = logging.getLogger(__name__)


async def daily_stock_alert():
    """每天 08:00 — 低庫存警報"""
    try:
        result = await get_low_stock()
        if "⚠️" in result:
            await push_message(LINE_BOSS_USER_ID, f"🔔 每日庫存警報\n\n{result}")
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
        await push_message(LINE_BOSS_USER_ID, f"🔔 週報提醒\n\n{result}")
    except Exception as e:
        logger.error(f"週報推播失敗：{e}")


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Taipei")
    scheduler.add_job(daily_stock_alert, "cron", hour=8, minute=0, id="daily_stock")
    scheduler.add_job(weekly_finance_summary, "cron", day_of_week="mon", hour=8, minute=30, id="weekly_finance")
    return scheduler
