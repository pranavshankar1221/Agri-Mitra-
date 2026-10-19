from datetime import datetime, timezone

class MarketDataService:
    @staticmethod
    def get_current_prices(commodity: str, location: str):
        # Mock logic
        return [
            {"market": "Market A", "modal_price": 28.0, "observed_at": datetime.now(timezone.utc).isoformat()},
            {"market": "Market B", "modal_price": 26.5, "observed_at": datetime.now(timezone.utc).isoformat()}
        ]
    
    @staticmethod
    def check_freshness(observed_at: str) -> bool:
        # Mock logic for freshness
        return True
