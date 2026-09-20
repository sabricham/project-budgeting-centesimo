from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

from app.core import ratelimit
from app.core.deps import DbSession
from app.core.errors import Unauthorized
from app.core.security import hash_password, verify_password
from app.modules.auth import service
from app.modules.auth.deps import CurrentUser
from app.modules.auth.schemas import (
    ChangePasswordIn,
    LoginIn,
    RefreshIn,
    TokenOut,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_key(request: Request) -> str:
    """IP del chiamante. Dietro nginx e Tailscale Funnel il valore vero è in
    X-Forwarded-For: uvicorn lo traduce in `request.client` grazie a --proxy-headers."""
    return request.client.host if request.client else "sconosciuto"


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, request: Request, session: DbSession) -> dict:
    key = _client_key(request)
    ratelimit.check(key)
    user = await service.authenticate(session, payload.username, payload.password)
    tokens = await service.issue_tokens(session, user)
    await session.commit()
    ratelimit.reset(key)
    return tokens


@router.post("/token", response_model=TokenOut, include_in_schema=False)
async def login_form(
    request: Request,
    session: DbSession,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> dict:
    """Stessa cosa di /login ma in formato form: serve solo alla Swagger UI."""
    return await login(LoginIn(username=form.username, password=form.password), request, session)


@router.post("/refresh", response_model=TokenOut)
async def refresh(payload: RefreshIn, session: DbSession) -> dict:
    tokens = await service.rotate(session, payload.refresh_token)
    await session.commit()
    return tokens


@router.post("/logout", status_code=204, response_model=None)
async def logout(payload: RefreshIn, session: DbSession) -> None:
    await service.revoke_one(session, payload.refresh_token)
    await session.commit()


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/change-password", status_code=204, response_model=None)
async def change_password(payload: ChangePasswordIn, user: CurrentUser, session: DbSession) -> None:
    if not verify_password(payload.current_password, user.password_hash):
        raise Unauthorized("Password attuale errata", code="bad_credentials")
    user.password_hash = hash_password(payload.new_password)
    # Cambiare password chiude ogni sessione, inclusa quella da cui si sta chiamando.
    await service.revoke_all(session, user.id)
    await session.commit()
