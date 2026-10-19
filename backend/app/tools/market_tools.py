from langchain_core.tools import tool
from app.services.market_data_service import MarketDataService
from app.services.logistics_service import LogisticsService
from app.services.analytics_service import AnalyticsService

@tool
def get_current_prices(commodity: str, location: str):
    """Fetches the current market prices for a commodity near a location."""
    return MarketDataService.get_current_prices(commodity, location)

@tool
def calculate_net_realization(price_per_kg: float, quantity_kg: float, distance_km: float):
    """Calculates the net realization amount after deducting transport costs."""
    gross = price_per_kg * quantity_kg
    cost = LogisticsService.calculate_transport_cost(distance_km, quantity_kg)
    return LogisticsService.calculate_net_realization(gross, cost)

@tool
def calculate_opportunity(price_change_pct: float, arrival_change_pct: float):
    """Calculates a market opportunity score (0-100) based on price and arrival trends."""
    return AnalyticsService.calculate_opportunity_score(price_change_pct, arrival_change_pct)
