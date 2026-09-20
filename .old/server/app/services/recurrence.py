"""Espansione delle ricorrenze in date concrete (§2.7).

Il modello copre anche il caso richiesto esplicitamente delle **più date a calendario**
nello stesso periodo (es. bolletta il 1 e il 15 del mese).

Forma di `occurrence_days` per frequenza:

    monthly       [1, 15]                        giorni del mese (1-31)
    weekly        [0, 3]                         giorni della settimana (0 = lunedì)
    yearly        [{"month": 1, "day": 1}]       coppie mese/giorno
    custom_dates  ["2026-03-01", "2026-07-14"]   date esplicite

`interval` = ogni N settimane/mesi/anni, contati a partire dal periodo di `start_date`.
Se `occurrence_days` è vuoto si deduce da `start_date` (comportamento "ogni mese lo
stesso giorno", il caso più comune).

Giorni inesistenti (31 febbraio) vengono riportati all'ultimo giorno del mese invece di
essere saltati: una rata "il 31" deve comunque cadere a febbraio.
"""

from __future__ import annotations

import calendar
import datetime as dt
from typing import Any

from app.enums import Frequency


def validate_occurrence_days(frequency: Frequency, days: list[Any]) -> None:
    """Validazione lato server della forma di `occurrence_days` (§1.3)."""
    if not days:
        return  # dedotto da start_date

    if frequency is Frequency.monthly:
        for d in days:
            if not isinstance(d, int) or not 1 <= d <= 31:
                raise ValueError("occurrence_days per `monthly` deve contenere interi 1-31")
    elif frequency is Frequency.weekly:
        for d in days:
            if not isinstance(d, int) or not 0 <= d <= 6:
                raise ValueError(
                    "occurrence_days per `weekly` deve contenere interi 0-6 (0 = lunedì)"
                )
    elif frequency is Frequency.yearly:
        for d in days:
            if not isinstance(d, dict) or "month" not in d or "day" not in d:
                raise ValueError(
                    'occurrence_days per `yearly` deve contenere oggetti {"month": M, "day": D}'
                )
            if not 1 <= int(d["month"]) <= 12 or not 1 <= int(d["day"]) <= 31:
                raise ValueError("month deve essere 1-12 e day 1-31")
    elif frequency is Frequency.custom_dates:
        for d in days:
            try:
                dt.date.fromisoformat(str(d))
            except ValueError as exc:
                raise ValueError(
                    "occurrence_days per `custom_dates` deve contenere date ISO (YYYY-MM-DD)"
                ) from exc


def _clamp_day(year: int, month: int, day: int) -> dt.date:
    last = calendar.monthrange(year, month)[1]
    return dt.date(year, month, min(day, last))


def _add_months(year: int, month: int, months: int) -> tuple[int, int]:
    index = (year * 12 + (month - 1)) + months
    return index // 12, index % 12 + 1


def occurrences_between(
    *,
    frequency: Frequency | str,
    interval: int,
    occurrence_days: list[Any],
    start_date: dt.date,
    end_date: dt.date | None,
    window_start: dt.date,
    window_end: dt.date,
) -> list[dt.date]:
    """Date di occorrenza comprese in [window_start, window_end], ordinate e deduplicate."""
    frequency = Frequency(frequency)
    interval = max(1, int(interval or 1))
    lower = max(window_start, start_date)
    upper = min(window_end, end_date) if end_date else window_end
    if lower > upper:
        return []

    days = list(occurrence_days or [])
    result: set[dt.date] = set()

    if frequency is Frequency.custom_dates:
        for raw in days:
            day = dt.date.fromisoformat(str(raw))
            if lower <= day <= upper:
                result.add(day)

    elif frequency is Frequency.weekly:
        weekdays = [int(d) for d in days] or [start_date.weekday()]
        # ancoraggio: lunedì della settimana di start_date
        anchor = start_date - dt.timedelta(days=start_date.weekday())
        day = lower - dt.timedelta(days=lower.weekday())
        while day <= upper:
            weeks = (day - anchor).days // 7
            if weeks >= 0 and weeks % interval == 0:
                for weekday in weekdays:
                    candidate = day + dt.timedelta(days=weekday)
                    if lower <= candidate <= upper:
                        result.add(candidate)
            day += dt.timedelta(days=7)

    elif frequency is Frequency.monthly:
        month_days = [int(d) for d in days] or [start_date.day]
        offset = 0
        while True:
            year, month = _add_months(start_date.year, start_date.month, offset * interval)
            if dt.date(year, month, 1) > upper:
                break
            for day_of_month in month_days:
                candidate = _clamp_day(year, month, day_of_month)
                if lower <= candidate <= upper:
                    result.add(candidate)
            offset += 1

    elif frequency is Frequency.yearly:
        pairs = (
            [(int(d["month"]), int(d["day"])) for d in days]
            if days
            else [(start_date.month, start_date.day)]
        )
        year = start_date.year
        while year <= upper.year:
            if (year - start_date.year) % interval == 0:
                for month, day_of_month in pairs:
                    candidate = _clamp_day(year, month, day_of_month)
                    if lower <= candidate <= upper:
                        result.add(candidate)
            year += 1

    return sorted(result)


