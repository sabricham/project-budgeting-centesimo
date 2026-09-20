"""Matematica dei saldi: è il punto in cui un errore resta invisibile più a lungo."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from app.modules.entries.service import (
    balances_by_account,
    daily_deltas,
    net_worth,
    totals_by_kind,
)
from app.modules.reports.service import net_worth_series

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_saldo_iniziale_senza_movimenti(session, scenario):
    saldi = await balances_by_account(session, scenario["user_id"])
    assert saldi[scenario["banca"]] == Decimal("1000.00")
    assert saldi[scenario["contanti"]] == Decimal("100.00")
    assert saldi[scenario["titoli"]] == Decimal("0.00")


async def test_entrata_somma_e_uscita_sottrae(session, scenario, make_entry):
    session.add(make_entry("income", "250.00", 5, account=scenario["banca"]))
    session.add(make_entry("expense", "40.50", 6, account=scenario["banca"]))
    await session.commit()

    saldi = await balances_by_account(session, scenario["user_id"])
    assert saldi[scenario["banca"]] == Decimal("1209.50")


async def test_investimento_sposta_senza_creare_ne_distruggere(session, scenario, make_entry):
    """Il punto centrale del modello: investire non è spendere.

    Il conto di partenza scende, quello di destinazione sale dello stesso importo,
    e il patrimonio complessivo non si muove di un centesimo.
    """
    prima = await net_worth(session, scenario["user_id"])

    session.add(
        make_entry("investment", "500.00", 10, account=scenario["banca"], to_account=scenario["titoli"])
    )
    await session.commit()

    saldi = await balances_by_account(session, scenario["user_id"])
    assert saldi[scenario["banca"]] == Decimal("500.00")
    assert saldi[scenario["titoli"]] == Decimal("500.00")
    assert await net_worth(session, scenario["user_id"]) == prima


async def test_as_of_ignora_i_movimenti_futuri(session, scenario, make_entry):
    session.add(make_entry("income", "100.00", 5, account=scenario["banca"]))
    session.add(make_entry("income", "100.00", 20, account=scenario["banca"]))
    await session.commit()

    uid = scenario["user_id"]
    al_10 = await balances_by_account(session, uid, as_of=dt.date(2026, 3, 10))
    alla_fine = await balances_by_account(session, uid)
    assert al_10[scenario["banca"]] == Decimal("1100.00")
    assert alla_fine[scenario["banca"]] == Decimal("1200.00")


async def test_entry_cancellata_esce_dai_saldi(session, scenario, make_entry):
    entry = make_entry("expense", "300.00", 5, account=scenario["banca"])
    session.add(entry)
    await session.commit()
    assert (await balances_by_account(session, scenario["user_id"]))[scenario["banca"]] == Decimal("700.00")

    entry.deleted_at = dt.datetime.now(dt.timezone.utc)
    await session.commit()
    assert (await balances_by_account(session, scenario["user_id"]))[scenario["banca"]] == Decimal("1000.00")


async def test_totali_per_tipo(session, scenario, make_entry):
    session.add(make_entry("income", "1000.00", 3, account=scenario["banca"]))
    session.add(make_entry("expense", "20.00", 4, account=scenario["banca"]))
    session.add(make_entry("expense", "30.00", 5, account=scenario["contanti"]))
    session.add(
        make_entry("investment", "200.00", 6, account=scenario["banca"], to_account=scenario["titoli"])
    )
    await session.commit()

    totali = await totals_by_kind(
        session, scenario["user_id"], dt.date(2026, 3, 1), dt.date(2026, 3, 31)
    )
    assert totali["income"] == Decimal("1000.00")
    assert totali["expense"] == Decimal("50.00")
    assert totali["investment"] == Decimal("200.00")


async def test_delta_giornalieri_si_annullano_sull_investimento(session, scenario, make_entry):
    """Su tutti i conti l'investimento vale zero; filtrando un conto solo, no."""
    session.add(
        make_entry("investment", "300.00", 12, account=scenario["banca"], to_account=scenario["titoli"])
    )
    await session.commit()

    uid = scenario["user_id"]
    periodo = (dt.date(2026, 3, 1), dt.date(2026, 3, 31))

    tutti = await daily_deltas(session, uid, *periodo)
    assert tutti.get(dt.date(2026, 3, 12), Decimal("0")) == Decimal("0")

    solo_banca = await daily_deltas(session, uid, *periodo, account_ids=[scenario["banca"]])
    assert solo_banca[dt.date(2026, 3, 12)] == Decimal("-300.00")

    solo_titoli = await daily_deltas(session, uid, *periodo, account_ids=[scenario["titoli"]])
    assert solo_titoli[dt.date(2026, 3, 12)] == Decimal("300.00")
