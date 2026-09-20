"""Prezzi di mercato e tassi di cambio da fonte esterna (§2.8).

Regole:
  * l'API esterna viene chiamata **solo** dal job schedulato, mai durante una richiesta
    dell'utente: né i rate-limit del piano gratuito né un disservizio del provider
    devono poter bloccare la UI;
  * se manca la chiave API il provider è `none` e il sistema resta pienamente usabile
    inserendo i prezzi a mano (`PUT /portfolio/prices/{ticker}`).

Aggiungere un provider = implementare `MarketDataProvider` e registrarlo in `get_provider`.
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal, InvalidOperation
from typing import Protocol

import httpx

from app.config import settings

log = logging.getLogger(__name__)

#: (prezzo, valuta di quotazione)
Quote = tuple[Decimal, str]

#: Serie giornaliera restituita da un provider: tipo di strumento risolto, valuta di
#: quotazione e chiusure per giorno.
DailySeries = tuple[str, str, dict["dt.date", Decimal]]

#: Alpha Vantage non risponde con un codice HTTP di errore quando la quota è esaurita:
#: risponde 200 con uno di questi campi al posto dei dati. Trattarlo come una risposta
#: valida significherebbe salvare una serie vuota sopra quella buona.
RATE_LIMIT_KEYS = ("Note", "Information", "Error Message")

#: Simboli che vanno cercati sull'endpoint cripto **prima** di quello azionario.
#: Diversi ticker esistono in entrambi i mondi: "BTC" è Bitcoin ma è anche un titolo
#: quotato, e provando prima le azioni si finisce per salvare la quotazione sbagliata
#: (28 USD invece di ~76.000 EUR) senza che nulla segnali l'errore.
CRYPTO_SYMBOLS = frozenset(
    {
        "BTC", "ETH", "USDT", "USDC", "BNB", "XRP", "ADA", "SOL", "DOGE", "DOT",
        "MATIC", "LTC", "TRX", "SHIB", "AVAX", "LINK", "ATOM", "XLM", "XMR", "ETC",
        "BCH", "NEAR", "ALGO", "VET", "FIL", "ICP", "HBAR", "APT", "ARB", "OP",
    }
)


def _to_decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


class MarketDataProvider(Protocol):
    name: str

    async def fetch_quotes(self, tickers: list[str]) -> dict[str, Quote]: ...

    async def fetch_fx_rates(self, pairs: list[tuple[str, str]]) -> dict[tuple[str, str], Decimal]:
        ...

    async def fetch_daily_series(self, ticker: str, hint: str = "unknown") -> DailySeries | None:
        """Serie giornaliera di un singolo ticker, in **una sola** richiesta.

        `hint` è il tipo memorizzato dalla volta precedente ("stock" | "crypto"):
        evita di sprecare un tentativo per capire su quale endpoint cercare.
        Restituisce `None` se il dato non è disponibile o la quota è esaurita.
        """
        ...


class NullProvider:
    """Nessuna fonte esterna configurata: i prezzi si inseriscono manualmente."""

    name = "none"

    async def fetch_quotes(self, tickers: list[str]) -> dict[str, Quote]:
        return {}

    async def fetch_fx_rates(self, pairs: list[tuple[str, str]]) -> dict[tuple[str, str], Decimal]:
        return {}

    async def fetch_daily_series(self, ticker: str, hint: str = "unknown") -> DailySeries | None:
        return None


class TwelveDataProvider:
    """https://twelvedata.com — piano gratuito, batch di simboli in una sola chiamata."""

    name = "twelvedata"
    base_url = "https://api.twelvedata.com"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def fetch_quotes(self, tickers: list[str]) -> dict[str, Quote]:
        if not tickers:
            return {}
        params = {"symbol": ",".join(tickers), "apikey": self._api_key}
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{self.base_url}/quote", params=params)
            response.raise_for_status()
            data = response.json()

        # Con un solo simbolo l'API restituisce l'oggetto, con più simboli una mappa.
        if len(tickers) == 1 and "symbol" in data:
            data = {tickers[0]: data}

        out: dict[str, Quote] = {}
        for ticker, payload in data.items():
            if not isinstance(payload, dict) or payload.get("status") == "error":
                log.warning("twelvedata: nessun prezzo per %s (%s)", ticker, payload)
                continue
            price = _to_decimal(payload.get("close") or payload.get("price"))
            if price is None or price <= 0:
                continue
            out[ticker.upper()] = (price, str(payload.get("currency") or "USD").upper())
        return out

    async def fetch_fx_rates(self, pairs: list[tuple[str, str]]) -> dict[tuple[str, str], Decimal]:
        out: dict[tuple[str, str], Decimal] = {}
        if not pairs:
            return out
        async with httpx.AsyncClient(timeout=15) as client:
            for base, quote in pairs:
                params = {"symbol": f"{base}/{quote}", "apikey": self._api_key}
                try:
                    response = await client.get(f"{self.base_url}/exchange_rate", params=params)
                    response.raise_for_status()
                    rate = _to_decimal(response.json().get("rate"))
                except (httpx.HTTPError, ValueError) as exc:
                    log.warning("twelvedata: cambio %s/%s non recuperato: %s", base, quote, exc)
                    continue
                if rate and rate > 0:
                    out[(base, quote)] = rate
        return out

    async def fetch_daily_series(self, ticker: str, hint: str = "unknown") -> DailySeries | None:
        # Non implementata: il deploy attuale usa Alpha Vantage. Restituendo None il
        # sistema resta funzionante con i soli prezzi già in archivio.
        return None


