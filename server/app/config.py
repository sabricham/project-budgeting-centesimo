"""Configurazione applicativa.

Regola: i valori non sensibili arrivano da variabili d'ambiente, i **segreti** arrivano
da file montati (Docker secrets). Per ogni segreto esiste la coppia `X_FILE` (percorso)
e `X` (valore diretto, comodo solo in test/dev): il file ha sempre la precedenza.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _read_secret(file_env: str, value_env: str, default: str | None = None) -> str | None:
    """Legge un segreto dal file indicato da `file_env`, con fallback su `value_env`."""
    path = os.getenv(file_env)
    if path:
        p = Path(path)
        if p.is_file():
            content = p.read_text(encoding="utf-8").strip()
            if content:
                return content
    value = os.getenv(value_env)
    if value:
        return value.strip()
    return default


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # --- Database -------------------------------------------------------
    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "money"
    db_user: str = "money_app"

    # --- Applicazione ---------------------------------------------------
    api_prefix: str = "/api/v1"
    base_currency: str = "EUR"
    access_token_minutes: int = 30
    refresh_token_days: int = 30
    jwt_algorithm: str = "HS256"

    # --- Scheduler (§2.7, §2.8, §2.10) ----------------------------------
    run_scheduler: bool = True
    # quanti giorni di occorrenze ricorrenti generare in anticipo
    recurring_horizon_days: int = 90
    # Ora del giorno in cui aggiornare prezzi e storico. Una volta al giorno, non ogni
    # 30 minuti come prima: la serie giornaliera cambia una volta al giorno, e il piano
    # gratuito di Alpha Vantage concede 25 richieste in tutto.
    price_refresh_hour: int = 22

    # Tetto prudenziale di richieste giornaliere verso il provider (la quota vera è 25).
    # Il margine serve agli aggiornamenti su richiesta quando si registra un'operazione.
    market_data_daily_budget: int = 20

    # --- Dati di mercato -------------------------------------------------
    market_data_provider: str = "twelvedata"  # twelvedata | alphavantage | none

    @property
    def database_url(self) -> str:
        password = _read_secret("DB_PASSWORD_FILE", "DB_PASSWORD", "")
        return (
            f"postgresql+asyncpg://{self.db_user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def jwt_secret(self) -> str:
        secret = _read_secret("JWT_SECRET_FILE", "JWT_SECRET")
        if not secret:
            raise RuntimeError(
                "JWT secret mancante: monta ./secrets/jwt_secret.txt oppure imposta JWT_SECRET."
            )
        return secret

    @property
    def market_data_api_key(self) -> str | None:
        return _read_secret("MARKET_DATA_API_KEY_FILE", "MARKET_DATA_API_KEY")


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
