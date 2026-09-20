"""Autenticazione (§1.1).

    POST /auth/login    -> access_token + refresh_token
    POST /auth/token    -> identico, ma con form OAuth2: serve al pulsante
                           "Authorize" della Swagger UI
    POST /auth/refresh  -> nuovo access_token, ruotando il refresh token
    POST /auth/logout   -> revoca il refresh token indicato
    GET  /auth/me       -> profilo dell'utente autenticato
    POST /auth/change-password -> cambia password e revoca TUTTE le sessioni
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, update

from app import schemas
from app.auth.deps import CurrentUser, DbSession
from app.auth.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    utcnow,
    verify_password,
)
from app.errors import Unauthorized
from app.models import RefreshToken, User

router = APIRouter(prefix="/auth", tags=["auth"])


async def _issue_tokens(
    session: DbSession, user: User, client_info: str | None
) -> schemas.TokenPair:
    access_token, expires_in = create_access_token(user.id, user.username)
    raw_refresh, token_hash, expires_at = generate_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            client_info=(client_info or "")[:255] or None,
        )
    )
    await session.commit()
    return schemas.TokenPair(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=expires_in,
    )


async def _authenticate(session: DbSession, username: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.username == username))
    # Verifica sempre un hash, anche se l'utente non esiste: evita di rivelare
    # quali username sono validi misurando i tempi di risposta.
    password_hash = user.password_hash if user else "$2b$12$" + "x" * 53
    ok = verify_password(password, password_hash) if user else False
    if not user or not ok or not user.is_active:
        raise Unauthorized("Credenziali non valide", code="invalid_credentials")
    return user


@router.post("/login", response_model=schemas.TokenPair)
async def login(payload: schemas.LoginRequest, session: DbSession) -> schemas.TokenPair:
    user = await _authenticate(session, payload.username, payload.password)
    return await _issue_tokens(session, user, payload.client_info)


@router.post("/token", response_model=schemas.TokenPair, include_in_schema=False)
async def login_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: DbSession,
    request: Request,
) -> schemas.TokenPair:
    """Variante form-encoded per la Swagger UI."""
    user = await _authenticate(session, form.username, form.password)
    return await _issue_tokens(session, user, request.headers.get("user-agent"))


@router.post("/refresh", response_model=schemas.TokenPair)
async def refresh(payload: schemas.RefreshRequest, session: DbSession) -> schemas.TokenPair:
    token_hash = hash_refresh_token(payload.refresh_token)
    row = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    now = utcnow()
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise Unauthorized("Refresh token non valido o scaduto", code="invalid_refresh_token")

    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Utente non trovato o disattivato", code="invalid_refresh_token")

    # Rotazione: il refresh token usato viene bruciato subito.
    row.revoked_at = now
    return await _issue_tokens(session, user, row.client_info)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def logout(payload: schemas.RefreshRequest, session: DbSession) -> None:
    token_hash = hash_refresh_token(payload.refresh_token)
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await session.commit()


@router.get("/me", response_model=schemas.UserOut)
async def me(user: CurrentUser) -> User:
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def change_password(
    payload: schemas.ChangePasswordRequest, user: CurrentUser, session: DbSession
) -> None:
    if not verify_password(payload.current_password, user.password_hash):
        raise Unauthorized("Password attuale errata", code="invalid_credentials")
    user.password_hash = hash_password(payload.new_password)
    # Cambio password = tutte le sessioni esistenti decadono (§1.1).
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=dt.datetime.now(dt.timezone.utc))
    )
    await session.commit()
