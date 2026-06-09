import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import LINE_BOSS_USER_ID
from query_wms import get_low_stock
from push import push_message

logger = logging.getLogger(__name__)


async def daily_stock_alert():
    """每天 08:00 — 低庫存警報；無品項低於安全庫存則不發訊息。"""
    try:
        result = await get_low_stock()
        # 只有真的有低於安全庫存（get_low_stock 以 ⚠️ 標示）才推播
        if "⚠️" in result:
            await push_message(LINE_BOSS_USER_ID, f"🔔 每日庫存警報\n\n{result}")
    except Exception as e:
        logger.error(f"庫存警報失敗：{e}")


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Taipei")
    scheduler.add_job(daily_stock_alert, "cron", hour=8, minute=0, id="daily_stock")
    return scheduler
