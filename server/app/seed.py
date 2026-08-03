"""Popolamento iniziale del database.

    docker compose exec api python -m app.seed --username sabri --password 'segreta123'
    docker compose exec api python -m app.seed --username sabri            # password generata
    docker compose exec api python -m app.seed --username sabri --demo     # + dati di esempio

È idempotente: rilanciarlo non duplica utente né categorie. Se l'utente esiste già la
password NON viene cambiata (per quello c'è POST /auth/change-password).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import secrets
from decimal import Decimal

from sqlalchemy import select

from app.auth.security import hash_password
from app.db import SessionLocal
from app.enums import AccountType, CategoryType
from app.models import Account, Category, User

#: Categorie di partenza: (nome, tipo, [sotto-categorie])
DEFAULT_CATEGORIES: list[tuple[str, CategoryType, list[str]]] = [
    ("Stipendio", CategoryType.income, []),
    ("Rimborsi", CategoryType.income, []),
    ("Altre entrate", CategoryType.income, []),
    ("Alimentari", CategoryType.expense, ["Supermercato", "Ristoranti e bar"]),
    ("Casa", CategoryType.expense, ["Affitto/Mutuo", "Bollette", "Manutenzione"]),
    ("Trasporti", CategoryType.expense, ["Carburante", "Mezzi pubblici", "Auto"]),
    ("Salute", CategoryType.expense, []),
    ("Abbonamenti", CategoryType.expense, []),
    ("Tempo libero", CategoryType.expense, ["Viaggi", "Shopping"]),
    ("Mutuo/Prestiti", CategoryType.expense, []),
    ("Altre uscite", CategoryType.expense, []),
]


async def seed(username: str, password: str | None, *, demo: bool = False) -> None:
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.username == username))
        generated: str | None = None

        if user is None:
            if not password:
                generated = secrets.token_urlsafe(12)
                password = generated
            user = User(
                username=username,
                password_hash=hash_password(password),
                display_name=username.capitalize(),
            )
            session.add(user)
            await session.flush()
            print(f"[seed] utente '{username}' creato (id={user.id})")
            if generated:
                print(f"[seed] password generata: {generated}   <-- salvala ora")
        else:
            print(f"[seed] utente '{username}' già presente (id={user.id}), password invariata")

        created = 0
        for name, category_type, children in DEFAULT_CATEGORIES:
            parent = await session.scalar(
                select(Category).where(
                    Category.user_id == user.id,
                    Category.name == name,
                    Category.parent_category_id.is_(None),
                )
            )
            if parent is None:
                parent = Category(
                    user_id=user.id, name=name, type=category_type.value, parent_category_id=None
                )
                session.add(parent)
                await session.flush()
                created += 1

            for child_name in children:
                exists = await session.scalar(
                    select(Category.id).where(
                        Category.user_id == user.id,
                        Category.name == child_name,
                        Category.parent_category_id == parent.id,
                    )
                )
                if exists is None:
                    session.add(
                        Category(
                            user_id=user.id,
                            name=child_name,
                            type=category_type.value,
                            parent_category_id=parent.id,
                        )
                    )
                    created += 1

        if created:
            print(f"[seed] {created} categorie create")

        if demo:
            await _seed_demo(session, user)

        await session.commit()
        print("[seed] completato")


async def _seed_demo(session, user: User) -> None:
    """Conti di esempio per provare subito l'app (uno per tipo)."""
    demo_accounts = [
        ("Conto corrente", AccountType.bank, Decimal("2500.00")),
        ("Contanti", AccountType.cash, Decimal("120.00")),
        ("Satispay", AccountType.ewallet, Decimal("50.00")),
        ("Fondo emergenze", AccountType.savings_goal, Decimal("1000.00")),
        ("Broker", AccountType.investment, Decimal("0.00")),
        ("Mutuo casa", AccountType.liability, Decimal("0.00")),
    ]
    for name, account_type, initial in demo_accounts:
        exists = await session.scalar(
            select(Account.id).where(Account.user_id == user.id, Account.name == name)
        )
        if exists is None:
            session.add(
                Account(
                    user_id=user.id,
                    name=name,
                    type=account_type.value,
                    currency="EUR",
                    initial_balance=initial,
                )
            )
    print(f"[seed] conti di esempio creati (data odierna {dt.date.today().isoformat()})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed iniziale di Money App")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", default=None, help="se omessa ne viene generata una")
    parser.add_argument("--demo", action="store_true", help="crea anche conti di esempio")
    args = parser.parse_args()
    asyncio.run(seed(args.username, args.password, demo=args.demo))


if __name__ == "__main__":
    main()
