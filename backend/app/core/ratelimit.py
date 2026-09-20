"""Limitatore di tentativi per il login.

Serve perché l'applicazione è raggiungibile da internet tramite Tailscale Funnel: l'URL
è pubblico e compare nei log di Certificate Transparency, quindi non è segreto. Il login
è l'unica barriera e va protetto dal tentativo a forza bruta.

Implementazione volutamente minima: finestra scorrevole in memoria. Regge finché l'API
è un solo processo — se un giorno servissero più worker, va spostato su Postgres o Redis.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from app.core.config import settings
from app.core.errors import TooManyRequests

_attempts: dict[str, deque[float]] = defaultdict(deque)


def check(key: str) -> None:
    """Registra un tentativo per `key` (di norma l'IP) e solleva 429 se è troppo frequente."""
    now = time.monotonic()
    window = settings.login_window_seconds
    bucket = _attempts[key]

    while bucket and now - bucket[0] > window:
        bucket.popleft()

    if len(bucket) >= settings.login_max_attempts:
        wait = int(window - (now - bucket[0])) + 1
        raise TooManyRequests(
            f"Troppi tentativi di accesso. Riprova fra {wait} secondi.",
            code="login_rate_limited",
        )

    bucket.append(now)


def reset(key: str) -> None:
    """Da chiamare dopo un login riuscito: chi conosce la password non va penalizzato."""
    _attempts.pop(key, None)
