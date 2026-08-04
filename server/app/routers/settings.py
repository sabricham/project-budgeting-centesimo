"""Impostazioni dell'applicazione e azzeramento dei dati personali.

    GET  /settings/market-data     configurazione dati di mercato (chiave mascherata)
    PUT  /settings/market-data     cambia provider, chiave API, endpoint di ricerca
    POST /settings/reset-data      cancella TUTTI i dati personali dell'utente
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, status
from sqlalchemy import delete, select

from app import schemas
from app.auth.deps import CurrentUser, DbSession
from app.auth.security import verify_password
from app.errors import Invalid, Unauthorized
from app.models import (
    Account,
    ApiBudget,
    Budget,
    Category,
    DashboardWidget,
    Goal,
    Holding,
    LiabilityUpdate,
    NetWorthSnapshot,
    RecurringTransaction,
    StockTransaction,
    Transaction,
    Transfer,
)
from app.services import app_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/market-data", response_model=schemas.MarketDataSettingsOut)
async def get_market_data(user: CurrentUser, session: DbSession) -> dict:
    provider, api_key, search_url = await app_settings.market_data_config(session)
    today = dt.date.today()
    budget = await session.get(ApiBudget, (today, provider))
    return {
        "provider": provider,
        # Mai in chiaro: una chiave salvata non deve poter essere riletta.
        "api_key_masked": app_settings.mask(api_key),
        "api_key_configured": bool(api_key),
        "search_url": search_url,
        "signup_url": app_settings.SIGNUP_URL,
        "daily_budget": None,
        "used_today": budget.used if budget else 0,
    }


@router.put("/market-data", response_model=schemas.MarketDataSettingsOut)
async def put_market_data(
    payload: schemas.MarketDataSettingsIn, user: CurrentUser, session: DbSession
) -> dict:
    if payload.provider is not None:
        await app_settings.put(session, app_settings.KEY_PROVIDER, payload.provider)
    if payload.search_url is not None:
        await app_settings.put(session, app_settings.KEY_SEARCH_URL, payload.search_url)
    # Stringa vuota = "lascia com'è": senza questa distinzione un salvataggio del modulo
    # con il campo chiave vuoto (perché mostrato mascherato) cancellerebbe la chiave.
    if payload.api_key:
        await app_settings.put(session, app_settings.KEY_API_KEY, payload.api_key)
    await session.commit()
    return await get_market_data(user, session)


@router.post("/reset-data", response_model=schemas.ResetResult)
async def reset_data(
    payload: schemas.ResetRequest, user: CurrentUser, session: DbSession
) -> dict:
    """Cancella tutti i dati personali dell'utente. **Irreversibile.**

    Restano solo l'account di accesso e le impostazioni: conti, movimenti, categorie,
    budget, obiettivi, ricorrenze e portafoglio vengono eliminati definitivamente, senza
    passare dal soft-delete.

    Due protezioni: serve la password, e serve scrivere una parola di conferma esatta —
    un click distratto non deve poter azzerare anni di dati.
    """
    if not verify_password(payload.password, user.password_hash):
        raise Unauthorized("Password errata", code="invalid_credentials")
    if payload.confirmation.strip().upper() != "AZZERA":
        raise Invalid("Per confermare scrivi AZZERA", code="confirmation_required")

    deleted: dict[str, int] = {}
    account_ids = list(
        (await session.execute(select(Account.id).where(Account.user_id == user.id))).scalars()
    )

    # Ordine dettato dalle chiavi esterne: prima i figli, poi i padri.
    for label, statement in (
        ("stock_transactions", delete(StockTransaction).where(StockTransaction.user_id == user.id)),
        ("holdings", delete(Holding).where(Holding.user_id == user.id)),
        ("liability_updates",
         delete(LiabilityUpdate).where(LiabilityUpdate.account_id.in_(account_ids))
         if account_ids else None),
        ("transactions", delete(Transaction).where(Transaction.user_id == user.id)),
        ("transfers", delete(Transfer).where(Transfer.user_id == user.id)),
        ("recurring_transactions",
         delete(RecurringTransaction).where(RecurringTransaction.user_id == user.id)),
        ("goals", delete(Goal).where(Goal.user_id == user.id)),
        ("budgets", delete(Budget).where(Budget.user_id == user.id)),
        ("dashboard_widgets", delete(DashboardWidget).where(DashboardWidget.user_id == user.id)),
        ("net_worth_snapshots",
         delete(NetWorthSnapshot).where(NetWorthSnapshot.user_id == user.id)),
        ("accounts", delete(Account).where(Account.user_id == user.id)),
        ("categories", delete(Category).where(Category.user_id == user.id)),
    ):
        if statement is None:
            deleted[label] = 0
            continue
        result = await session.execute(statement)
        deleted[label] = result.rowcount or 0

    await session.commit()
    return {"deleted": deleted, "total": sum(deleted.values())}
