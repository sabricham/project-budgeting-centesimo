"""Fixture di test.

I test di integrazione girano su un database **separato** (`<nome_db>_test`) creato al
volo: non toccano mai i dati reali. Servono un Postgres raggiungibile, quindi si lanciano
dentro il container:

    docker compose exec api pytest

I test di pura logica (`test_recurrence.py`) non hanno bisogno di database e girano
ovunque con `pytest tests/test_recurrence.py`.
"""

from __future__ import annotations

from typing import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.security import hash_password
from app.config import settings
from app.db import Base, get_session
from app.models import User

TEST_DB_NAME = f"{settings.db_name}_test"


def _url(db_name: str) -> str:
    return settings.database_url.rsplit("/", 1)[0] + f"/{db_name}"


async def _ensure_test_database() -> None:
    admin = create_async_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            from sqlalchemy import text

            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB_NAME}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    finally:
        await admin.dispose()


@pytest_asyncio.fixture(scope="session")
async def engine():
    await _ensure_test_database()
    test_engine = create_async_engine(_url(TEST_DB_NAME))
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    """Factory di sessioni su database pulito.

    La pulizia sta qui e non in una fixture `autouse`: così i test di pura logica
    (che non chiedono questa fixture) girano anche senza un Postgres disponibile.
    """
    from sqlalchemy import text

    async with engine.begin() as conn:
        tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncIterator[AsyncClient]:
    from app.main import app

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as http_client:
        yield http_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def user(session_factory) -> User:
    async with session_factory() as session:
        row = User(
            username="tester",
            password_hash=hash_password("password123"),
            display_name="Tester",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


@pytest_asyncio.fixture
async def auth(client: AsyncClient, user: User) -> AsyncClient:
    """Client già autenticato: l'header Authorization è impostato su tutte le richieste."""
    response = await client.post(
        "/api/v1/auth/login", json={"username": "tester", "password": "password123"}
    )
    assert response.status_code == 200, response.text
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return client
