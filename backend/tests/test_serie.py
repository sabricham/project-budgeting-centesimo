"""La serie del patrimonio: quello che disegna il grafico della pagina Recap."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from app.modules.reports.service import net_worth_series

pytestmark = pytest.mark.asyncio(loop_scope="session")

MARZO = (dt.date(2026, 3, 1), dt.date(2026, 3, 31))


async def test_la_serie_parte_dal_patrimonio_gia_posseduto(session, scenario, make_entry):
    """Il primo punto non è zero: è quello che rende la linea un patrimonio e non un flusso."""
    serie = await net_worth_series(session, scenario["user_id"], *MARZO)
    assert serie["opening_balance"] == Decimal("1100.00")
    assert serie["points"][0]["value"] == Decimal("1100.00")


async def test_i_movimenti_di_febbraio_contano_nell_apertura_di_marzo(session, scenario, make_entry):
    entry = make_entry("income", "400.00", 5, account=scenario["banca"])
    entry.date = dt.date(2026, 2, 5)
    session.add(entry)
    await session.commit()

    serie = await net_worth_series(session, scenario["user_id"], *MARZO)
    assert serie["opening_balance"] == Decimal("1500.00")


async def test_la_chiusura_coincide_col_saldo_totale(session, scenario, make_entry):
    session.add(make_entry("income", "500.00", 10, account=scenario["banca"]))
    session.add(make_entry("expense", "75.25", 20, account=scenario["contanti"]))
    await session.commit()

    serie = await net_worth_series(session, scenario["user_id"], *MARZO)
    assert serie["closing_balance"] == Decimal("1524.75")
    assert serie["points"][-1]["value"] == serie["closing_balance"]
    assert serie["points"][-1]["date"] == dt.date(2026, 3, 31)


async def test_l_investimento_non_muove_la_curva_totale(session, scenario, make_entry):
    """Il comportamento per cui esiste il terzo tipo di movimento."""
    session.add(
        make_entry("investment", "600.00", 15, account=scenario["banca"], to_account=scenario["titoli"])
    )
    await session.commit()

    serie = await net_worth_series(session, scenario["user_id"], *MARZO)
    valori = {p["value"] for p in serie["points"]}
    assert valori == {Decimal("1100.00")}, "un investimento ha alterato il patrimonio totale"


async def test_filtrando_un_conto_l_investimento_si_vede(session, scenario, make_entry):
    session.add(
        make_entry("investment", "600.00", 15, account=scenario["banca"], to_account=scenario["titoli"])
    )
    await session.commit()

    uid = scenario["user_id"]
    banca = await net_worth_series(session, uid, *MARZO, account_ids=[scenario["banca"]])
    assert banca["opening_balance"] == Decimal("1000.00")
    assert banca["closing_balance"] == Decimal("400.00")

    titoli = await net_worth_series(session, uid, *MARZO, account_ids=[scenario["titoli"]])
    assert titoli["opening_balance"] == Decimal("0.00")
    assert titoli["closing_balance"] == Decimal("600.00")


async def test_la_curva_e_cumulativa_non_giornaliera(session, scenario, make_entry):
    """Ogni punto è il patrimonio a quella data, non la variazione di quel giorno."""
    session.add(make_entry("income", "100.00", 5, account=scenario["banca"]))
    session.add(make_entry("income", "100.00", 10, account=scenario["banca"]))
    await session.commit()

    serie = await net_worth_series(session, scenario["user_id"], *MARZO)
    per_data = {p["date"]: p["value"] for p in serie["points"]}
    assert per_data[dt.date(2026, 3, 4)] == Decimal("1100.00")
    assert per_data[dt.date(2026, 3, 5)] == Decimal("1200.00")
    assert per_data[dt.date(2026, 3, 9)] == Decimal("1200.00")
    assert per_data[dt.date(2026, 3, 10)] == Decimal("1300.00")
    assert per_data[dt.date(2026, 3, 31)] == Decimal("1300.00")


async def test_un_anno_intero_usa_punti_mensili_o_settimanali(session, scenario):
    serie = await net_worth_series(
        session, scenario["user_id"], dt.date(2026, 1, 1), dt.date(2026, 12, 31)
    )
    assert serie["granularity"] in ("week", "month")
    assert len(serie["points"]) < 100, "troppi punti: il grafico sarebbe illeggibile"
