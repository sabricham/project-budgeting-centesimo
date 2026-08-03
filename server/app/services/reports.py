"""Aggregazioni per widget e pagina Report (§2.11).

Un solo endpoint generico (`/reports/timeseries`) invece di uno per widget: aggiungere
un widget nel client non deve richiedere di toccare il backend, finché riusa le metriche
esistenti.

Granularità per range, come da §2.11:

    day    -> un punto (il giorno stesso)
    week   -> un punto per giorno, da lunedì
    month  -> un punto per giorno del mese corrente
    year   -> un punto per mese dell'anno corrente
"""

from __future__ import annotations

import calendar
import datetime as dt
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ASSET_ACCOUNT_TYPES, Metric, TimeRange, TransactionStatus, TransactionType
from app.models import (
    Account,
    Category,
    NetWorthSnapshot,
    StockTransaction,
    Transaction,
    Transfer,
    User,
)
from app.services.balances import ZERO, cash_balances, net_worth, q2


def range_bounds(
    time_range: TimeRange, today: dt.date | None = None
) -> tuple[dt.date, dt.date, str]:
    """(date_from, date_to, granularità) per il range richiesto."""
    today = today or dt.date.today()
    if time_range is TimeRange.day:
        return today, today, "day"
    if time_range is TimeRange.week:
        monday = today - dt.timedelta(days=today.weekday())
        return monday, monday + dt.timedelta(days=6), "day"
    if time_range is TimeRange.month:
        first = today.replace(day=1)
        last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
        return first, last, "day"
    first = dt.date(today.year, 1, 1)
    return first, dt.date(today.year, 12, 31), "month"


def buckets(date_from: dt.date, date_to: dt.date, granularity: str) -> list[dt.date]:
    out: list[dt.date] = []
    if granularity == "day":
        day = date_from
        while day <= date_to:
            out.append(day)
            day += dt.timedelta(days=1)
        return out

    year, month = date_from.year, date_from.month
    while dt.date(year, month, 1) <= date_to:
        out.append(dt.date(year, month, 1))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return out


def bucket_end(bucket: dt.date, granularity: str) -> dt.date:
    if granularity == "day":
        return bucket
    return bucket.replace(day=calendar.monthrange(bucket.year, bucket.month)[1])


async def _user_currency(session: AsyncSession, user_id: int) -> str:
    return await session.scalar(select(User.base_currency).where(User.id == user_id)) or "EUR"


async def _resolve_accounts(
    session: AsyncSession, user_id: int, account_ids: list[int] | None
) -> list[int]:
    stmt = select(Account.id).where(
        Account.user_id == user_id, Account.type.in_(ASSET_ACCOUNT_TYPES)
    )
    if account_ids:
        stmt = stmt.where(Account.id.in_(account_ids))
    return [row[0] for row in await session.execute(stmt)]


async def _daily_flow(
    session: AsyncSession,
    user_id: int,
    account_ids: list[int],
    date_from: dt.date,
    date_to: dt.date,
    *,
    tx_type: TransactionType | None = None,
    include_transfers: bool = True,
) -> dict[dt.date, Decimal]:
    """Variazione di cassa giorno per giorno.

    Con `tx_type` restituisce solo le entrate o solo le uscite (valori positivi) e
    ignora i trasferimenti: un trasferimento non è né spesa né entrata (§2.3).
    """
    flows: dict[dt.date, Decimal] = {}

    tx_stmt = (
        select(Transaction.date, Transaction.type, func.coalesce(func.sum(Transaction.amount), 0))
        .where(
            Transaction.user_id == user_id,
            Transaction.account_id.in_(account_ids),
            Transaction.deleted_at.is_(None),
            Transaction.status == TransactionStatus.confirmed.value,
            Transaction.date >= date_from,
            Transaction.date <= date_to,
        )
        .group_by(Transaction.date, Transaction.type)
    )
    if tx_type is not None:
        tx_stmt = tx_stmt.where(Transaction.type == tx_type.value)

    for day, row_type, total in await session.execute(tx_stmt):
        value = Decimal(total)
        if tx_type is None and row_type == TransactionType.expense.value:
            value = -value
        flows[day] = flows.get(day, ZERO) + value

    if tx_type is not None:
        return flows

    if include_transfers:
        for column, sign in ((Transfer.to_account_id, 1), (Transfer.from_account_id, -1)):
            stmt = (
                select(Transfer.date, func.coalesce(func.sum(Transfer.amount), 0))
                .where(
                    Transfer.user_id == user_id,
                    column.in_(account_ids),
                    Transfer.deleted_at.is_(None),
                    Transfer.date >= date_from,
                    Transfer.date <= date_to,
                )
                .group_by(Transfer.date)
            )
            for day, total in await session.execute(stmt):
                flows[day] = flows.get(day, ZERO) + Decimal(total) * sign

    stock_stmt = (
        select(StockTransaction.date, func.coalesce(func.sum(StockTransaction.cash_delta), 0))
        .where(
            StockTransaction.user_id == user_id,
            StockTransaction.account_id.in_(account_ids),
            StockTransaction.date >= date_from,
            StockTransaction.date <= date_to,
        )
        .group_by(StockTransaction.date)
    )
    for day, total in await session.execute(stock_stmt):
        flows[day] = flows.get(day, ZERO) + Decimal(total)

    return flows


