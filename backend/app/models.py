"""Database models."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import (
    Column,
    String,
    Float,
    DateTime,
    Text,
    JSON
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import TypeDecorator, CHAR
import uuid as uuid_pkg

Base = declarative_base()


class GUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses PostgreSQL's UUID type, otherwise uses CHAR(36), storing as stringified hex values.
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return value
        else:
            if isinstance(value, uuid_pkg.UUID):
                return str(value)
            return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return value
        else:
            if isinstance(value, uuid_pkg.UUID):
                return value
            return uuid_pkg.UUID(value)


class InspectionEvent(Base):
    """Inspection event model."""

    __tablename__ = "inspection_events"

    event_id = Column(GUID, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    line_id = Column(String(50), nullable=False, index=True)
    machine_id = Column(String(50), nullable=True)
    sku = Column(String(100), nullable=True)
    result = Column(String(10), nullable=False, index=True)  # 'pass' or 'fail'
    confidence = Column(Float, nullable=True)
    defect_type = Column(String(100), nullable=True)
    severity = Column(String(20), nullable=True)

    def __repr__(self):
        return f"<InspectionEvent {self.event_id} {self.line_id} {self.result}>"


class Alert(Base):
    """Alert model."""

    __tablename__ = "alerts"

    alert_id = Column(GUID, primary_key=True)
    created_at = Column(DateTime, nullable=False, index=True)
    line_id = Column(String(50), nullable=False, index=True)
    sku = Column(String(100), nullable=True)
    metric = Column(String(50), nullable=False)
    value = Column(Float, nullable=False)
    baseline = Column(Float, nullable=True)
    severity = Column(String(20), nullable=False, index=True)
    reason = Column(Text, nullable=True)
    evidence = Column(JSON, nullable=True, default=dict)
    status = Column(String(20), nullable=False, default="active", index=True)
    acknowledged_by = Column(String(100), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    assigned_to = Column(String(100), nullable=True)
    resolved_by = Column(String(100), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Alert {self.alert_id} {self.severity} {self.status}>"
