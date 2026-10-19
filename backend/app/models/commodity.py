from sqlalchemy import Column, String
import uuid
from app.db.base import Base

def generate_uuid():
    return str(uuid.uuid4())

class Commodity(Base):
    __tablename__ = "commodities"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False, unique=True)
    category = Column(String, nullable=False)
    unit = Column(String, nullable=False) # e.g., kg, quintal, tonne
