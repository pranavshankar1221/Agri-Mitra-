from sqlalchemy import Column, String, Float, DateTime, ForeignKey
import uuid
from datetime import datetime, timezone
from app.db.base import Base
from sqlalchemy.orm import relationship

def generate_uuid():
    return str(uuid.uuid4())

class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(String, primary_key=True, default=generate_uuid)
    farmer_id = Column(String, ForeignKey("farmers.id"), nullable=True)
    commodity_id = Column(String, ForeignKey("commodities.id"), nullable=False)
    recommendation_type = Column(String, nullable=False) # e.g., SELL_AT_MARKET_B
    recommendation_text = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    risk_level = Column(String, nullable=False) # e.g., LOW, MEDIUM, HIGH
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    farmer = relationship("Farmer")
    commodity = relationship("Commodity")
    sources = relationship("RecommendationSource", back_populates="recommendation", cascade="all, delete-orphan")


class RecommendationSource(Base):
    __tablename__ = "recommendation_sources"

    id = Column(String, primary_key=True, default=generate_uuid)
    recommendation_id = Column(String, ForeignKey("recommendations.id"), nullable=False)
    source_type = Column(String, nullable=False) # e.g., market_api, rag_document
    source_reference = Column(String, nullable=False) # e.g., name of API, or document ID
    source_timestamp = Column(DateTime, nullable=True)
    
    recommendation = relationship("Recommendation", back_populates="sources")
