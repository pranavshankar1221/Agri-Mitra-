class LogisticsService:
    @staticmethod
    def calculate_transport_cost(distance_km: float, quantity_kg: float) -> float:
        # Mock logic: e.g. 5 Rs per km per tonne
        rate_per_km_per_kg = 0.005
        return distance_km * quantity_kg * rate_per_km_per_kg
        
    @staticmethod
    def calculate_net_realization(gross_revenue: float, transport_cost: float, other_costs: float = 0.0) -> float:
        return gross_revenue - transport_cost - other_costs
