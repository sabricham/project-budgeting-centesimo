from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query

from app.core.deps import DbSession
from app.core.errors import Invalid
from app.modules.auth.deps import CurrentUser
from app.modules.entries.service import totals_by_kind
from app.modules.reports import service
from app.modules.reports.schemas import NetWorthSeriesOut, SummaryOut

router = APIRouter(prefix="/reports", tags=["reports"])

#: Limite di sicurezza: oltre questo un grafico non si legge comunque, e la query
#: diventa inutilmente pesante.
MAX_SPAN_DAYS = 3660


def _check_range(date_from: dt.date, date_to: dt.date) -> None:
    if date_from > date_to:
        raise Invalid("La data iniziale è successiva a quella finale")
    if (date_to - date_from).days > MAX_SPAN_DAYS:
        raise Invalid("Intervallo troppo ampio: massimo 10 anni")


def _accounts(account_id: int | None) -> list[int] | None:
    """`None` significa «considera tutti i conti»."""
    return None if account_id is None else [account_id]


@router.get("/net-worth-series", response_model=NetWorthSeriesOut)
async def net_worth_series(
    user: CurrentUser,
    session: DbSession,
    date_from: dt.date,
    date_to: dt.date,
    account_id: int | None = Query(default=None, description="Vuoto = tutti i conti"),
) -> NetWorthSeriesOut:
    """Andamento del patrimonio nel periodo — il grafico della pagina Recap."""
    _check_range(date_from, date_to)
    data = await service.net_worth_series(
        session, user.id, date_from, date_to, account_ids=_accounts(account_id)
    )
    return NetWorthSeriesOut.model_validate(data)


@router.get("/summary", response_model=SummaryOut)
async def summary(
    user: CurrentUser,
    session: DbSession,
    date_from: dt.date,
    date_to: dt.date,
    account_id: int | None = Query(default=None, description="Vuoto = tutti i conti"),
) -> SummaryOut:
    """Totali del periodo, da mostrare accanto al grafico."""
    _check_range(date_from, date_to)
    account_ids = _accounts(account_id)

    totals = await totals_by_kind(session, user.id, date_from, date_to, account_ids=account_ids)
    series = await service.net_worth_series(
        session, user.id, date_from, date_to, account_ids=account_ids
    )

    return SummaryOut(
        date_from=date_from,
        date_to=date_to,
        income=totals["income"],
        expense=totals["expense"],
        investment=totals["investment"],
        net_change=series["closing_balance"] - series["opening_balance"],
        closing_balance=series["closing_balance"],
    )
