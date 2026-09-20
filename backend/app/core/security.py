"""Hashing password e token. Funzioni pure: nessun modello, nessun database.

Due token con ruoli distinti (impianto ripreso dalla v1, che funzionava bene):

  * **access_token** — JWT firmato HS256, vita breve. Verificato ad ogni richiesta su
    firma e scadenza, senza toccare il database.
  * **refresh_token** — stringa opaca casuale, vita lunga. Nel database ne salviamo solo
    lo SHA-256, così è **revocabile** (logout, cambio password) — cosa impossibile con un
    JWT autocontenuto — ed è illeggibile anche a chi accedesse al database.

Il refresh token viene ruotato ad ogni uso: il precedente è revocato subito.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.errors import Unauthorized

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACCESS_TOKEN_TYPE = "access"


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd.verify(password, password_hash)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def create_access_token(user_id: int, username: str) -> tuple[str, int]:
    """(jwt, secondi alla scadenza)."""
    expires_in = settings.access_token_minutes * 60
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "type": ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=expires_in)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise Unauthorized("Token non valido o scaduto", code="invalid_token") from exc
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise Unauthorized("Tipo di token non valido", code="invalid_token")
    return payload


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_refresh_token() -> tuple[str, str, dt.datetime]:
    """(token in chiaro, hash da salvare, scadenza)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw), utcnow() + dt.timedelta(days=settings.refresh_token_days)
