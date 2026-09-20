"""Fixture dei test.

I test di integrazione girano su un database **separato**, creato al volo e distrutto
alla fine: non toccano mai i dati reali. I test di logica pura non hanno bisogno di
Postgres e girano comunque.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

from app.core.config import settings
from app.core.db import Base
from app.core.security import hash_password

TEST_DB = "centesimo_test"

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _url(database: str) -> str:
    base = settings.database_url
    return base.rsplit("/", 1)[0] + "/" + database


@pytest_asyncio.fixture(scope="session")
async def engine():
    # Il database di test si crea fuori da qualunque transazione: CREATE DATABASE
    # non è transazionale in Postgres.
    admin = create_async_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    await admin.dispose()

    test_engine = create_async_engine(_url(TEST_DB))
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield test_engine
    await test_engine.dispose()

    admin = create_async_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
    await admin.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    """Una sessione pulita per test: le tabelle si svuotano prima di ognuno."""
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        await s.execute(
            text("TRUNCATE entries, accounts, subcategories, categories, users RESTART IDENTITY CASCADE")
        )
        await s.commit()
        yield s


@pytest_asyncio.fixture
async def scenario(session):
    """Utente, una sottocategoria e tre conti con saldo iniziale noto."""
    from app.modules.accounts.models import Account
    from app.modules.auth.models import User
    from app.modules.categories.models import Category, Subcategory

    user = User(username="prova", password_hash=hash_password("x" * 12))
    session.add(user)
    await session.flush()

    category = Category(name="Categoria", position=0)
    session.add(category)
    await session.flush()
    sub = Subcategory(category_id=category.id, name="Sottocategoria", position=0)
    session.add(sub)

    accounts = [
        Account(user_id=user.id, name="Banca", type="bank", initial_balance=Decimal("1000.00")),
        Account(user_id=user.id, name="Contanti", type="cash", initial_balance=Decimal("100.00")),
        Account(user_id=user.id, name="Titoli", type="investment", initial_balance=Decimal("0.00")),
    ]
    session.add_all(accounts)
    await session.commit()

    return {
        "user_id": user.id,
        "sub_id": sub.id,
        "banca": accounts[0].id,
        "contanti": accounts[1].id,
        "titoli": accounts[2].id,
    }


@pytest.fixture
def make_entry(scenario):
    """Costruttore di entry con i riferimenti dello scenario già compilati."""
    from app.modules.entries.models import Entry

    def build(kind: str, amount: str, day: int, *, account: int, to_account: int | None = None):
        return Entry(
            user_id=scenario["user_id"],
            date=dt.date(2026, 3, day),
            description="",
            amount=Decimal(amount),
            kind=kind,
            account_id=account,
            to_account_id=to_account,
            subcategory_id=scenario["sub_id"],
        )

    return build
