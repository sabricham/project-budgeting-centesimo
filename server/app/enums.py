"""Enumerazioni condivise fra modelli SQLAlchemy e schemi Pydantic.

Sono `str, Enum` così vanno direttamente in JSON come stringhe leggibili.
A livello DB sono colonne testuali con CHECK constraint (niente ENUM nativi Postgres:
aggiungere un valore richiederebbe una migrazione ALTER TYPE, qui basta cambiare il CHECK).
"""

from __future__ import annotations

from enum import Enum


class AccountType(str, Enum):
    bank = "bank"
    cash = "cash"
    card = "card"
    ewallet = "ewallet"
    investment = "investment"
    savings_goal = "savings_goal"
    liability = "liability"


#: Conti il cui saldo si calcola da initial_balance + movimenti (§2.2).
ASSET_ACCOUNT_TYPES: tuple[str, ...] = (
    AccountType.bank,
    AccountType.cash,
    AccountType.card,
    AccountType.ewallet,
    AccountType.investment,
    AccountType.savings_goal,
)


class CategoryType(str, Enum):
    income = "income"
    expense = "expense"


class TransactionType(str, Enum):
    income = "income"
    expense = "expense"


class TransactionStatus(str, Enum):
    #: generata da una ricorrenza ma non ancora effettiva: NON entra nei saldi (§2.7)
    projected = "projected"
    confirmed = "confirmed"


class Frequency(str, Enum):
    weekly = "weekly"
    monthly = "monthly"
    yearly = "yearly"
    custom_dates = "custom_dates"


class StockTransactionType(str, Enum):
    buy = "buy"
    sell = "sell"
    dividend = "dividend"


class TimeRange(str, Enum):
    day = "day"
    week = "week"
    month = "month"
    year = "year"


class Metric(str, Enum):
    balance = "balance"
    spending = "spending"
    income = "income"
    net_worth = "net_worth"


def values(enum_cls: type[Enum]) -> list[str]:
    """Lista dei valori, usata per costruire i CHECK constraint."""
    return [member.value for member in enum_cls]
