"""Registro dei moduli di dominio.

**Per aggiungere un dominio**: crea una cartella qui sotto con `models.py`, `schemas.py`,
`service.py`, `router.py` e un `__init__.py` che esporta `router`; poi aggiungila a
`MODULES`. Nient'altro va toccato:

  * `app/main.py` monta i router in ciclo su questa tupla;
  * Alembic vede i modelli perché l'import qui li registra su `Base.metadata`.

L'ordine conta solo per l'ordine delle sezioni nella documentazione Swagger.
"""

from __future__ import annotations

from app.modules import accounts, auth, categories, entries, reports

MODULES = (auth, accounts, categories, entries, reports)

__all__ = ["MODULES"]
