from sqlalchemy import Column, String, Float, DateTime, ForeignKey
import uuid
from datetime import datetime, timezone
from app.db.base import Base
from sqlalchemy.orm import relationship

def generate_uuid():
    return str(uuid.uuid4())

class MarketPrice(Base):
    __tablename__ = "market_prices"

    id = Column(String, primary_key=True, default=generate_uuid)
    commodity_id = Column(String, ForeignKey("commodities.id"), nullable=False)
    market_id = Column(String, ForeignKey("markets.id"), nullable=False)
    min_price = Column(Float, nullable=True)
    modal_price = Column(Float, nullable=False)
    max_price = Column(Float, nullable=True)
    arrival_quantity = Column(Float, nullable=True)
    observed_at = Column(DateTime, nullable=False)
    source = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    commodity = relationship("Commodity")
    market = relationship("Market")
