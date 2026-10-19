from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.schemas.market import MarketPricesResponse, MarketTrendsResponse
from app.services.gov_market_data_service import (
    GovernmentMarketDataService,
    MarketDataError,
)

router = APIRouter()


def _translate_error(error: MarketDataError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=str(error))


def _validate_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y").strftime("%d/%m/%Y")
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail="date must use YYYY-MM-DD or DD/MM/YYYY format.",
            ) from error


@router.get("/prices", response_model=MarketPricesResponse)
def get_market_prices(
    state: str | None = Query(default=None, max_length=100),
    district: str | None = Query(default=None, max_length=100),
    market: str | None = Query(default=None, max_length=100),
    commodity: str | None = Query(default=None, max_length=100),
    date: str | None = Query(default=None, max_length=10),
    limit: int = Query(default=10, ge=1, le=1000),
    offset: int = Query(default=0, ge=0, le=100000),
    refresh: bool = False,
) -> MarketPricesResponse:
    try:
        return GovernmentMarketDataService.fetch_prices(
            state=state,
            district=district,
            market=market,
            commodity=commodity,
            report_date=_validate_date(date),
            limit=limit,
            offset=offset,
            refresh=refresh,
        )
    except MarketDataError as error:
        raise _translate_error(error) from error


@router.get("/commodities")
def get_commodities(
    limit: int = Query(default=1000, ge=1, le=1000),
    offset: int = Query(default=0, ge=0, le=100000),
) -> dict[str, object]:
    try:
        result = GovernmentMarketDataService.fetch_prices(limit=limit, offset=offset)
    except MarketDataError as error:
        raise _translate_error(error) from error
    return {
        "commodities": sorted({record.commodity for record in result.records}),
        "source": result.source,
        "retrieved_at": result.retrieved_at,
    }


@router.get("/markets")
def get_markets(
    state: str | None = Query(default=None, max_length=100),
    district: str | None = Query(default=None, max_length=100),
    commodity: str | None = Query(default=None, max_length=100),
) -> dict[str, object]:
    try:
        result = GovernmentMarketDataService.fetch_prices(
            state=state,
            district=district,
            commodity=commodity,
            limit=100,
        )
    except MarketDataError as error:
        raise _translate_error(error) from error
    return {
        "markets": sorted({record.market for record in result.records if record.market}),
        "source": result.source,
        "retrieved_at": result.retrieved_at,
    }


@router.get("/trends", response_model=MarketTrendsResponse)
def get_market_trends(
    commodity: str = Query(min_length=1, max_length=100),
    state: str | None = Query(default=None, max_length=100),
    district: str | None = Query(default=None, max_length=100),
    market: str | None = Query(default=None, max_length=100),
    days: int = Query(default=30, ge=1, le=365),
    refresh: bool = False,
) -> MarketTrendsResponse:
    try:
        GovernmentMarketDataService.fetch_prices(
            state=state,
            district=district,
            market=market,
            commodity=commodity,
            limit=1000,
            refresh=refresh,
        )
        return MarketTrendsResponse.model_validate(
            GovernmentMarketDataService.get_trends(
                commodity,
                state=state,
                district=district,
                market=market,
                days=days,
            )
        )
    except MarketDataError as error:
        raise _translate_error(error) from error
