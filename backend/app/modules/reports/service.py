"""Aggregazioni per la pagina Recap.

Scelta architetturale: **il backend non conosce i periodi**. Non esiste un enum
`mese | settimana | anno`: il frontend calcola `date_from` e `date_to` e li manda.
Qui si ricevono due date e basta. Aggiungere un periodo nuovo all'interfaccia (per dire
«ultimi 90 giorni») non richiede nessuna modifica al server.

L'unica cosa che il server deduce è la **granularità** dei punti del grafico, perché
dipende solo dall'ampiezza dell'intervallo e non dal significato che l'utente gli dà.
"""

from __future__ import annotations

import calendar
import datetime as dt
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.entries.service import ZERO, balances_by_account, daily_deltas, q2

DAY = "day"
WEEK = "week"
MONTH = "month"


def pick_granularity(date_from: dt.date, date_to: dt.date) -> str:
    """Un punto al giorno fino a ~2 mesi, poi settimanale, poi mensile.

    Le soglie servono a tenere il grafico leggibile: 365 punti giornalieri su un anno
    sono illeggibili su uno schermo, 12 punti mensili si leggono.
    """
    span = (date_to - date_from).days
    if span <= 62:
        return DAY
    if span <= 400:
        return WEEK
    return MONTH


def buckets(date_from: dt.date, date_to: dt.date, granularity: str) -> list[dt.date]:
    """Date di **fine** di ogni intervallo: è lì che si legge il saldo cumulato.

    L'ultimo punto è sempre `date_to`, anche se l'intervallo finale è parziale — così
    il grafico arriva davvero fino alla fine del periodo scelto.
    """
    out: list[dt.date] = []

    if granularity == DAY:
        day = date_from
        while day <= date_to:
            out.append(day)
            day += dt.timedelta(days=1)
        return out

    if granularity == WEEK:
        # fine settimana = domenica
        cursor = date_from + dt.timedelta(days=6 - date_from.weekday())
        while cursor < date_to:
            out.append(cursor)
            cursor += dt.timedelta(days=7)
    else:
        year, month = date_from.year, date_from.month
        while True:
            last = dt.date(year, month, calendar.monthrange(year, month)[1])
            if last >= date_to:
                break
            out.append(last)
            month += 1
            if month > 12:
                year, month = year + 1, 1

    out.append(date_to)
    return out


async def net_worth_series(
    session: AsyncSession,
    user_id: int,
    date_from: dt.date,
    date_to: dt.date,
    *,
    account_ids: list[int] | None = None,
) -> dict:
    """Andamento del patrimonio nel periodo.

    Si parte dal saldo posseduto **alla vigilia** del periodo e si applicano i movimenti
    giorno per giorno: così la linea mostra il patrimonio reale, non soltanto i flussi
    del periodo. È anche il motivo per cui il primo punto non parte quasi mai da zero.
    """
    granularity = pick_granularity(date_from, date_to)

    opening_by_account = await balances_by_account(
        session, user_id, as_of=date_from - dt.timedelta(days=1)
    )
    if account_ids is None:
        opening = q2(sum(opening_by_account.values(), ZERO))
    else:
        opening = q2(sum((opening_by_account.get(i, ZERO) for i in account_ids), ZERO))

    deltas = await daily_deltas(session, user_id, date_from, date_to, account_ids=account_ids)

    points: list[dict] = []
    running: Decimal = opening
    cursor = date_from
    for bucket_end in buckets(date_from, date_to, granularity):
        while cursor <= bucket_end:
            running += deltas.get(cursor, ZERO)
            cursor += dt.timedelta(days=1)
        points.append({"date": bucket_end, "value": q2(running)})

    return {
        "date_from": date_from,
        "date_to": date_to,
        "granularity": granularity,
        "opening_balance": opening,
        "closing_balance": points[-1]["value"] if points else opening,
        "points": points,
    }
