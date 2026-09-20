"""Hashing password e gestione token (§1.1).

Due token con ruoli distinti:

  * **access_token** — JWT firmato HS256, vita breve (default 30 min). Verificato ad ogni
    richiesta solo su firma+scadenza, senza toccare il DB.
  * **refresh_token** — stringa opaca casuale, vita lunga (default 30 giorni). Nel DB ne
    salviamo solo lo SHA-256, così è revocabile (logout, cambio password) e illeggibile
    anche a chi accedesse al database.

Il refresh token viene **ruotato** ad ogni uso: quello vecchio è revocato subito.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.errors import Unauthorized

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACCESS_TOKEN_TYPE = "access"


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def create_access_token(user_id: int, username: str) -> tuple[str, int]:
    """Restituisce (jwt, secondi_alla_scadenza)."""
    expires_in = settings.access_token_minutes * 60
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "type": ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=expires_in)).timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise Unauthorized("Token non valido o scaduto", code="invalid_token") from exc
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise Unauthorized("Tipo di token non valido", code="invalid_token")
    return payload


def generate_refresh_token() -> tuple[str, str, dt.datetime]:
    """Restituisce (token_in_chiaro, hash_da_salvare, scadenza)."""
    raw = secrets.token_urlsafe(48)
    expires_at = utcnow() + dt.timedelta(days=settings.refresh_token_days)
    return raw, hash_refresh_token(raw), expires_at


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
