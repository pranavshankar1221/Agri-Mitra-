from pydantic import BaseModel
from typing import Any


class MarketPriceRecord(BaseModel):
    state: str | None
    district: str | None
    market: str | None
    commodity: str
    variety: str | None
    grade: str | None = None
    report_date: str
    min_price: float | None
    max_price: float | None
    modal_price: float | None
    unit: str
    source: str
    retrieved_at: str
    source_values: dict[str, Any]


class MarketPricesResponse(BaseModel):
    records: list[MarketPriceRecord]
    count: int
    total: int | None
    limit: int
    offset: int
    source: str
    retrieved_at: str
    history_saved: bool = True
    history_warning: str | None = None


class MarketTrendPoint(BaseModel):
    report_date: str
    average_modal_price: float
    observations: int


class MarketTrendsResponse(BaseModel):
    commodity: str
    market: str | None
    unit: str
    points: list[MarketTrendPoint]
    change_7d_pct: float | None
    change_30d_pct: float | None
    source: str
    retrieved_at: str