class AlphaVantageProvider:
    """https://www.alphavantage.co — un simbolo per chiamata, 25 richieste al giorno.

    La serie giornaliera è la chiamata più conveniente del piano gratuito: **una**
    richiesta restituisce insieme la quotazione di oggi e i ~100 giorni precedenti, quindi
    non serve una chiamata separata per il prezzo corrente.
    """

    name = "alphavantage"
    base_url = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def _get(self, client: httpx.AsyncClient, params: dict) -> dict | None:
        """GET che distingue un rifiuto per quota da una risposta con dati."""
        response = await client.get(self.base_url, params={**params, "apikey": self._api_key})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return None
        for key in RATE_LIMIT_KEYS:
            if key in payload:
                log.warning("alphavantage: risposta senza dati (%s): %s", key, payload[key])
                return None
        return payload

    async def fetch_daily_series(self, ticker: str, hint: str = "unknown") -> DailySeries | None:
        symbol = ticker.upper()
        stock_attempt = (
            "stock",
            {"function": "TIME_SERIES_DAILY", "symbol": symbol, "outputsize": "compact"},
        )
        crypto_attempt = ("crypto", self._crypto_params(symbol))

        if hint == "crypto":
            attempts = [crypto_attempt]
        elif hint == "stock":
            # Con un tipo già noto si tenta solo quell'endpoint: una richiesta, non due.
            attempts = [stock_attempt]
        elif symbol in CRYPTO_SYMBOLS:
            # Prima le cripto: questi simboli esistono anche come titoli azionari, e
            # l'ordine sbagliato porta a salvare in silenzio la quotazione di un'altra cosa.
            attempts = [crypto_attempt, stock_attempt]
        else:
            attempts = [stock_attempt, crypto_attempt]

        async with httpx.AsyncClient(timeout=20) as client:
            for kind, params in attempts:
                try:
                    payload = await self._get(client, params)
                except (httpx.HTTPError, ValueError) as exc:
                    log.warning("alphavantage: %s non recuperato: %s", symbol, exc)
                    return None
                if payload is None:
                    # Quota esaurita o simbolo rifiutato: inutile insistere con l'altro
                    # endpoint, si spenderebbe una seconda richiesta per nulla.
                    return None

                parsed = self._parse(payload, kind)
                if parsed is not None:
                    return parsed
        return None

    @staticmethod
    def _crypto_params(symbol: str) -> dict:
        # `market` è la valuta in cui si vuole la quotazione: EUR evita di dover poi
        # applicare un cambio, risparmiando una richiesta di FX.
        return {"function": "DIGITAL_CURRENCY_DAILY", "symbol": symbol, "market": "EUR"}

    @staticmethod
    def _parse(payload: dict, kind: str) -> DailySeries | None:
        series_key = next(
            (k for k in payload if k.lower().startswith("time series")), None
        )
        if series_key is None:
            return None

        currency = "EUR" if kind == "crypto" else "USD"
        if kind == "stock":
            meta = payload.get("Meta Data") or {}
            for key, value in meta.items():
                if "currency" in key.lower() and isinstance(value, str) and len(value) == 3:
                    currency = value.upper()

        closes: dict[dt.date, Decimal] = {}
        for day, row in (payload.get(series_key) or {}).items():
            if not isinstance(row, dict):
                continue
            # Le chiavi sono numerate ("4. close", "4a. close (EUR)"): si cerca per nome.
            raw = next((v for k, v in row.items() if "close" in k.lower()), None)
            price = _to_decimal(raw)
            if price is None or price <= 0:
                continue
            try:
                closes[dt.date.fromisoformat(day[:10])] = price
            except ValueError:
                continue

        return (kind, currency, closes) if closes else None

    async def fetch_quotes(self, tickers: list[str]) -> dict[str, Quote]:
        out: dict[str, Quote] = {}
        async with httpx.AsyncClient(timeout=15) as client:
            for ticker in tickers:
                params = {
                    "function": "GLOBAL_QUOTE",
                    "symbol": ticker,
                    "apikey": self._api_key,
                }
                try:
                    response = await client.get(self.base_url, params=params)
                    response.raise_for_status()
                    quote = response.json().get("Global Quote") or {}
                except (httpx.HTTPError, ValueError) as exc:
                    log.warning("alphavantage: %s non recuperato: %s", ticker, exc)
                    continue
                price = _to_decimal(quote.get("05. price"))
                if price and price > 0:
                    # GLOBAL_QUOTE non espone la valuta: si assume USD, correggibile a mano.
                    out[ticker.upper()] = (price, "USD")
        return out

    async def fetch_fx_rates(self, pairs: list[tuple[str, str]]) -> dict[tuple[str, str], Decimal]:
        out: dict[tuple[str, str], Decimal] = {}
        async with httpx.AsyncClient(timeout=15) as client:
            for base, quote in pairs:
                params = {
                    "function": "CURRENCY_EXCHANGE_RATE",
                    "from_currency": base,
                    "to_currency": quote,
                    "apikey": self._api_key,
                }
                try:
                    response = await client.get(self.base_url, params=params)
                    response.raise_for_status()
                    payload = response.json().get("Realtime Currency Exchange Rate") or {}
                except (httpx.HTTPError, ValueError) as exc:
                    log.warning("alphavantage: cambio %s/%s non recuperato: %s", base, quote, exc)
                    continue
                rate = _to_decimal(payload.get("5. Exchange Rate"))
                if rate and rate > 0:
                    out[(base, quote)] = rate
        return out


def get_provider(
    provider_name: str | None = None, api_key: str | None = None
) -> MarketDataProvider:
    """Provider da usare.

    Senza argomenti legge la configurazione di avvio (Docker secret / variabili). I
    chiamanti che hanno una sessione passano invece la configurazione risolta da
    `app_settings.market_data_config`, che può essere stata cambiata a caldo.
    """
    key = api_key if api_key is not None else settings.market_data_api_key
    provider = (provider_name or settings.market_data_provider or "none").lower()
    if not key or provider in ("none", ""):
        return NullProvider()
    if provider == "twelvedata":
        return TwelveDataProvider(key)
    if provider == "alphavantage":
        return AlphaVantageProvider(key)
    log.warning("provider dati di mercato sconosciuto: %s — uso NullProvider", provider)
    return NullProvider()
