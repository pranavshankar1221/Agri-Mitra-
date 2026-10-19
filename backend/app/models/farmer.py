from sqlalchemy import Column, String, Float, Boolean, DateTime
import uuid
from datetime import datetime, timezone
from app.db.base import Base

def generate_uuid():
    return str(uuid.uuid4())

class Farmer(Base):
    __tablename__ = "farmers"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    location = Column(String, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    land_area = Column(Float, nullable=True) # in acres or hectares
    soil_type = Column(String, nullable=True)
    irrigation = Column(String, nullable=True)
    storage_available = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
