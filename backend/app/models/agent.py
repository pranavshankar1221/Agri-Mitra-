from sqlalchemy import Column, String, DateTime, ForeignKey
import uuid
from datetime import datetime, timezone
from app.db.base import Base
from sqlalchemy.orm import relationship

def generate_uuid():
    return str(uuid.uuid4())

class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(String, primary_key=True, default=generate_uuid)
    query = Column(String, nullable=False)
    workflow_type = Column(String, nullable=True)
    status = Column(String, nullable=False, default="started")
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    error = Column(String, nullable=True)
    
    steps = relationship("AgentRunStep", back_populates="agent_run", cascade="all, delete-orphan")

class AgentRunStep(Base):
    __tablename__ = "agent_run_steps"

    id = Column(String, primary_key=True, default=generate_uuid)
    agent_run_id = Column(String, ForeignKey("agent_runs.id"), nullable=False)
    agent_name = Column(String, nullable=False)
    step_name = Column(String, nullable=False)
    input_summary = Column(String, nullable=True)
    output_summary = Column(String, nullable=True)
    status = Column(String, nullable=False, default="started")
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    agent_run = relationship("AgentRun", back_populates="steps")
