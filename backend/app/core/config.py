"""Configurazione applicativa.

Regola ereditata dalla v1 e confermata: i valori non sensibili arrivano da variabili
d'ambiente, i **segreti** da file montati (Docker secrets). Per ogni segreto esiste la
coppia `X_FILE` (percorso del file) e `X` (valore diretto, comodo solo nei test):
il file ha sempre la precedenza.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def read_secret(file_env: str, value_env: str, default: str | None = None) -> str | None:
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

    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "centesimo"
    db_user: str = "centesimo"

    api_prefix: str = "/api/v1"
    base_currency: str = "EUR"

    access_token_minutes: int = 60
    refresh_token_days: int = 30
    jwt_algorithm: str = "HS256"

    #: L'app è esposta su internet via Tailscale Funnel: il login è l'unica barriera,
    #: quindi i tentativi vanno limitati. Vedi core/ratelimit.py.
    login_max_attempts: int = 8
    login_window_seconds: int = 300

    #: Origini ammesse dal browser. Vuoto = stessa origine soltanto (il caso normale,
    #: perché nginx serve frontend e API sotto lo stesso host).
    cors_origins: str = ""

    @property
    def database_url(self) -> str:
        password = read_secret("DB_PASSWORD_FILE", "DB_PASSWORD", "") or ""
        return (
            f"postgresql+asyncpg://{self.db_user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def jwt_secret(self) -> str:
        secret = read_secret("JWT_SECRET_FILE", "JWT_SECRET")
        if not secret:
            raise RuntimeError(
                "JWT secret mancante: monta ./secrets/jwt_secret.txt oppure imposta JWT_SECRET."
            )
        return secret


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
