"""Creazione dell'utente iniziale e allineamento del catalogo categorie.

    docker compose exec api python -m app.seed --username sabri --password 'la-tua-password'
    docker compose exec api python -m app.seed --username sabri     # password generata

Idempotente: se l'utente esiste la password **non** viene cambiata (per quello c'è
POST /api/v1/auth/change-password).
"""

from __future__ import annotations

import argparse
import asyncio
import secrets

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.categories.service import sync_catalog

#: L'app è pubblica su internet: una password corta qui sarebbe il punto debole di tutto.
MIN_PASSWORD_LENGTH = 10


async def seed(username: str, password: str | None) -> None:
    async with SessionLocal() as session:
        added = await sync_catalog(session)
        print(f"[seed] catalogo: +{added[0]} categorie, +{added[1]} sottocategorie")

        user = await session.scalar(select(User).where(User.username == username))
        if user is not None:
            print(f"[seed] utente '{username}' già presente (id={user.id}), password invariata")
            return

        generated = None
        if not password:
            generated = secrets.token_urlsafe(12)
            password = generated
        elif len(password) < MIN_PASSWORD_LENGTH:
            raise SystemExit(
                f"[seed] password troppo corta: minimo {MIN_PASSWORD_LENGTH} caratteri. "
                "L'applicazione è raggiungibile da internet."
            )

        session.add(
            User(
                username=username,
                password_hash=hash_password(password),
                display_name=username.capitalize(),
            )
        )
        await session.commit()
        print(f"[seed] utente '{username}' creato")
        if generated:
            print(f"[seed] password generata: {generated}   <-- salvala adesso")


def main() -> None:
    parser = argparse.ArgumentParser(description="Popolamento iniziale di Centesimo")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", default=None)
    args = parser.parse_args()
    asyncio.run(seed(args.username, args.password))


if __name__ == "__main__":
    main()
