"""Logica di autenticazione: emissione, rotazione e revoca dei token."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Unauthorized
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    utcnow,
    verify_password,
)
from app.modules.auth.models import RefreshToken, User


async def authenticate(session: AsyncSession, username: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.username == username))
    # Messaggio identico nei due casi: non si rivela se l'utente esiste.
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise Unauthorized("Credenziali non valide", code="bad_credentials")
    return user


async def issue_tokens(session: AsyncSession, user: User) -> dict:
    access, expires_in = create_access_token(user.id, user.username)
    raw, token_hash, expires_at = generate_refresh_token()
    session.add(RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    return {"access_token": access, "refresh_token": raw, "expires_in": expires_in}


async def rotate(session: AsyncSession, raw_token: str) -> dict:
    """Scambia un refresh token con una coppia nuova, revocando il precedente."""
    row = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
    )
    if row is None or row.revoked_at is not None or row.expires_at <= utcnow():
        raise Unauthorized("Sessione scaduta: rifai il login", code="invalid_refresh_token")

    row.revoked_at = utcnow()
    user = await session.scalar(select(User).where(User.id == row.user_id))
    if user is None or not user.is_active:
        raise Unauthorized("Utente non trovato o disattivato", code="invalid_token")
    return await issue_tokens(session, user)


async def revoke_one(session: AsyncSession, raw_token: str) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw_token))
        .where(RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


async def revoke_all(session: AsyncSession, user_id: int) -> None:
    """Usata al cambio password: invalida ogni sessione, compresa quella in corso."""
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
