from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, String, Text, UniqueConstraint

from app.db.base import Base


class MarketObservation(Base):
    __tablename__ = "market_observations"
    __table_args__ = (
        UniqueConstraint("record_key", name="uq_market_observations_record_key"),
    )

    id = Column(String, primary_key=True)
    record_key = Column(String, nullable=False)
    state = Column(String, nullable=True)
    district = Column(String, nullable=True)
    market = Column(String, nullable=True)
    commodity = Column(String, nullable=False)
    variety = Column(String, nullable=True)
    report_date = Column(String, nullable=False)
    min_price = Column(Float, nullable=True)
    max_price = Column(Float, nullable=True)
    modal_price = Column(Float, nullable=True)
    unit = Column(String, nullable=False, default="INR per quintal")
    source = Column(String, nullable=False)
    source_payload = Column(Text, nullable=False)
    retrieved_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
