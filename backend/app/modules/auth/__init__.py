from app.modules.auth import models  # noqa: F401  (registra le tabelle su Base.metadata)
from app.modules.auth.router import router

__all__ = ["router"]
