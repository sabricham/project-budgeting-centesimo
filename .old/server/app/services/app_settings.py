"""Impostazioni modificabili a caldo, con ricaduta sui valori di avvio.

Ordine di precedenza: **tabella `app_settings` → file di secret / variabile d'ambiente →
valore predefinito**. Così l'applicazione può cambiare la chiave API senza riavviare il
container, ma un deploy pulito continua a partire dal Docker secret come prima (§3.1).

I segreti non escono mai in chiaro da qui verso il client: c'è `mask` apposta.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AppSetting

KEY_API_KEY = "market_data_api_key"
KEY_PROVIDER = "market_data_provider"
KEY_SEARCH_URL = "market_data_search_url"

#: Endpoint di ricerca simboli, preimpostato. È un'informazione pubblica, non un segreto.
DEFAULT_SEARCH_URL = "https://www.alphavantage.co/query?function=SYMBOL_SEARCH"

#: Dove registrarsi per ottenere una chiave gratuita, mostrato nell'applicazione.
SIGNUP_URL = "https://www.alphavantage.co/support/#api-key"


async def get(session: AsyncSession, key: str) -> str | None:
    row = await session.get(AppSetting, key)
    value = (row.value or "").strip() if row else ""
    return value or None


async def put(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key)
        session.add(row)
    row.value = value.strip()
    row.updated_at = dt.datetime.now(dt.timezone.utc)


async def market_data_config(session: AsyncSession) -> tuple[str, str | None, str]:
    """(provider, chiave API, url di ricerca) risolti secondo la precedenza descritta."""
    provider = await get(session, KEY_PROVIDER) or settings.market_data_provider or "none"
    api_key = await get(session, KEY_API_KEY) or settings.market_data_api_key
    search_url = await get(session, KEY_SEARCH_URL) or DEFAULT_SEARCH_URL
    return provider.lower(), api_key, search_url


def mask(secret: str | None) -> str | None:
    """Chiave ridotta a un promemoria: mostra solo le ultime 4 cifre.

    Serve a far vedere all'utente *quale* chiave è configurata senza rimandarla in rete:
    una volta salvata, una chiave non deve più poter essere riletta in chiaro.
    """
    if not secret:
        return None
    return f"••••••••{secret[-4:]}" if len(secret) > 4 else "••••"


async def all_settings(session: AsyncSession) -> list[AppSetting]:
    return list((await session.execute(select(AppSetting))).scalars())
