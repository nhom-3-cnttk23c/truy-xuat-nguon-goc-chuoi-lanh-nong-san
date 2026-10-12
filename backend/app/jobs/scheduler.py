"""Hourly maintenance without keeping migration credentials in the web process."""

import asyncio
import logging
import time

from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine

logger = logging.getLogger(__name__)
last_success: float | None = None


def mark_overdue() -> int:
    total = 0
    while True:
        with engine.begin() as connection:
            changed = connection.scalar(
                text("SELECT public.app_mark_overdue_handovers(:hours)"),
                {"hours": settings.HANDOVER_OVERDUE_HOURS},
            )
        total += changed
        if changed < 500:
            return total


async def run_hourly():
    global last_success
    while True:
        try:
            count = await asyncio.to_thread(mark_overdue)
            last_success = time.monotonic()
            logger.info("Overdue maintenance completed: %d marked", count)
        except Exception:
            logger.error("Overdue maintenance failed; retrying next hour")
        await asyncio.sleep(3600)
