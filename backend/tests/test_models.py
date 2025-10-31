"""Tests for database models."""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, InspectionEvent, Alert


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestInspectionEvent:
    """Tests for InspectionEvent model."""

    def test_create_inspection_event_pass(self, db_session):
        """Test creating a PASS inspection event."""
        event_id = uuid4()
        now = datetime.utcnow()

        event = InspectionEvent(
            event_id=event_id,
            timestamp=now,
            line_id="line-1",
            machine_id="machine-1a",
            sku="SKU-12345",
            result="pass",
            confidence=0.95,
            defect_type=None,
            severity=None
        )

        db_session.add(event)
        db_session.commit()

        retrieved = db_session.query(InspectionEvent).filter_by(event_id=event_id).first()
        assert retrieved is not None
        assert retrieved.event_id == event_id
        assert retrieved.line_id == "line-1"
        assert retrieved.result == "pass"
        assert retrieved.confidence == 0.95
        assert retrieved.defect_type is None

    def test_create_inspection_event_fail(self, db_session):
        """Test creating a FAIL inspection event with defect."""
        event_id = uuid4()
        now = datetime.utcnow()

        event = InspectionEvent(
            event_id=event_id,
            timestamp=now,
            line_id="line-2",
            machine_id="machine-2a",
            sku="SKU-67890",
            result="fail",
            confidence=0.89,
            defect_type="scratch",
            severity="warning"
        )

        db_session.add(event)
        db_session.commit()

        retrieved = db_session.query(InspectionEvent).filter_by(event_id=event_id).first()
        assert retrieved is not None
        assert retrieved.result == "fail"
        assert retrieved.defect_type == "scratch"
        assert retrieved.severity == "warning"

    def test_query_events_by_line_and_result(self, db_session):
        """Test querying events by line_id and result."""
        now = datetime.utcnow()

        # Create multiple events
        events = [
            InspectionEvent(
                event_id=uuid4(),
                timestamp=now - timedelta(minutes=i),
                line_id="line-1",
                machine_id="machine-1a",
                sku="SKU-TEST",
                result="fail" if i % 3 == 0 else "pass",
                confidence=0.90
            )
            for i in range(10)
        ]

        db_session.add_all(events)
        db_session.commit()

        # Query fails on line-1
        fails = db_session.query(InspectionEvent).filter_by(
            line_id="line-1",
            result="fail"
        ).all()

        assert len(fails) == 4  # indices 0, 3, 6, 9

    def test_query_events_by_time_window(self, db_session):
        """Test querying events within a time window."""
        now = datetime.utcnow()

        # Create events spread over 30 minutes
        for i in range(30):
            event = InspectionEvent(
                event_id=uuid4(),
                timestamp=now - timedelta(minutes=i),
                line_id="line-1",
                machine_id="machine-1a",
                sku="SKU-TEST",
                result="pass",
                confidence=0.90
            )
            db_session.add(event)

        db_session.commit()

        # Query last 10 minutes
        window_start = now - timedelta(minutes=10)
        recent_events = db_session.query(InspectionEvent).filter(
            InspectionEvent.timestamp >= window_start
        ).all()

        assert len(recent_events) == 11  # 0-10 minutes inclusive


