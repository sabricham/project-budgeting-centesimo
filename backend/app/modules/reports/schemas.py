from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel


class SeriesPoint(BaseModel):
    date: dt.date
    value: Decimal


class NetWorthSeriesOut(BaseModel):
    date_from: dt.date
    date_to: dt.date
    granularity: str
    opening_balance: Decimal
    closing_balance: Decimal
    points: list[SeriesPoint]


class SummaryOut(BaseModel):
    date_from: dt.date
    date_to: dt.date
    income: Decimal
    expense: Decimal
    investment: Decimal
    #: differenza fra patrimonio di fine e di inizio periodo
    net_change: Decimal
    closing_balance: Decimal
