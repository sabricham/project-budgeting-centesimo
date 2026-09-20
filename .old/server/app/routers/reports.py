"""Report e serie temporali (§2.10, §2.11)."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query

from app import schemas
from app.auth.deps import CurrentUser, DbSession
from app.enums import Metric, TimeRange, TransactionType
from app.services import reports as report_service
from app.services.balances import net_worth

router = APIRouter(prefix="/reports", tags=["reports"])


def _parse_ids(value: str | None) -> list[int] | None:
    if not value:
        return None
    return [int(part) for part in value.split(",") if part.strip()]


@router.get("/net-worth", response_model=schemas.NetWorthOut)
async def get_net_worth(
    user: CurrentUser,
    session: DbSession,
    as_of: dt.date | None = Query(default=None, description="Default: oggi"),
) -> dict:
    """Σ saldi dei conti asset − Σ residui dei conti liability (§2.10)."""
    day = as_of or dt.date.today()
    assets, liabilities, total = await net_worth(session, user.id, as_of=day)
    return {
        "currency": user.base_currency,
        "assets": assets,
        "liabilities": liabilities,
        "net_worth": total,
        "as_of": day,
    }


@router.get("/timeseries", response_model=schemas.TimeseriesOut)
async def get_timeseries(
    user: CurrentUser,
    session: DbSession,
    metric: Metric = Metric.balance,
    range: TimeRange = TimeRange.month,
    account_ids: str | None = Query(
        default=None, description="Lista di id separati da virgola, es. `1,2`"
    ),
) -> dict:
    """Endpoint generico riusato da tutti i widget della dashboard (§2.11)."""
    return await report_service.timeseries(
        session,
        user.id,
        metric=metric,
        time_range=range,
        account_ids=_parse_ids(account_ids),
    )


@router.get("/by-category", response_model=schemas.CategoryBreakdownOut)
async def get_by_category(
    user: CurrentUser,
    session: DbSession,
    type: TransactionType = TransactionType.expense,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    range: TimeRange | None = Query(
        default=None, description="In alternativa a date_from/date_to"
    ),
    account_ids: str | None = None,
) -> dict:
    """Totali per categoria. I trasferimenti non compaiono mai (§2.3)."""
    if date_from is None or date_to is None:
        date_from, date_to, _ = report_service.range_bounds(range or TimeRange.month)
    return await report_service.category_breakdown(
        session,
        user.id,
        tx_type=type,
        date_from=date_from,
        date_to=date_to,
        account_ids=_parse_ids(account_ids),
    )


@router.post("/net-worth/snapshot", response_model=schemas.NetWorthOut)
async def create_snapshot(user: CurrentUser, session: DbSession) -> dict:
    """Forza il salvataggio dello snapshot di oggi (di norma lo fa il job notturno)."""
    snapshot = await report_service.save_net_worth_snapshot(session, user.id)
    return {
        "currency": user.base_currency,
        "assets": snapshot.assets,
        "liabilities": snapshot.liabilities,
        "net_worth": snapshot.net_worth,
        "as_of": snapshot.date,
    }