async def timeseries(
    session: AsyncSession,
    user_id: int,
    *,
    metric: Metric,
    time_range: TimeRange,
    account_ids: list[int] | None = None,
    today: dt.date | None = None,
) -> dict:
    date_from, date_to, granularity = range_bounds(time_range, today)
    points: list[dict] = []

    if metric is Metric.net_worth:
        points = await _net_worth_series(session, user_id, date_from, date_to, granularity)
    else:
        ids = await _resolve_accounts(session, user_id, account_ids)
        if not ids:
            points = [{"bucket": b, "value": ZERO} for b in buckets(date_from, date_to, granularity)]
        elif metric is Metric.balance:
            opening = sum(
                (
                    await cash_balances(
                        session, user_id, account_ids=ids, as_of=date_from - dt.timedelta(days=1)
                    )
                ).values(),
                ZERO,
            )
            flows = await _daily_flow(session, user_id, ids, date_from, date_to)
            running = Decimal(opening)
            for bucket in buckets(date_from, date_to, granularity):
                end = bucket_end(bucket, granularity)
                day = bucket
                while day <= end:
                    running += flows.get(day, ZERO)
                    day += dt.timedelta(days=1)
                points.append({"bucket": bucket, "value": q2(running)})
        else:
            tx_type = (
                TransactionType.expense if metric is Metric.spending else TransactionType.income
            )
            flows = await _daily_flow(
                session, user_id, ids, date_from, date_to, tx_type=tx_type, include_transfers=False
            )
            for bucket in buckets(date_from, date_to, granularity):
                end = bucket_end(bucket, granularity)
                total = ZERO
                day = bucket
                while day <= end:
                    total += flows.get(day, ZERO)
                    day += dt.timedelta(days=1)
                points.append({"bucket": bucket, "value": q2(total)})

    return {
        "metric": metric,
        "range": time_range,
        "currency": await _user_currency(session, user_id),
        "date_from": date_from,
        "date_to": date_to,
        "points": points,
    }


async def _net_worth_series(
    session: AsyncSession,
    user_id: int,
    date_from: dt.date,
    date_to: dt.date,
    granularity: str,
) -> list[dict]:
    """Serie del patrimonio netto.

    Usa gli snapshot giornalieri quando esistono (sono l'unico dato storicamente fedele:
    dipendono dai prezzi di mercato e dagli snapshot dei debiti di quel giorno). Per i
    bucket senza snapshot ricalcola dai movimenti, che è comunque corretto per la parte
    liquida e approssima le posizioni ai prezzi correnti.
    """
    rows = await session.execute(
        select(NetWorthSnapshot.date, NetWorthSnapshot.net_worth)
        .where(
            NetWorthSnapshot.user_id == user_id,
            NetWorthSnapshot.date >= date_from - dt.timedelta(days=400),
            NetWorthSnapshot.date <= date_to,
        )
        .order_by(NetWorthSnapshot.date)
    )
    snapshots = list(rows)
    today = dt.date.today()

    points: list[dict] = []
    for bucket in buckets(date_from, date_to, granularity):
        end = min(bucket_end(bucket, granularity), today)
        if end < bucket and granularity == "day":
            end = bucket
        latest = [value for day, value in snapshots if day <= end]
        if latest:
            points.append({"bucket": bucket, "value": q2(latest[-1])})
        elif bucket <= today:
            _, _, value = await net_worth(session, user_id, as_of=end)
            points.append({"bucket": bucket, "value": value})
        else:
            points.append({"bucket": bucket, "value": ZERO})
    return points


async def category_breakdown(
    session: AsyncSession,
    user_id: int,
    *,
    tx_type: TransactionType,
    date_from: dt.date,
    date_to: dt.date,
    account_ids: list[int] | None = None,
) -> dict:
    """Totali per categoria in un periodo — i trasferimenti non compaiono mai (§2.3)."""
    stmt = (
        select(
            Transaction.category_id,
            Category.name,
            Category.parent_category_id,
            func.coalesce(func.sum(Transaction.amount), 0),
        )
        .join(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None),
            Transaction.status == TransactionStatus.confirmed.value,
            Transaction.type == tx_type.value,
            Transaction.date >= date_from,
            Transaction.date <= date_to,
        )
        .group_by(Transaction.category_id, Category.name, Category.parent_category_id)
        .order_by(func.sum(Transaction.amount).desc())
    )
    if account_ids:
        stmt = stmt.where(Transaction.account_id.in_(account_ids))

    rows = list(await session.execute(stmt))
    total = q2(sum((Decimal(r[3]) for r in rows), ZERO))

    items = [
        {
            "category_id": category_id,
            "category_name": name,
            "parent_category_id": parent_id,
            "total": q2(amount),
            "share": float(Decimal(amount) / total) if total else 0.0,
        }
        for category_id, name, parent_id, amount in rows
    ]
    return {
        "type": tx_type,
        "date_from": date_from,
        "date_to": date_to,
        "currency": await _user_currency(session, user_id),
        "total": total,
        "items": items,
    }


async def save_net_worth_snapshot(
    session: AsyncSession, user_id: int, *, day: dt.date | None = None
) -> NetWorthSnapshot:
    """Salva (o aggiorna) lo snapshot del giorno — chiamata dal job schedulato (§2.10)."""
    day = day or dt.date.today()
    assets, liabilities, total = await net_worth(session, user_id)

    existing = await session.scalar(
        select(NetWorthSnapshot).where(
            NetWorthSnapshot.user_id == user_id, NetWorthSnapshot.date == day
        )
    )
    if existing is None:
        existing = NetWorthSnapshot(user_id=user_id, date=day, assets=ZERO, liabilities=ZERO, net_worth=ZERO)
        session.add(existing)

    existing.assets = assets
    existing.liabilities = liabilities
    existing.net_worth = total
    await session.commit()
    return existing
