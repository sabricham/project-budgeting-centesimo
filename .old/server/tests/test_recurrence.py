"""Test dell'espansione delle ricorrenze (§2.7) — pura logica, nessun database."""

from __future__ import annotations

import datetime as dt

import pytest

from app.enums import Frequency
from app.services.recurrence import (
    next_occurrence,
    occurrences_between,
    validate_occurrence_days,
)

D = dt.date


def expand(**kwargs):
    base = {
        "interval": 1,
        "end_date": None,
        "window_start": D(2026, 1, 1),
        "window_end": D(2026, 12, 31),
    }
    return occurrences_between(**{**base, **kwargs})


def test_monthly_due_date_al_mese():
    """Il caso richiesto esplicitamente: più date a calendario nello stesso mese."""
    dates = expand(
        frequency=Frequency.monthly,
        occurrence_days=[1, 15],
        start_date=D(2026, 1, 1),
        window_end=D(2026, 3, 31),
    )
    assert dates == [
        D(2026, 1, 1),
        D(2026, 1, 15),
        D(2026, 2, 1),
        D(2026, 2, 15),
        D(2026, 3, 1),
        D(2026, 3, 15),
    ]


def test_monthly_giorno_31_viene_riportato_a_fine_mese():
    dates = expand(
        frequency=Frequency.monthly,
        occurrence_days=[31],
        start_date=D(2026, 1, 31),
        window_end=D(2026, 4, 30),
    )
    assert dates == [D(2026, 1, 31), D(2026, 2, 28), D(2026, 3, 31), D(2026, 4, 30)]


def test_monthly_con_intervallo_2():
    dates = expand(
        frequency=Frequency.monthly,
        interval=2,
        occurrence_days=[10],
        start_date=D(2026, 1, 10),
        window_end=D(2026, 6, 30),
    )
    assert dates == [D(2026, 1, 10), D(2026, 3, 10), D(2026, 5, 10)]


def test_weekly_lunedi_e_giovedi():
    dates = expand(
        frequency=Frequency.weekly,
        occurrence_days=[0, 3],
        start_date=D(2026, 1, 5),  # lunedì
        window_start=D(2026, 1, 5),
        window_end=D(2026, 1, 18),
    )
    assert dates == [D(2026, 1, 5), D(2026, 1, 8), D(2026, 1, 12), D(2026, 1, 15)]


def test_weekly_ogni_due_settimane():
    dates = expand(
        frequency=Frequency.weekly,
        interval=2,
        occurrence_days=[0],
        start_date=D(2026, 1, 5),
        window_start=D(2026, 1, 5),
        window_end=D(2026, 2, 16),
    )
    assert dates == [D(2026, 1, 5), D(2026, 1, 19), D(2026, 2, 2), D(2026, 2, 16)]


def test_yearly():
    dates = expand(
        frequency=Frequency.yearly,
        occurrence_days=[{"month": 1, "day": 1}, {"month": 7, "day": 14}],
        start_date=D(2026, 1, 1),
    )
    assert dates == [D(2026, 1, 1), D(2026, 7, 14)]


def test_custom_dates():
    dates = expand(
        frequency=Frequency.custom_dates,
        occurrence_days=["2026-03-03", "2026-09-09", "2027-01-01"],
        start_date=D(2026, 1, 1),
    )
    assert dates == [D(2026, 3, 3), D(2026, 9, 9)]


def test_occurrence_days_vuoto_deduce_da_start_date():
    dates = expand(
        frequency=Frequency.monthly,
        occurrence_days=[],
        start_date=D(2026, 1, 7),
        window_end=D(2026, 3, 31),
    )
    assert dates == [D(2026, 1, 7), D(2026, 2, 7), D(2026, 3, 7)]


def test_end_date_taglia_le_occorrenze():
    dates = expand(
        frequency=Frequency.monthly,
        occurrence_days=[1],
        start_date=D(2026, 1, 1),
        end_date=D(2026, 2, 15),
    )
    assert dates == [D(2026, 1, 1), D(2026, 2, 1)]


def test_next_occurrence():
    assert next_occurrence(
        frequency=Frequency.monthly,
        interval=1,
        occurrence_days=[15],
        start_date=D(2026, 1, 1),
        end_date=None,
        today=D(2026, 3, 20),
    ) == D(2026, 4, 15)


@pytest.mark.parametrize(
    "frequency,days",
    [
        (Frequency.monthly, [0]),
        (Frequency.monthly, [32]),
        (Frequency.weekly, [7]),
        (Frequency.yearly, [{"month": 13, "day": 1}]),
        (Frequency.custom_dates, ["non-una-data"]),
    ],
)
def test_validazione_occurrence_days_rifiuta_valori_impossibili(frequency, days):
    with pytest.raises(ValueError):
        validate_occurrence_days(frequency, days)
