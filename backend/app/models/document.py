from sqlalchemy import Column, String, DateTime, JSON, ForeignKey
import uuid
from datetime import datetime, timezone
from app.db.base import Base

def generate_uuid():
    return str(uuid.uuid4())

class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=generate_uuid)
    title = Column(String, nullable=False)
    source = Column(String, nullable=True)
    document_type = Column(String, nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(String, primary_key=True, default=generate_uuid)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    chunk_text = Column(String, nullable=False)
    # Using JSON to store embedding representation if needed, 
    # but we will likely rely on ChromaDB for actual vector search
    metadata_json = Column(JSON, nullable=True) 
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