class TestAlert:
    """Tests for Alert model."""

    def test_create_alert_active(self, db_session):
        """Test creating an active alert."""
        alert_id = uuid4()
        now = datetime.utcnow()

        alert = Alert(
            alert_id=alert_id,
            created_at=now,
            line_id="line-2",
            sku="SKU-12345",
            metric="defect_rate",
            value=0.15,
            baseline=0.05,
            severity="critical",
            reason="Defect rate 3x baseline",
            evidence={"event_ids": [str(uuid4()), str(uuid4())]},
            status="active"
        )

        db_session.add(alert)
        db_session.commit()

        retrieved = db_session.query(Alert).filter_by(alert_id=alert_id).first()
        assert retrieved is not None
        assert retrieved.severity == "critical"
        assert retrieved.status == "active"
        assert retrieved.value == 0.15
        assert retrieved.baseline == 0.05
        assert len(retrieved.evidence["event_ids"]) == 2

    def test_acknowledge_alert(self, db_session):
        """Test acknowledging an alert."""
        alert_id = uuid4()
        now = datetime.utcnow()

        alert = Alert(
            alert_id=alert_id,
            created_at=now,
            line_id="line-2",
            metric="defect_rate",
            value=0.10,
            baseline=0.03,
            severity="warning",
            reason="Elevated defect rate",
            evidence={},
            status="active"
        )

        db_session.add(alert)
        db_session.commit()

        # Acknowledge
        alert.status = "acknowledged"
        alert.acknowledged_by = "operator1"
        alert.acknowledged_at = datetime.utcnow()
        db_session.commit()

        retrieved = db_session.query(Alert).filter_by(alert_id=alert_id).first()
        assert retrieved.status == "acknowledged"
        assert retrieved.acknowledged_by == "operator1"
        assert retrieved.acknowledged_at is not None

    def test_assign_alert(self, db_session):
        """Test assigning an alert to operator."""
        alert = Alert(
            alert_id=uuid4(),
            created_at=datetime.utcnow(),
            line_id="line-1",
            metric="defect_rate",
            value=0.08,
            baseline=0.02,
            severity="warning",
            reason="Test",
            evidence={},
            status="acknowledged"
        )

        db_session.add(alert)
        db_session.commit()

        # Assign
        alert.assigned_to = "operator2"
        db_session.commit()

        retrieved = db_session.query(Alert).first()
        assert retrieved.assigned_to == "operator2"

    def test_resolve_alert(self, db_session):
        """Test resolving an alert."""
        alert = Alert(
            alert_id=uuid4(),
            created_at=datetime.utcnow(),
            line_id="line-3",
            metric="defect_rate",
            value=0.12,
            baseline=0.04,
            severity="critical",
            reason="Spike detected",
            evidence={},
            status="escalated"
        )

        db_session.add(alert)
        db_session.commit()

        # Resolve
        alert.status = "resolved"
        alert.resolved_by = "operator3"
        alert.resolved_at = datetime.utcnow()
        alert.notes = "Fixed sensor calibration"
        db_session.commit()

        retrieved = db_session.query(Alert).first()
        assert retrieved.status == "resolved"
        assert retrieved.resolved_by == "operator3"
        assert retrieved.notes == "Fixed sensor calibration"
        assert retrieved.resolved_at is not None

    def test_query_active_alerts(self, db_session):
        """Test querying only active alerts."""
        now = datetime.utcnow()

        # Create alerts with different statuses
        alerts = [
            Alert(
                alert_id=uuid4(),
                created_at=now,
                line_id=f"line-{i % 4 + 1}",
                metric="defect_rate",
                value=0.10,
                baseline=0.03,
                severity="warning",
                reason="Test",
                evidence={},
                status=["active", "acknowledged", "escalated", "resolved"][i % 4]
            )
            for i in range(12)
        ]

        db_session.add_all(alerts)
        db_session.commit()

        # Query active alerts
        active_alerts = db_session.query(Alert).filter_by(status="active").all()
        assert len(active_alerts) == 3

    def test_query_alerts_by_severity(self, db_session):
        """Test querying alerts by severity."""
        now = datetime.utcnow()

        severities = ["info", "warning", "critical"]
        for i, sev in enumerate(severities * 3):
            alert = Alert(
                alert_id=uuid4(),
                created_at=now,
                line_id="line-1",
                metric="defect_rate",
                value=0.05 * (i + 1),
                baseline=0.02,
                severity=sev,
                reason="Test",
                evidence={},
                status="active"
            )
            db_session.add(alert)

        db_session.commit()

        critical_alerts = db_session.query(Alert).filter_by(severity="critical").all()
        assert len(critical_alerts) == 3

    def test_evidence_json_storage(self, db_session):
        """Test storing complex evidence as JSON."""
        alert = Alert(
            alert_id=uuid4(),
            created_at=datetime.utcnow(),
            line_id="line-2",
            metric="defect_rate",
            value=0.20,
            baseline=0.05,
            severity="critical",
            reason="Multiple defects detected",
            evidence={
                "event_ids": [str(uuid4()) for _ in range(5)],
                "defect_types": ["scratch", "dent", "scratch"],
                "sample_images": ["img1.jpg", "img2.jpg"],
                "metadata": {
                    "shift": "morning",
                    "operator_id": "OP-001"
                }
            },
            status="active"
        )

        db_session.add(alert)
        db_session.commit()

        retrieved = db_session.query(Alert).first()
        assert len(retrieved.evidence["event_ids"]) == 5
        assert retrieved.evidence["defect_types"][0] == "scratch"
        assert retrieved.evidence["metadata"]["shift"] == "morning"
