"""Granularità e intervalli del grafico. Logica pura: nessun database."""

from __future__ import annotations

import datetime as dt

from app.modules.reports.service import DAY, MONTH, WEEK, buckets, pick_granularity


def test_granularita_cresce_con_l_ampiezza():
    d = dt.date(2026, 1, 1)
    assert pick_granularity(d, d + dt.timedelta(days=6)) == DAY       # ultimi 7 giorni
    assert pick_granularity(d, d + dt.timedelta(days=30)) == DAY      # un mese
    assert pick_granularity(d, d + dt.timedelta(days=29)) == DAY      # ultimi 30 giorni
    assert pick_granularity(d, d + dt.timedelta(days=90)) == WEEK     # un trimestre
    assert pick_granularity(d, d + dt.timedelta(days=364)) == WEEK    # ultimi 365 giorni
    assert pick_granularity(d, d + dt.timedelta(days=1000)) == MONTH


def test_un_punto_per_giorno_del_mese():
    punti = buckets(dt.date(2026, 3, 1), dt.date(2026, 3, 31), DAY)
    assert len(punti) == 31
    assert punti[0] == dt.date(2026, 3, 1)
    assert punti[-1] == dt.date(2026, 3, 31)


def test_l_ultimo_punto_e_sempre_la_fine_del_periodo():
    """Anche quando l'ultimo intervallo è parziale: il grafico deve arrivare in fondo."""
    for granularita in (DAY, WEEK, MONTH):
        punti = buckets(dt.date(2026, 1, 15), dt.date(2026, 7, 9), granularita)
        assert punti[-1] == dt.date(2026, 7, 9), granularita
        assert punti == sorted(punti), granularita
        assert len(punti) == len(set(punti)), f"{granularita}: punti duplicati"


def test_i_punti_settimanali_cadono_di_domenica():
    punti = buckets(dt.date(2026, 1, 1), dt.date(2026, 4, 1), WEEK)
    # tutti tranne l'ultimo, che è la fine del periodo
    for punto in punti[:-1]:
        assert punto.weekday() == 6, f"{punto} non è domenica"


def test_periodo_di_un_giorno_solo():
    giorno = dt.date(2026, 3, 10)
    assert buckets(giorno, giorno, DAY) == [giorno]