async def generate_occurrences(
    session,
    *,
    user_id: int | None = None,
    recurring_id: int | None = None,
    horizon_days: int = 90,
    today: dt.date | None = None,
    lookback_days: int = 365,
) -> dict[str, int]:
    """Materializza le occorrenze future come `Transaction` (§2.7).

    * genera in anticipo fino a `horizon_days` con `status = projected`, così esiste la
      vista "prossime spese in arrivo";
    * con `auto_confirm` le occorrenze già maturate diventano `confirmed` ed entrano nei
      saldi; altrimenti restano da confermare a mano (bollette a importo variabile);
    * è **idempotente**: la coppia (source_recurring_id, date) è UNIQUE e viene comunque
      ricontrollata prima di inserire, quindi il job può girare quante volte vuole.
    """
    from sqlalchemy import select

    from app.enums import TransactionStatus
    from app.models import RecurringTransaction, Transaction

    today = today or dt.date.today()
    created = confirmed = 0

    stmt = select(RecurringTransaction).where(RecurringTransaction.active.is_(True))
    if user_id is not None:
        stmt = stmt.where(RecurringTransaction.user_id == user_id)
    if recurring_id is not None:
        stmt = stmt.where(RecurringTransaction.id == recurring_id)

    for rec in await session.scalars(stmt):
        window_start = max(rec.start_date, today - dt.timedelta(days=lookback_days))
        dates = occurrences_between(
            frequency=rec.frequency,
            interval=rec.interval,
            occurrence_days=rec.occurrence_days,
            start_date=rec.start_date,
            end_date=rec.end_date,
            window_start=window_start,
            window_end=today + dt.timedelta(days=horizon_days),
        )
        if not dates:
            continue

        existing = {
            row.date: row
            for row in await session.scalars(
                select(Transaction).where(
                    Transaction.source_recurring_id == rec.id,
                    Transaction.date.in_(dates),
                )
            )
        }

        for day in dates:
            row = existing.get(day)
            if row is None:
                status = (
                    TransactionStatus.confirmed.value
                    if rec.auto_confirm and day <= today
                    else TransactionStatus.projected.value
                )
                session.add(
                    Transaction(
                        user_id=rec.user_id,
                        account_id=rec.account_id,
                        category_id=rec.category_id,
                        type=rec.type,
                        amount=rec.amount,
                        date=day,
                        description=rec.description,
                        status=status,
                        source_recurring_id=rec.id,
                    )
                )
                created += 1
            elif (
                rec.auto_confirm
                and day <= today
                and row.status == TransactionStatus.projected.value
                and row.deleted_at is None
            ):
                row.status = TransactionStatus.confirmed.value
                confirmed += 1

    await session.commit()
    return {"created": created, "confirmed": confirmed}


def next_occurrence(
    *,
    frequency: Frequency | str,
    interval: int,
    occurrence_days: list[Any],
    start_date: dt.date,
    end_date: dt.date | None,
    today: dt.date | None = None,
    horizon_days: int = 400,
) -> dt.date | None:
    """Prima occorrenza da oggi in avanti (per la colonna "prossima scadenza")."""
    today = today or dt.date.today()
    upcoming = occurrences_between(
        frequency=frequency,
        interval=interval,
        occurrence_days=occurrence_days,
        start_date=start_date,
        end_date=end_date,
        window_start=today,
        window_end=today + dt.timedelta(days=horizon_days),
    )
    return upcoming[0] if upcoming else None
