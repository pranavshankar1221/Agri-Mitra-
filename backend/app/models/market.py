from sqlalchemy import Column, String, Float
import uuid
from app.db.base import Base

def generate_uuid():
    return str(uuid.uuid4())

class Market(Base):
    __tablename__ = "markets"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    state = Column(String, nullable=False)
    district = Column(String, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    source = Column(String, nullable=True)
