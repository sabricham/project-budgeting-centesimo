"""Scheduler APScheduler dentro il container API (§3.1).

Un servizio separato non serve: i job sono tre, brevi e idempotenti.

    ogni giorno 00:10  genera le occorrenze ricorrenti (§2.7)
    ogni N minuti      aggiorna PriceCache/FxRateCache (§2.8)
    ogni giorno 23:50  salva lo snapshot del patrimonio netto (§2.10)

Con `RUN_SCHEDULER=false` l'API parte senza job (comodo nei test).
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.services.scheduler_jobs import (
    job_generate_recurring,
    job_net_worth_snapshot,
    job_refresh_market_data,
)

log = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> AsyncIOScheduler | None:
    global _scheduler
    if not settings.run_scheduler:
        log.info("scheduler disabilitato (RUN_SCHEDULER=false)")
        return None

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        job_generate_recurring,
        CronTrigger(hour=0, minute=10),
        id="generate_recurring",
        replace_existing=True,
        # se l'API è stata ferma qualche ora, il job recupera comunque
        misfire_grace_time=3600,
        coalesce=True,
    )
    scheduler.add_job(
        job_refresh_market_data,
        IntervalTrigger(minutes=settings.price_refresh_minutes),
        id="refresh_market_data",
        replace_existing=True,
        misfire_grace_time=600,
        coalesce=True,
    )
    scheduler.add_job(
        job_net_worth_snapshot,
        CronTrigger(hour=23, minute=50),
        id="net_worth_snapshot",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    log.info("scheduler avviato con %d job", len(scheduler.get_jobs()))
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def scheduler_status() -> str:
    if not settings.run_scheduler:
        return "disabled"
    return "running" if _scheduler is not None and _scheduler.running else "stopped"
