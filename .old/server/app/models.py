"""Modelli SQLAlchemy 2.0.

Convenzioni (§1.3):
  * denaro   -> NUMERIC(18, 2)  (mai FLOAT)
  * quantità -> NUMERIC(24, 8)  (frazioni di azione / ETF)
  * prezzi   -> NUMERIC(18, 6)
  * istanti  -> TIMESTAMP WITH TIME ZONE in UTC
  * date     -> DATE (la data contabile non ha fuso orario)

Ogni tabella di dominio porta `user_id`: il modello è predisposto al multi-utente
(§0) anche se oggi l'utente è uno solo. Non c'è nessuna logica multi-utente oltre al
filtro implicito sull'utente del token.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app import enums
from app.db import Base

MONEY = Numeric(18, 2)
QUANTITY = Numeric(24, 8)
PRICE = Numeric(18, 6)
FX_RATE = Numeric(18, 8)


def _check(column: str, enum_cls: type) -> str:
    allowed = ", ".join(f"'{v}'" for v in enums.values(enum_cls))
    return f"{column} IN ({allowed})"


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: usato per rilevare modifiche concorrenti (§1.3): le PATCH possono passare
    #: `expected_updated_at` e ricevere 409 invece di sovrascrivere in silenzio.
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# --------------------------------------------------------------------------- #
#  Utenti e sessioni
# --------------------------------------------------------------------------- #


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    #: hash bcrypt — la password in chiaro non viene mai salvata né loggata (§1.1)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class RefreshToken(Base):
    """Refresh token opaco (§1.1).

    Nel DB finisce solo lo SHA-256 del token: se il database venisse letto, i token
    non sarebbero riutilizzabili. La riga esiste per poterli **revocare** davvero
    (logout, cambio password) — cosa impossibile con un JWT autocontenuto.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    client_info: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# --------------------------------------------------------------------------- #
#  Conti, categorie, budget
# --------------------------------------------------------------------------- #


