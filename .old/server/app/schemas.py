"""Schemi Pydantic v2 = contratto pubblico dell'API.

Convenzione importi (§1.3): tutti i campi monetari sono `Decimal`. Pydantic v2 li
serializza in JSON **come stringhe** (`"10.50"`), mai come float: è esattamente la
convenzione richiesta dal contratto client. In ingresso accetta sia `"10.50"` sia
`10.50`, ma li converte subito in Decimal senza passare da float.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app import enums

Money = Annotated[Decimal, Field(max_digits=18, decimal_places=2)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2)]
Quantity = Annotated[Decimal, Field(max_digits=24, decimal_places=8)]
Price = Annotated[Decimal, Field(max_digits=18, decimal_places=6)]
Currency = Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")]

T = TypeVar("T")


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(Schema, Generic[T]):
    """Risposta paginata standard (§1.2)."""

    items: list[T]
    total: int
    limit: int
    offset: int


class ConcurrencyMixin(BaseModel):
    """Controllo di concorrenza ottimistico opzionale (§1.3).

    Il client può inviare l'`updated_at` che ha letto: se nel frattempo la riga è
    cambiata riceve 409 invece di sovrascrivere le modifiche di un altro dispositivo.
    """

    expected_updated_at: dt.datetime | None = None


# --------------------------------------------------------------------------- #
#  Auth
# --------------------------------------------------------------------------- #


class LoginRequest(Schema):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    client_info: str | None = Field(default=None, max_length=255)


class TokenPair(Schema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Secondi alla scadenza dell'access token")


class RefreshRequest(Schema):
    refresh_token: str


class ChangePasswordRequest(Schema):
    current_password: str
    new_password: str = Field(min_length=8, max_length=256)


class UserOut(Schema):
    id: int
    username: str
    display_name: str | None
    base_currency: str


# --------------------------------------------------------------------------- #
#  Conti
# --------------------------------------------------------------------------- #


class AccountCreate(Schema):
    name: str = Field(min_length=1, max_length=120)
    type: enums.AccountType
    currency: Currency = "EUR"
    initial_balance: Money = Decimal("0")
    icon: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, max_length=9)
    notes: str | None = None


class AccountUpdate(ConcurrencyMixin):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    currency: Currency | None = None
    initial_balance: Money | None = None
    icon: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, max_length=9)
    notes: str | None = None
    archived: bool | None = None


class AccountOut(Schema):
    id: int
    name: str
    type: enums.AccountType
    currency: str
    initial_balance: Money
    icon: str | None
    color: str | None
    archived: bool
    notes: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class AccountWithBalance(AccountOut):
    #: saldo calcolato lato server, mai persistito (§2.2)
    balance: Money
    #: solo per i conti `investment`: quota di saldo non investita (§2.8)
    cash_balance: Money | None = None
    #: solo per i conti `investment`: valore di mercato delle posizioni
    holdings_value: Money | None = None


# --------------------------------------------------------------------------- #
#  Categorie
# --------------------------------------------------------------------------- #


class CategoryCreate(Schema):
    name: str = Field(min_length=1, max_length=120)
    type: enums.CategoryType
    parent_category_id: int | None = None
    icon: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, max_length=9)


class CategoryUpdate(ConcurrencyMixin):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_category_id: int | None = None
    icon: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, max_length=9)
    archived: bool | None = None


class CategoryOut(Schema):
    id: int
    name: str
    type: enums.CategoryType
    parent_category_id: int | None
    icon: str | None
    color: str | None
    archived: bool
    created_at: dt.datetime
    updated_at: dt.datetime


# --------------------------------------------------------------------------- #
#  Budget
# --------------------------------------------------------------------------- #


class BudgetCreate(Schema):
    category_id: int
    amount_limit: PositiveMoney
    active: bool = True


class BudgetUpdate(ConcurrencyMixin):
    amount_limit: PositiveMoney | None = None
    active: bool | None = None


class BudgetOut(Schema):
    id: int
    category_id: int
    category_name: str
    amount_limit: Money
    active: bool
    #: speso nel mese corrente per quella categoria (§2.5) — calcolato dal server
    spent_this_month: Money
    remaining: Money
    #: 0..1+ (può superare 1 se hai sforato)
    usage_ratio: float
    created_at: dt.datetime
    updated_at: dt.datetime


# --------------------------------------------------------------------------- #
#  Transazioni
# --------------------------------------------------------------------------- #


class TransactionCreate(Schema):
    account_id: int
    category_id: int
    type: enums.TransactionType
    amount: PositiveMoney
    date: dt.date
    description: str | None = Field(default=None, max_length=255)
    status: enums.TransactionStatus = enums.TransactionStatus.confirmed


class TransactionUpdate(ConcurrencyMixin):
    account_id: int | None = None
    category_id: int | None = None
    type: enums.TransactionType | None = None
    amount: PositiveMoney | None = None
    date: dt.date | None = None
    description: str | None = Field(default=None, max_length=255)
    status: enums.TransactionStatus | None = None


class TransactionOut(Schema):
    id: int
    account_id: int
    account_name: str | None = None
    category_id: int
    category_name: str | None = None
    type: enums.TransactionType
    amount: Money
    date: dt.date
    description: str | None
    status: enums.TransactionStatus
    source_recurring_id: int | None
    created_at: dt.datetime
    updated_at: dt.datetime


# --------------------------------------------------------------------------- #
#  Trasferimenti
# --------------------------------------------------------------------------- #


class TransferCreate(Schema):
    from_account_id: int
    to_account_id: int
    amount: PositiveMoney
    date: dt.date
    description: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _distinct_accounts(self) -> "TransferCreate":
        if self.from_account_id == self.to_account_id:
            raise ValueError("il conto di origine e quello di destinazione devono essere diversi")
        return self


class TransferUpdate(ConcurrencyMixin):
    from_account_id: int | None = None
    to_account_id: int | None = None
    amount: PositiveMoney | None = None
    date: dt.date | None = None
    description: str | None = Field(default=None, max_length=255)


class TransferOut(Schema):
    id: int
    from_account_id: int
    from_account_name: str | None = None
    to_account_id: int
    to_account_name: str | None = None
    amount: Money
    date: dt.date
    description: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


# --------------------------------------------------------------------------- #
#  Debiti / prestiti
# --------------------------------------------------------------------------- #


class LiabilityUpdateCreate(Schema):
    account_id: int
    residual_amount: Money = Field(ge=0)
    date: dt.date
    note: str | None = Field(default=None, max_length=255)


class LiabilityUpdateOut(Schema):
    id: int
    account_id: int
    residual_amount: Money
    date: dt.date
    note: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


# --------------------------------------------------------------------------- #
#  Obiettivi
# --------------------------------------------------------------------------- #


class GoalCreate(Schema):
    name: str = Field(min_length=1, max_length=120)
    target_amount: PositiveMoney
    target_date: dt.date | None = None
    linked_account_id: int
    icon: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, max_length=9)


class GoalUpdate(ConcurrencyMixin):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_amount: PositiveMoney | None = None
    target_date: dt.date | None = None
    icon: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, max_length=9)


class GoalOut(Schema):
    id: int
    name: str
    target_amount: Money
    target_date: dt.date | None
    linked_account_id: int
    linked_account_name: str | None = None
    icon: str | None
    color: str | None
    #: saldo del conto collegato (§2.9), non un campo salvato
    current_amount: Money
    progress: float
    #: quanto accantonare al mese per arrivare in tempo (null senza target_date)
    monthly_required: Money | None = None
    months_remaining: int | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


# --------------------------------------------------------------------------- #
#  Ricorrenze
# --------------------------------------------------------------------------- #


class RecurringCreate(Schema):
    account_id: int
    category_id: int
    type: enums.TransactionType
    amount: PositiveMoney
    description: str | None = Field(default=None, max_length=255)
    frequency: enums.Frequency
    interval: int = Field(default=1, ge=1, le=99)
    occurrence_days: list[Any] = Field(default_factory=list)
    start_date: dt.date
    end_date: dt.date | None = None
    active: bool = True
    auto_confirm: bool = False

    @model_validator(mode="after")
    def _validate_occurrences(self) -> "RecurringCreate":
        from app.services.recurrence import validate_occurrence_days

        validate_occurrence_days(self.frequency, self.occurrence_days)
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date precedente a start_date")
        return self


class RecurringUpdate(ConcurrencyMixin):
    account_id: int | None = None
    category_id: int | None = None
    amount: PositiveMoney | None = None
    description: str | None = Field(default=None, max_length=255)
    frequency: enums.Frequency | None = None
    interval: int | None = Field(default=None, ge=1, le=99)
    occurrence_days: list[Any] | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    active: bool | None = None
    auto_confirm: bool | None = None


class RecurringOut(Schema):
    id: int
    account_id: int
    account_name: str | None = None
    category_id: int
    category_name: str | None = None
    type: enums.TransactionType
    amount: Money
    description: str | None
    frequency: enums.Frequency
    interval: int
    occurrence_days: list[Any]
    start_date: dt.date
    end_date: dt.date | None
    active: bool
    auto_confirm: bool
    next_occurrence: dt.date | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class ConfirmOccurrenceRequest(Schema):
    """Conferma di un'occorrenza `projected`, con eventuale correzione dell'importo
    (caso tipico: bolletta a importo variabile, §2.7)."""

    amount: PositiveMoney | None = None
    date: dt.date | None = None


# --------------------------------------------------------------------------- #
#  Dashboard
# --------------------------------------------------------------------------- #


class WidgetCreate(Schema):
    type: str = Field(min_length=1, max_length=40)
    position_x: int = Field(default=0, ge=0)
    position_y: int = Field(default=0, ge=0)
    width: int = Field(default=1, ge=1, le=12)
    height: int = Field(default=1, ge=1, le=12)
    config: dict[str, Any] = Field(default_factory=dict)


class WidgetUpdate(ConcurrencyMixin):
    type: str | None = Field(default=None, min_length=1, max_length=40)
    position_x: int | None = Field(default=None, ge=0)
    position_y: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=1, le=12)
    height: int | None = Field(default=None, ge=1, le=12)
    config: dict[str, Any] | None = None


class WidgetOut(Schema):
    id: int
    type: str
    position_x: int
    position_y: int
    width: int
    height: int
    config: dict[str, Any]
    created_at: dt.datetime
    updated_at: dt.datetime


# --------------------------------------------------------------------------- #
#  Portafoglio
# --------------------------------------------------------------------------- #


class StockTransactionCreate(Schema):
    account_id: int
    ticker: str = Field(min_length=1, max_length=24)
    type: enums.StockTransactionType
    quantity: Quantity | None = Field(default=None, gt=0)
    price_per_share: Price | None = Field(default=None, gt=0)
    fees: Money = Field(default=Decimal("0"), ge=0)
    amount: PositiveMoney | None = None
    currency: Currency = "EUR"
    date: dt.date
    notes: str | None = Field(default=None, max_length=255)

    @field_validator("ticker")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="after")
    def _coherent(self) -> "StockTransactionCreate":
        if self.type is enums.StockTransactionType.dividend:
            if self.amount is None:
                raise ValueError("per un dividendo serve `amount`")
        else:
            if self.quantity is None or self.price_per_share is None:
                raise ValueError("per buy/sell servono `quantity` e `price_per_share`")
        return self


class StockTransactionOut(Schema):
    id: int
    account_id: int
    ticker: str
    type: enums.StockTransactionType
    quantity: Quantity | None
    price_per_share: Price | None
    fees: Money
    amount: Money | None
    currency: str
    date: dt.date
    notes: str | None
    realized_pnl: Money | None
    cash_delta: Money
    created_at: dt.datetime


class HoldingOut(Schema):
    id: int
    account_id: int
    ticker: str
    quantity: Quantity
    avg_cost_basis: Price
    currency: str
    #: dati derivati dal PriceCache; `null` se non c'è ancora un prezzo noto
    last_price: Price | None = None
    price_fetched_at: dt.datetime | None = None
    price_source: str | None = None
    market_value: Money | None = None
    cost_value: Money
    unrealized_pnl: Money | None = None
    unrealized_pnl_pct: float | None = None


class PortfolioSummary(Schema):
    account_id: int
    account_name: str
    currency: str
    cash_balance: Money
    holdings_value: Money
    total_value: Money
    total_cost: Money
    unrealized_pnl: Money
    realized_pnl: Money
    holdings: list[HoldingOut]
    #: ticker per cui manca un prezzo: la valorizzazione li considera al costo di carico
    missing_prices: list[str] = Field(default_factory=list)


class PriceIn(Schema):
    price: Price = Field(gt=0)
    currency: Currency = "EUR"


class PriceOut(Schema):
    ticker: str
    price: Price
    currency: str
    fetched_at: dt.datetime
    source: str


class FxRateIn(Schema):
    rate: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=8)]


class FxRateOut(Schema):
    base_currency: str
    quote_currency: str
    rate: Annotated[Decimal, Field(max_digits=18, decimal_places=8)]
    fetched_at: dt.datetime
    source: str


# --------------------------------------------------------------------------- #
#  Report
# --------------------------------------------------------------------------- #


class NetWorthOut(Schema):
    currency: str
    assets: Money
    liabilities: Money
    net_worth: Money
    as_of: dt.date


class TimeseriesPoint(Schema):
    #: inizio del bucket (giorno o mese a seconda del range, §2.11)
    bucket: dt.date
    value: Money


class TimeseriesOut(Schema):
    metric: enums.Metric
    range: enums.TimeRange
    currency: str
    date_from: dt.date
    date_to: dt.date
    points: list[TimeseriesPoint]


class CategoryBreakdownItem(Schema):
    category_id: int
    category_name: str
    parent_category_id: int | None
    total: Money
    share: float


class CategoryBreakdownOut(Schema):
    type: enums.TransactionType
    date_from: dt.date
    date_to: dt.date
    currency: str
    total: Money
    items: list[CategoryBreakdownItem]


# --------------------------------------------------------------------------- #
#  Impostazioni e azzeramento
# --------------------------------------------------------------------------- #


class MarketDataSettingsOut(Schema):
    provider: str
    #: solo le ultime cifre: la chiave salvata non torna mai in chiaro
    api_key_masked: str | None
    api_key_configured: bool
    search_url: str
    signup_url: str
    daily_budget: int | None
    used_today: int


class MarketDataSettingsIn(Schema):
    provider: str | None = Field(default=None, max_length=24)
    #: vuoto o assente = lascia invariata la chiave già salvata
    api_key: str | None = Field(default=None, max_length=128)
    search_url: str | None = Field(default=None, max_length=255)


class ResetRequest(Schema):
    password: str
    #: deve valere "AZZERA": un click distratto non deve poter cancellare tutto
    confirmation: str


class ResetResult(Schema):
    deleted: dict[str, int]
    total: int


class PortfolioHistoryPoint(Schema):
    date: dt.date
    value: Money


class PortfolioHistoryOut(Schema):
    currency: str
    interval_days: int
    points: list[PortfolioHistoryPoint]
    #: ticker senza storico salvato: la curva li ignora invece di fingere uno zero
    missing: list[str] = Field(default_factory=list)


class HealthOut(Schema):
    status: str
    db: str
    version: str
    scheduler: str
