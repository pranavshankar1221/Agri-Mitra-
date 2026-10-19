class AnalyticsService:
    @staticmethod
    def calculate_price_change_pct(current: float, historical: float) -> float:
        if historical == 0:
            return 0.0
        return ((current - historical) / historical) * 100
        
    @staticmethod
    def calculate_opportunity_score(price_change: float, arrival_change: float) -> float:
        # Higher price and lower arrival usually means higher opportunity for a seller
        base_score = 50.0
        score = base_score + (price_change * 1.5) - (arrival_change * 1.0)
        return max(0.0, min(100.0, score))