class Account(TimestampMixin, Base):
    """Conto (§2.2).

    Il saldo NON è una colonna: per i tipi asset si calcola da
    `initial_balance + Σ transazioni + Σ trasferimenti (+ Σ operazioni titoli)`,
    per i `liability` è l'ultimo `LiabilityUpdate.residual_amount` (§2.10).
    Vedi `app/services/balances.py`.
    """

    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(_check("type", enums.AccountType), name="ck_accounts_type"),
        UniqueConstraint("user_id", "name", name="uq_accounts_user_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    initial_balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    icon: Mapped[str | None] = mapped_column(String(64))
    color: Mapped[str | None] = mapped_column(String(9))
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class Category(TimestampMixin, Base):
    """Categoria di entrata/uscita, con sotto-categorie via self-FK (§2.4)."""

    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint(_check("type", enums.CategoryType), name="ck_categories_type"),
        UniqueConstraint("user_id", "name", "parent_category_id", name="uq_categories_user_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    parent_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    icon: Mapped[str | None] = mapped_column(String(64))
    color: Mapped[str | None] = mapped_column(String(9))
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    children: Mapped[list["Category"]] = relationship(lazy="noload")


class Budget(TimestampMixin, Base):
    """Limite di spesa mensile per categoria (§2.5).

    Un solo budget corrente per categoria (vincolo UNIQUE): non c'è storico dei limiti
    passati — scelta esplicita per l'MVP, si aggiunge in futuro con una `BudgetHistory`.
    """

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("category_id", name="uq_budgets_category"),
        CheckConstraint("amount_limit > 0", name="ck_budgets_amount_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    amount_limit: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# --------------------------------------------------------------------------- #
#  Movimenti
# --------------------------------------------------------------------------- #


class Transaction(TimestampMixin, Base):
    """Entrata o uscita su un conto (§2.6).

    `status = projected` identifica le occorrenze generate in anticipo da una
    ricorrenza: sono visibili ("prossime spese in arrivo") ma **non** entrano nei saldi
    né nei report finché non vengono confermate.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint(_check("type", enums.TransactionType), name="ck_transactions_type"),
        CheckConstraint(_check("status", enums.TransactionStatus), name="ck_transactions_status"),
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        Index("ix_transactions_user_date", "user_id", "date"),
        Index("ix_transactions_account_date", "account_id", "date"),
        UniqueConstraint(
            "source_recurring_id", "date", name="uq_transactions_recurring_occurrence"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default=enums.TransactionStatus.confirmed.value
    )
    #: collega la transazione all'abbonamento che l'ha generata (§2.6)
    source_recurring_id: Mapped[int | None] = mapped_column(
        ForeignKey("recurring_transactions.id", ondelete="SET NULL")
    )
    #: soft-delete: lo storico non si perde
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Transfer(TimestampMixin, Base):
    """Spostamento di denaro fra due conti propri (§2.3).

    Non è né entrata né uscita: non ha categoria e non compare nei report di spesa,
    ma muove il saldo di entrambi i conti.
    """

    __tablename__ = "transfers"
    __table_args__ = (
        CheckConstraint("from_account_id <> to_account_id", name="ck_transfers_distinct_accounts"),
        CheckConstraint("amount > 0", name="ck_transfers_amount_positive"),
        Index("ix_transfers_user_date", "user_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    to_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class LiabilityUpdate(TimestampMixin, Base):
    """Snapshot del capitale residuo di un conto `liability` (§2.10)."""

    __tablename__ = "liability_updates"
    __table_args__ = (
        CheckConstraint("residual_amount >= 0", name="ck_liability_residual_non_negative"),
        Index("ix_liability_updates_account_date", "account_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    residual_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255))


# --------------------------------------------------------------------------- #
#  Ricorrenze
# --------------------------------------------------------------------------- #


class RecurringTransaction(TimestampMixin, Base):
    """Definizione di un abbonamento / bolletta ricorrente (§2.7)."""

    __tablename__ = "recurring_transactions"
    __table_args__ = (
        CheckConstraint(_check("type", enums.TransactionType), name="ck_recurring_type"),
        CheckConstraint(_check("frequency", enums.Frequency), name="ck_recurring_frequency"),
        CheckConstraint("interval >= 1", name="ck_recurring_interval_positive"),
        CheckConstraint("amount > 0", name="ck_recurring_amount_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    frequency: Mapped[str] = mapped_column(String(16), nullable=False)
    interval: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: forma dipendente da `frequency`, vedi app/services/recurrence.py
    #:   monthly -> [1, 15] | weekly -> [0, 3] | yearly -> [{"month":1,"day":1}]
    #:   custom_dates -> ["2026-03-01", ...]
    occurrence_days: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: se true l'occorrenza diventa `confirmed` alla data, altrimenti resta da confermare
    #: (utile per bollette a importo variabile)
    auto_confirm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


# --------------------------------------------------------------------------- #
#  Obiettivi di risparmio
# --------------------------------------------------------------------------- #


class Goal(TimestampMixin, Base):
    """Obiettivo di risparmio sovrapposto a un conto `savings_goal` (§2.9).

    `current_amount` non è persistito: è il saldo del conto collegato. Un conto può
    essere collegato a un solo obiettivo alla volta (UNIQUE su linked_account_id).
    """

    __tablename__ = "goals"
    __table_args__ = (
        UniqueConstraint("linked_account_id", name="uq_goals_linked_account"),
        CheckConstraint("target_amount > 0", name="ck_goals_target_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    target_date: Mapped[dt.date | None] = mapped_column(Date)
    linked_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    icon: Mapped[str | None] = mapped_column(String(64))
    color: Mapped[str | None] = mapped_column(String(9))


# --------------------------------------------------------------------------- #
#  Dashboard
# --------------------------------------------------------------------------- #


class DashboardWidget(TimestampMixin, Base):
    """Widget della home (§2.11).

    `config` è JSONB libero: ogni tipo di widget ha impostazioni diverse e aggiungerne
    uno nuovo non deve richiedere una migrazione.
    """

    __tablename__ = "dashboard_widgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    position_x: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    position_y: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


# --------------------------------------------------------------------------- #
#  Portafoglio investimenti
# --------------------------------------------------------------------------- #


class Holding(TimestampMixin, Base):
    """Posizione aperta su un titolo (§2.8).

    `quantity` e `avg_cost_basis` sono derivati dalle `StockTransaction` ma vengono
    mantenuti qui in forma aggregata: ricalcolare la media ponderata di carico ad ogni
    lettura richiederebbe di riprocessare tutto lo storico ordinato.
    """

    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("account_id", "ticker", name="uq_holdings_account_ticker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False, default=0)
    avg_cost_basis: Mapped[Decimal] = mapped_column(PRICE, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")


class StockTransaction(TimestampMixin, Base):
    """Operazione su titoli: acquisto, vendita o dividendo (§2.8).

    Muove sempre la **liquidità** del conto `investment` di appartenenza; per le vendite
    salva la plus/minusvalenza realizzata calcolata sull'`avg_cost_basis` del momento.
    """

    __tablename__ = "stock_transactions"
    __table_args__ = (
        CheckConstraint(_check("type", enums.StockTransactionType), name="ck_stock_tx_type"),
        Index("ix_stock_transactions_account_date", "account_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(24), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(QUANTITY)
    price_per_share: Mapped[Decimal | None] = mapped_column(PRICE)
    fees: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    #: valorizzato solo per i dividendi
    amount: Mapped[Decimal | None] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(255))
    #: plus/minusvalenza realizzata, solo per `sell`
    realized_pnl: Mapped[Decimal | None] = mapped_column(MONEY)
    #: effetto netto sulla liquidità del conto (negativo per gli acquisti)
    cash_delta: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)


class PriceCache(Base):
    """Ultimo prezzo noto per ticker (§2.8).

    L'API esterna non viene MAI chiamata sul path di una richiesta utente: la aggiorna
    un job schedulato e la UI legge solo da qui.
    """

    __tablename__ = "price_cache"

    ticker: Mapped[str] = mapped_column(String(24), primary_key=True)
    price: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: provider che ha fornito il dato, oppure "manual"
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="manual")
    #: "stock" | "crypto" | "unknown". Azioni e cripto hanno endpoint diversi: memorizzare
    #: l'esito del primo tentativo evita di sprecare una richiesta al giorno per indovinare.
    asset_kind: Mapped[str] = mapped_column(String(8), nullable=False, default="unknown")


class AppSetting(Base):
    """Impostazioni modificabili a caldo, in coppie chiave/valore.

    **Deroga esplicita a §3.1**, approvata: la chiave API dei dati di mercato era un
    Docker secret letto all'avvio, e cambiarla richiedeva di riavviare il container.
    Qui può essere impostata dall'applicazione. Il file di secret resta il valore di
    partenza: se in tabella non c'è nulla, si continua a leggere da lì.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc)
    )


class PriceHistory(Base):
    """Serie storica giornaliera dei prezzi, una riga per ticker e giorno.

    È l'archivio locale che rende il grafico indipendente dal provider: la UI legge solo
    da qui, quindi cambiare intervallo o riaprire la pagina non costa nessuna chiamata.

    Serve anche ad aggirare il limite del piano gratuito: Alpha Vantage restituisce una
    finestra di ~100 giorni per richiesta, ma conservando ogni giorno la nostra copia lo
    storico si accumula e non viene mai perso.
    """

    __tablename__ = "price_history"

    ticker: Mapped[str] = mapped_column(String(24), primary_key=True)
    #: giorno di borsa a cui si riferisce la chiusura
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    close: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="manual")


class ApiBudget(Base):
    """Consumo giornaliero di chiamate verso il provider dei dati di mercato.

    Il piano gratuito di Alpha Vantage concede 25 richieste al giorno: senza un contatore
    l'applicazione può bruciare la quota e restare cieca fino al giorno dopo. Qui si tiene
    il conto e si smette **prima** del tetto, degradando sui dati già in cache.
    """

    __tablename__ = "api_budget"

    day: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    provider: Mapped[str] = mapped_column(String(24), primary_key=True)
    used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class FxRateCache(Base):
    """Tasso di cambio cachato, usato solo in fase di aggregazione (§2.8)."""

    __tablename__ = "fx_rate_cache"

    base_currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    quote_currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    rate: Mapped[Decimal] = mapped_column(FX_RATE, nullable=False)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="manual")


class NetWorthSnapshot(Base):
    """Fotografia giornaliera del patrimonio netto (§2.10).

    Serve la serie storica: il patrimonio passato non è ricostruibile a posteriori
    perché dipende dai prezzi di mercato e dagli snapshot dei debiti di quel giorno.
    """

    __tablename__ = "net_worth_snapshots"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_net_worth_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    assets: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    liabilities: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    net_worth: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
