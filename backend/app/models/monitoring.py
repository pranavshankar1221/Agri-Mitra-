from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey
import uuid
from datetime import datetime, timezone
from app.db.base import Base
from sqlalchemy.orm import relationship

def generate_uuid():
    return str(uuid.uuid4())

class MonitoringRule(Base):
    __tablename__ = "monitoring_rules"

    id = Column(String, primary_key=True, default=generate_uuid)
    farmer_id = Column(String, ForeignKey("farmers.id"), nullable=False)
    commodity_id = Column(String, ForeignKey("commodities.id"), nullable=False)
    market_id = Column(String, ForeignKey("markets.id"), nullable=True)
    condition_type = Column(String, nullable=False) # e.g., price_change_pct
    threshold = Column(Float, nullable=False)
    active = Column(Boolean, default=True)
    last_triggered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    farmer = relationship("Farmer")
    commodity = relationship("Commodity")
    market = relationship("Market")
