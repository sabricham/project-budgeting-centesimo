"""Test di integrazione dell'API (richiedono Postgres: `docker compose exec api pytest`).

Coprono le invarianti che è più costoso scoprire rotte in produzione:
saldi calcolati, trasferimenti esclusi dai report di spesa, budget, patrimonio netto,
ricorrenze, media ponderata del portafoglio, controllo di concorrenza.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

# I test devono girare sullo stesso event loop delle fixture (`engine` e' di scope
# sessione, e le connessioni asyncpg restano legate al loop che le ha aperte).
# Senza questo ogni accesso al DB fallisce con "got Future attached to a different
# loop": in pytest-asyncio 0.25 lo scope del loop dei TEST si imposta solo dal
# marker, non da pytest.ini (`asyncio_default_fixture_loop_scope` copre le fixture).
pytestmark = pytest.mark.asyncio(loop_scope="session")

API = "/api/v1"
TODAY = dt.date.today()
FIRST_OF_MONTH = TODAY.replace(day=1)


async def make_account(auth, name: str, account_type: str = "bank", initial: str = "0.00") -> dict:
    response = await auth.post(
        f"{API}/accounts",
        json={"name": name, "type": account_type, "currency": "EUR", "initial_balance": initial},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def make_category(auth, name: str, category_type: str = "expense", parent: int | None = None) -> dict:
    response = await auth.post(
        f"{API}/categories",
        json={"name": name, "type": category_type, "parent_category_id": parent},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def make_transaction(auth, account_id: int, category_id: int, amount: str, tx_type: str = "expense", date: dt.date | None = None) -> dict:
    response = await auth.post(
        f"{API}/transactions",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "type": tx_type,
            "amount": amount,
            "date": (date or TODAY).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- #
#  Auth
# --------------------------------------------------------------------------- #


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["db"] == "ok"


async def test_login_refresh_logout(client, user):
    login = await client.post(
        f"{API}/auth/login", json={"username": "tester", "password": "password123"}
    )
    assert login.status_code == 200
    tokens = login.json()

    me = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.json()["username"] == "tester"

    refreshed = await client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200

    # il refresh token è a uso singolo: riutilizzarlo deve fallire
    replay = await client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "invalid_refresh_token"

    new_tokens = refreshed.json()
    logout = await client.post(f"{API}/auth/logout", json={"refresh_token": new_tokens["refresh_token"]})
    assert logout.status_code == 204
    after = await client.post(f"{API}/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]})
    assert after.status_code == 401


async def test_credenziali_sbagliate(client, user):
    response = await client.post(f"{API}/auth/login", json={"username": "tester", "password": "sbagliata"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_endpoint_protetto_senza_token(client):
    assert (await client.get(f"{API}/accounts")).status_code == 401


# --------------------------------------------------------------------------- #
#  Saldi (§2.2)
# --------------------------------------------------------------------------- #


async def test_saldo_calcolato_dai_movimenti(auth):
    account = await make_account(auth, "Conto", initial="1000.00")
    spesa = await make_category(auth, "Spesa")
    entrata = await make_category(auth, "Stipendio", "income")

    await make_transaction(auth, account["id"], spesa["id"], "250.50")
    await make_transaction(auth, account["id"], entrata["id"], "1500.00", "income")

    fresh = (await auth.get(f"{API}/accounts/{account['id']}")).json()
    assert Decimal(fresh["balance"]) == Decimal("2249.50")


async def test_transazione_projected_non_entra_nel_saldo(auth):
    account = await make_account(auth, "Conto", initial="100.00")
    category = await make_category(auth, "Bollette")

    response = await auth.post(
        f"{API}/transactions",
        json={
            "account_id": account["id"],
            "category_id": category["id"],
            "type": "expense",
            "amount": "50.00",
            "date": TODAY.isoformat(),
            "status": "projected",
        },
    )
    assert response.status_code == 201

    fresh = (await auth.get(f"{API}/accounts/{account['id']}")).json()
    assert Decimal(fresh["balance"]) == Decimal("100.00")


async def test_soft_delete_toglie_dal_saldo_e_restore_lo_rimette(auth):
    account = await make_account(auth, "Conto", initial="500.00")
    category = await make_category(auth, "Spesa")
    tx = await make_transaction(auth, account["id"], category["id"], "100.00")

    await auth.delete(f"{API}/transactions/{tx['id']}")
    assert Decimal((await auth.get(f"{API}/accounts/{account['id']}")).json()["balance"]) == Decimal("500.00")

    await auth.post(f"{API}/transactions/{tx['id']}/restore")
    assert Decimal((await auth.get(f"{API}/accounts/{account['id']}")).json()["balance"]) == Decimal("400.00")


# --------------------------------------------------------------------------- #
#  Validazione lato server (§1.3)
# --------------------------------------------------------------------------- #


async def test_categoria_di_tipo_sbagliato_rifiutata(auth):
    account = await make_account(auth, "Conto")
    entrata = await make_category(auth, "Stipendio", "income")

    response = await auth.post(
        f"{API}/transactions",
        json={
            "account_id": account["id"],
            "category_id": entrata["id"],
            "type": "expense",
            "amount": "10.00",
            "date": TODAY.isoformat(),
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid"


async def test_importo_negativo_rifiutato(auth):
    account = await make_account(auth, "Conto")
    category = await make_category(auth, "Spesa")
    response = await auth.post(
        f"{API}/transactions",
        json={
            "account_id": account["id"],
            "category_id": category["id"],
            "type": "expense",
            "amount": "-10.00",
            "date": TODAY.isoformat(),
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_transazione_su_conto_liability_rifiutata(auth):
    mutuo = await make_account(auth, "Mutuo", "liability")
    category = await make_category(auth, "Mutuo/Prestiti")
    response = await auth.post(
        f"{API}/transactions",
        json={
            "account_id": mutuo["id"],
            "category_id": category["id"],
            "type": "expense",
            "amount": "600.00",
            "date": TODAY.isoformat(),
        },
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
#  Trasferimenti (§2.3)
# --------------------------------------------------------------------------- #


async def test_trasferimento_muove_i_saldi_ma_non_e_una_spesa(auth):
    banca = await make_account(auth, "Banca", initial="1000.00")
    satispay = await make_account(auth, "Satispay", "ewallet", initial="0.00")
    category = await make_category(auth, "Spesa")
    await make_transaction(auth, banca["id"], category["id"], "100.00")

    response = await auth.post(
        f"{API}/transfers",
        json={
            "from_account_id": banca["id"],
            "to_account_id": satispay["id"],
            "amount": "200.00",
            "date": TODAY.isoformat(),
        },
    )
    assert response.status_code == 201

    assert Decimal((await auth.get(f"{API}/accounts/{banca['id']}")).json()["balance"]) == Decimal("700.00")
    assert Decimal((await auth.get(f"{API}/accounts/{satispay['id']}")).json()["balance"]) == Decimal("200.00")

    # il report di spesa vede solo i 100 della transazione, non i 200 spostati
    report = (await auth.get(f"{API}/reports/by-category?type=expense&range=month")).json()
    assert Decimal(report["total"]) == Decimal("100.00")


async def test_trasferimento_stesso_conto_rifiutato(auth):
    banca = await make_account(auth, "Banca", initial="100.00")
    response = await auth.post(
        f"{API}/transfers",
        json={
            "from_account_id": banca["id"],
            "to_account_id": banca["id"],
            "amount": "10.00",
            "date": TODAY.isoformat(),
        },
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
#  Budget (§2.5)
# --------------------------------------------------------------------------- #


async def test_budget_include_le_sottocategorie(auth):
    account = await make_account(auth, "Conto", initial="1000.00")
    alimentari = await make_category(auth, "Alimentari")
    supermercato = await make_category(auth, "Supermercato", parent=alimentari["id"])

    await make_transaction(auth, account["id"], alimentari["id"], "50.00", date=FIRST_OF_MONTH)
    await make_transaction(auth, account["id"], supermercato["id"], "70.00", date=FIRST_OF_MONTH)

    created = await auth.post(
        f"{API}/budgets", json={"category_id": alimentari["id"], "amount_limit": "300.00"}
    )
    assert created.status_code == 201

    budget = (await auth.get(f"{API}/budgets")).json()[0]
    assert Decimal(budget["spent_this_month"]) == Decimal("120.00")
    assert Decimal(budget["remaining"]) == Decimal("180.00")


async def test_budget_solo_su_categorie_di_spesa(auth):
    entrata = await make_category(auth, "Stipendio", "income")
    response = await auth.post(
        f"{API}/budgets", json={"category_id": entrata["id"], "amount_limit": "100.00"}
    )
    assert response.status_code == 422


async def test_budget_duplicato_rifiutato(auth):
    category = await make_category(auth, "Spesa")
    await auth.post(f"{API}/budgets", json={"category_id": category["id"], "amount_limit": "100.00"})
    second = await auth.post(
        f"{API}/budgets", json={"category_id": category["id"], "amount_limit": "200.00"}
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "budget_exists"


# --------------------------------------------------------------------------- #
#  Debiti e patrimonio netto (§2.10)
# --------------------------------------------------------------------------- #


async def test_net_worth_sottrae_i_debiti(auth):
    await make_account(auth, "Banca", initial="10000.00")
    mutuo = await make_account(auth, "Mutuo", "liability")

    await auth.post(
        f"{API}/liabilities",
        json={"account_id": mutuo["id"], "residual_amount": "144500.00", "date": TODAY.isoformat()},
    )

    report = (await auth.get(f"{API}/reports/net-worth")).json()
    assert Decimal(report["assets"]) == Decimal("10000.00")
    assert Decimal(report["liabilities"]) == Decimal("144500.00")
    assert Decimal(report["net_worth"]) == Decimal("-134500.00")


async def test_liability_usa_lultimo_snapshot(auth):
    mutuo = await make_account(auth, "Mutuo", "liability")
    for day, residual in (
        (TODAY - dt.timedelta(days=60), "150000.00"),
        (TODAY - dt.timedelta(days=30), "147000.00"),
    ):
        await auth.post(
            f"{API}/liabilities",
            json={"account_id": mutuo["id"], "residual_amount": residual, "date": day.isoformat()},
        )

    account = (await auth.get(f"{API}/accounts/{mutuo['id']}")).json()
    assert Decimal(account["balance"]) == Decimal("147000.00")


# --------------------------------------------------------------------------- #
#  Obiettivi (§2.9)
# --------------------------------------------------------------------------- #


async def test_goal_progresso_dal_conto_collegato(auth):
    banca = await make_account(auth, "Banca", initial="5000.00")
    fondo = await make_account(auth, "Vacanze", "savings_goal", initial="0.00")

    await auth.post(
        f"{API}/transfers",
        json={
            "from_account_id": banca["id"],
            "to_account_id": fondo["id"],
            "amount": "600.00",
            "date": TODAY.isoformat(),
        },
    )
    created = await auth.post(
        f"{API}/goals",
        json={"name": "Vacanza", "target_amount": "2400.00", "linked_account_id": fondo["id"]},
    )
    assert created.status_code == 201
    goal = created.json()
    assert Decimal(goal["current_amount"]) == Decimal("600.00")
    assert goal["progress"] == pytest.approx(0.25)


async def test_goal_solo_su_conti_savings_goal(auth):
    banca = await make_account(auth, "Banca")
    response = await auth.post(
        f"{API}/goals",
        json={"name": "X", "target_amount": "100.00", "linked_account_id": banca["id"]},
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
#  Ricorrenze (§2.7)
# --------------------------------------------------------------------------- #


async def test_ricorrenza_genera_occorrenze_e_conferma(auth):
    account = await make_account(auth, "Conto", initial="1000.00")
    category = await make_category(auth, "Bollette")

    created = await auth.post(
        f"{API}/recurring",
        json={
            "account_id": account["id"],
            "category_id": category["id"],
            "type": "expense",
            "amount": "80.00",
            "description": "Luce",
            "frequency": "monthly",
            "occurrence_days": [1, 15],
            "start_date": FIRST_OF_MONTH.isoformat(),
            "auto_confirm": False,
        },
    )
    assert created.status_code == 201

    upcoming = (await auth.get(f"{API}/recurring/upcoming?days=90")).json()
    assert upcoming["total"] >= 2

    # finché sono `projected` il saldo non si muove
    assert Decimal((await auth.get(f"{API}/accounts/{account['id']}")).json()["balance"]) == Decimal("1000.00")

    # conferma con importo corretto (bolletta a importo variabile)
    occurrence = upcoming["items"][0]
    confirmed = await auth.post(
        f"{API}/recurring/occurrences/{occurrence['id']}/confirm", json={"amount": "95.40"}
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    assert Decimal((await auth.get(f"{API}/accounts/{account['id']}")).json()["balance"]) == Decimal("904.60")


async def test_generazione_ricorrenze_idempotente(auth):
    account = await make_account(auth, "Conto", initial="1000.00")
    category = await make_category(auth, "Abbonamenti")
    await auth.post(
        f"{API}/recurring",
        json={
            "account_id": account["id"],
            "category_id": category["id"],
            "type": "expense",
            "amount": "12.99",
            "description": "Netflix",
            "frequency": "monthly",
            "occurrence_days": [5],
            "start_date": FIRST_OF_MONTH.isoformat(),
        },
    )
    before = (await auth.get(f"{API}/transactions?include_deleted=true&limit=500")).json()["total"]
    await auth.post(f"{API}/recurring/generate")
    await auth.post(f"{API}/recurring/generate")
    after = (await auth.get(f"{API}/transactions?include_deleted=true&limit=500")).json()["total"]
    assert before == after


# --------------------------------------------------------------------------- #
#  Portafoglio (§2.8)
# --------------------------------------------------------------------------- #


async def test_portafoglio_media_ponderata_e_plusvalenza(auth):
    broker = await make_account(auth, "Broker", "investment", initial="10000.00")

    async def stock(tx_type: str, **kwargs):
        payload = {"account_id": broker["id"], "ticker": "AAPL", "type": tx_type,
                   "currency": "EUR", "date": TODAY.isoformat(), **kwargs}
        response = await auth.post(f"{API}/portfolio/transactions", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    await stock("buy", quantity="10", price_per_share="100", fees="5.00")
    await stock("buy", quantity="10", price_per_share="110", fees="5.00")
    sell = await stock("sell", quantity="5", price_per_share="120", fees="5.00")

    # media ponderata comprensiva di commissioni: (1005 + 1105) / 20 = 105.50
    assert Decimal(sell["realized_pnl"]) == Decimal("67.50")

    await auth.put(f"{API}/portfolio/prices/AAPL", json={"price": "130", "currency": "EUR"})
    summary = (await auth.get(f"{API}/portfolio/{broker['id']}")).json()

    assert Decimal(summary["cash_balance"]) == Decimal("8485.00")
    assert Decimal(summary["holdings"][0]["quantity"]) == Decimal("15")
    assert Decimal(summary["holdings"][0]["avg_cost_basis"]) == Decimal("105.50")
    assert Decimal(summary["holdings_value"]) == Decimal("1950.00")
    assert Decimal(summary["total_value"]) == Decimal("10435.00")
    assert Decimal(summary["unrealized_pnl"]) == Decimal("367.50")
    assert Decimal(summary["realized_pnl"]) == Decimal("67.50")

    # il saldo del conto investimento include liquidità + valore di mercato
    account = (await auth.get(f"{API}/accounts/{broker['id']}")).json()
    assert Decimal(account["balance"]) == Decimal("10435.00")


async def test_vendita_oltre_la_quantita_posseduta_rifiutata(auth):
    broker = await make_account(auth, "Broker", "investment", initial="1000.00")
    await auth.post(
        f"{API}/portfolio/transactions",
        json={"account_id": broker["id"], "ticker": "MSFT", "type": "buy", "quantity": "2",
              "price_per_share": "100", "currency": "EUR", "date": TODAY.isoformat()},
    )
    response = await auth.post(
        f"{API}/portfolio/transactions",
        json={"account_id": broker["id"], "ticker": "MSFT", "type": "sell", "quantity": "5",
              "price_per_share": "100", "currency": "EUR", "date": TODAY.isoformat()},
    )
    assert response.status_code == 422


async def test_titoli_solo_su_conti_investment(auth):
    banca = await make_account(auth, "Banca", initial="1000.00")
    response = await auth.post(
        f"{API}/portfolio/transactions",
        json={"account_id": banca["id"], "ticker": "AAPL", "type": "buy", "quantity": "1",
              "price_per_share": "100", "currency": "EUR", "date": TODAY.isoformat()},
    )
    assert response.status_code == 422


async def test_dividendo_aumenta_la_liquidita(auth):
    broker = await make_account(auth, "Broker", "investment", initial="1000.00")
    response = await auth.post(
        f"{API}/portfolio/transactions",
        json={"account_id": broker["id"], "ticker": "VWCE", "type": "dividend", "amount": "42.00",
              "currency": "EUR", "date": TODAY.isoformat()},
    )
    assert response.status_code == 201
    summary = (await auth.get(f"{API}/portfolio/{broker['id']}")).json()
    assert Decimal(summary["cash_balance"]) == Decimal("1042.00")


# --------------------------------------------------------------------------- #
#  Report (§2.11)
# --------------------------------------------------------------------------- #


async def test_timeseries_saldo_mensile(auth):
    account = await make_account(auth, "Conto", initial="100.00")
    category = await make_category(auth, "Spesa")
    await make_transaction(auth, account["id"], category["id"], "40.00", date=FIRST_OF_MONTH)

    series = (await auth.get(f"{API}/reports/timeseries?metric=balance&range=month")).json()
    assert series["metric"] == "balance"
    assert len(series["points"]) >= 28
    assert Decimal(series["points"][0]["value"]) == Decimal("60.00")


async def test_timeseries_spending_esclude_i_trasferimenti(auth):
    banca = await make_account(auth, "Banca", initial="1000.00")
    fondo = await make_account(auth, "Fondo", "savings_goal")
    category = await make_category(auth, "Spesa")
    await make_transaction(auth, banca["id"], category["id"], "30.00", date=FIRST_OF_MONTH)
    await auth.post(
        f"{API}/transfers",
        json={"from_account_id": banca["id"], "to_account_id": fondo["id"],
              "amount": "500.00", "date": FIRST_OF_MONTH.isoformat()},
    )

    series = (await auth.get(f"{API}/reports/timeseries?metric=spending&range=month")).json()
    assert sum(Decimal(p["value"]) for p in series["points"]) == Decimal("30.00")


# --------------------------------------------------------------------------- #
#  Concorrenza (§1.3) e dashboard (§2.11)
# --------------------------------------------------------------------------- #


async def test_updated_at_stantio_da_409(auth):
    account = await make_account(auth, "Conto", initial="100.00")
    await auth.patch(f"{API}/accounts/{account['id']}", json={"name": "Rinominato"})

    response = await auth.patch(
        f"{API}/accounts/{account['id']}",
        json={"name": "Altro nome", "expected_updated_at": account["updated_at"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_update"


async def test_dashboard_widget_crud(auth):
    created = await auth.post(
        f"{API}/dashboard/widgets",
        json={"type": "balance", "position_x": 0, "position_y": 0, "width": 2, "height": 1,
              "config": {"range": "month", "account_ids": [1]}},
    )
    assert created.status_code == 201
    widget = created.json()
    assert widget["config"]["range"] == "month"

    patched = await auth.patch(
        f"{API}/dashboard/widgets/{widget['id']}", json={"config": {"range": "year"}}
    )
    assert patched.json()["config"]["range"] == "year"

    assert (await auth.delete(f"{API}/dashboard/widgets/{widget['id']}")).status_code == 204
    assert (await auth.get(f"{API}/dashboard/widgets")).json() == []


async def test_conto_con_movimenti_non_eliminabile_ma_archiviabile(auth):
    account = await make_account(auth, "Conto", initial="100.00")
    category = await make_category(auth, "Spesa")
    await make_transaction(auth, account["id"], category["id"], "10.00")

    hard = await auth.delete(f"{API}/accounts/{account['id']}?hard=true")
    assert hard.status_code == 409

    assert (await auth.delete(f"{API}/accounts/{account['id']}")).status_code == 204
    assert (await auth.get(f"{API}/accounts")).json() == []
    assert len((await auth.get(f"{API}/accounts?include_archived=true")).json()) == 1
