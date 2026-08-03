"""Dipendenze FastAPI per l'autenticazione.

`CurrentUser` è l'unica cosa che i router devono conoscere: ogni query di dominio
filtra su `user.id`, così nessun endpoint può restituire dati di un altro utente
(oggi teorico, domani reale se il modello multi-utente viene attivato).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_access_token
from app.config import settings
from app.db import get_session
from app.errors import Unauthorized
from app.models import User

# tokenUrl serve solo alla Swagger UI per il pulsante "Authorize".
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/token")

DbSession = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: DbSession,
) -> User:
    payload = decode_access_token(token)
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise Unauthorized("Token privo di soggetto valido", code="invalid_token") from exc

    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise Unauthorized("Utente non trovato o disattivato", code="invalid_token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
