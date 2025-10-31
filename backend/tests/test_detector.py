"""Tests for detection engine."""
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, InspectionEvent, Alert
from app.detector import (
    calculate_defect_rate,
    get_baseline_defect_rate,
    determine_severity,
    should_create_alert,
    find_active_alert_in_cooldown,
    create_alert_from_events,
    process_events_for_line
)
from app.config import get_settings

settings = get_settings()


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def create_test_event(line_id, result, minutes_ago=0):
    """Helper to create test inspection events."""
    return InspectionEvent(
        event_id=uuid4(),
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        line_id=line_id,
        machine_id=f"machine-{line_id}a",
        sku="SKU-TEST",
        result=result,
        confidence=0.92
    )


class TestDefectRateCalculation:
    """Tests for defect rate calculation."""

    def test_calculate_defect_rate_all_pass(self, db_session):
        """Test defect rate when all events pass."""
        events = [create_test_event("line-1", "pass", i) for i in range(10)]
        db_session.add_all(events)
        db_session.commit()

        rate = calculate_defect_rate(events)
        assert rate == 0.0

    def test_calculate_defect_rate_all_fail(self, db_session):
        """Test defect rate when all events fail."""
        events = [create_test_event("line-1", "fail", i) for i in range(10)]
        db_session.add_all(events)
        db_session.commit()

        rate = calculate_defect_rate(events)
        assert rate == 1.0

    def test_calculate_defect_rate_mixed(self, db_session):
        """Test defect rate with mixed results."""
        # 3 fails, 7 passes = 30% defect rate
        events = [
            create_test_event("line-1", "fail", 0),
            create_test_event("line-1", "fail", 1),
            create_test_event("line-1", "fail", 2),
        ] + [create_test_event("line-1", "pass", i) for i in range(3, 10)]

        db_session.add_all(events)
        db_session.commit()

        rate = calculate_defect_rate(events)
        assert rate == pytest.approx(0.3, abs=0.01)

    def test_calculate_defect_rate_empty(self, db_session):
        """Test defect rate with no events."""
        rate = calculate_defect_rate([])
        assert rate == 0.0


class TestBaselineCalculation:
    """Tests for baseline defect rate."""

    def test_get_baseline_normal(self, db_session):
        """Test getting baseline defect rate."""
        now = datetime.now(timezone.utc)

        # Create baseline events (60-70 minutes ago): 2% defect rate
        baseline_events = []
        for i in range(100):
            minutes_ago = 60 + (i % 10)
            result = "fail" if i < 2 else "pass"
            event = InspectionEvent(
                event_id=uuid4(),
                timestamp=now - timedelta(minutes=minutes_ago),
                line_id="line-1",
                machine_id="machine-1a",
                sku="SKU-TEST",
                result=result,
                confidence=0.92
            )
            baseline_events.append(event)

        db_session.add_all(baseline_events)
        db_session.commit()

        baseline = get_baseline_defect_rate(
            db_session,
            "line-1",
            baseline_minutes=60
        )
        assert baseline == pytest.approx(0.02, abs=0.01)

    def test_get_baseline_insufficient_data(self, db_session):
        """Test baseline with insufficient events."""
        # Only create 2 events
        now = datetime.now(timezone.utc)
        for i in range(2):
            event = InspectionEvent(
                event_id=uuid4(),
                timestamp=now - timedelta(minutes=65),
                line_id="line-1",
                machine_id="machine-1a",
                sku="SKU-TEST",
                result="pass",
                confidence=0.92
            )
            db_session.add(event)
        db_session.commit()

        baseline = get_baseline_defect_rate(db_session, "line-1")
        assert baseline == 0.0  # Default when insufficient data


class TestSeverityDetermination:
    """Tests for severity classification."""

    def test_severity_info(self):
        """Test INFO severity classification."""
        # 1.5x baseline, meets info threshold
        severity = determine_severity(
            current_rate=0.03,
            baseline_rate=0.02
        )
        assert severity == "info"

    def test_severity_warning(self):
        """Test WARNING severity classification."""
        # 2.5x baseline, exceeds warning threshold
        severity = determine_severity(
            current_rate=0.10,
            baseline_rate=0.04
        )
        assert severity == "warning"

    def test_severity_critical(self):
        """Test CRITICAL severity classification."""
        # 4x baseline, exceeds critical threshold
        severity = determine_severity(
            current_rate=0.16,
            baseline_rate=0.04
        )
        assert severity == "critical"

    def test_severity_absolute_threshold_critical(self):
        """Test CRITICAL based on absolute threshold."""
        # Even with low baseline, high absolute rate = critical
        severity = determine_severity(
            current_rate=0.15,
            baseline_rate=0.01
        )
        assert severity == "critical"

    def test_severity_none_below_thresholds(self):
        """Test no alert when below all thresholds."""
        severity = determine_severity(
            current_rate=0.03,
            baseline_rate=0.025
        )
        assert severity is None


class TestAlertCreationLogic:
    """Tests for alert creation decisions."""

    def test_should_create_alert_true(self):
        """Test should create alert when conditions met."""
        # Current rate 3x baseline with sufficient events
        should_alert = should_create_alert(
            current_rate=0.12,
            baseline_rate=0.04,
            event_count=10
        )
        assert should_alert is True

    def test_should_create_alert_insufficient_events(self):
        """Test no alert with insufficient events."""
        should_alert = should_create_alert(
            current_rate=0.12,
            baseline_rate=0.04,
            event_count=3  # Below MIN_EVENTS
        )
        assert should_alert is False

    def test_should_create_alert_below_threshold(self):
        """Test no alert when below threshold."""
        should_alert = should_create_alert(
            current_rate=0.04,
            baseline_rate=0.035,
            event_count=10
        )
        assert should_alert is False


class TestCooldownLogic:
    """Tests for alert cooldown/deduplication."""

    def test_find_active_alert_in_cooldown(self, db_session):
        """Test finding existing alert within cooldown."""
        now = datetime.now(timezone.utc)

        # Create alert 2 minutes ago
        existing_alert = Alert(
            alert_id=uuid4(),
            created_at=now - timedelta(minutes=2),
            line_id="line-1",
            metric="defect_rate",
            value=0.10,
            baseline=0.03,
            severity="warning",
            reason="Test alert",
            evidence={},
            status="active"
        )
        db_session.add(existing_alert)
        db_session.commit()

        found = find_active_alert_in_cooldown(
            db_session,
            "line-1",
            "defect_rate",
            cooldown_minutes=5
        )
        assert found is not None
        assert found.alert_id == existing_alert.alert_id

    def test_no_alert_outside_cooldown(self, db_session):
        """Test no alert found outside cooldown window."""
        now = datetime.now(timezone.utc)

        # Create alert 10 minutes ago
        old_alert = Alert(
            alert_id=uuid4(),
            created_at=now - timedelta(minutes=10),
            line_id="line-1",
            metric="defect_rate",
            value=0.08,
            baseline=0.02,
            severity="warning",
            reason="Old alert",
            evidence={},
            status="active"
        )
        db_session.add(old_alert)
        db_session.commit()

        found = find_active_alert_in_cooldown(
            db_session,
            "line-1",
            "defect_rate",
            cooldown_minutes=5
        )
        assert found is None

    def test_no_alert_different_line(self, db_session):
        """Test alert not found for different line."""
        now = datetime.now(timezone.utc)

        alert = Alert(
            alert_id=uuid4(),
            created_at=now - timedelta(minutes=2),
            line_id="line-2",
            metric="defect_rate",
            value=0.10,
            baseline=0.03,
            severity="warning",
            reason="Line 2 alert",
            evidence={},
            status="active"
        )
        db_session.add(alert)
        db_session.commit()

        found = find_active_alert_in_cooldown(
            db_session,
            "line-1",  # Searching for line-1
            "defect_rate",
            cooldown_minutes=5
        )
        assert found is None


class TestAlertCreation:
    """Tests for creating alert objects."""

    def test_create_alert_from_events(self, db_session):
        """Test creating alert with evidence."""
        events = [
            create_test_event("line-1", "fail", i)
            for i in range(5)
        ]
        db_session.add_all(events)
        db_session.commit()

        alert = create_alert_from_events(
            line_id="line-1",
            current_rate=0.15,
            baseline_rate=0.05,
            severity="critical",
            events=events
        )

        assert alert.line_id == "line-1"
        assert alert.metric == "defect_rate"
        assert alert.value == 0.15
        assert alert.baseline == 0.05
        assert alert.severity == "critical"
        assert alert.status == "active"
        assert len(alert.evidence["event_ids"]) == 5
        assert "Defect rate" in alert.reason


class TestProcessEventsForLine:
    """Integration tests for processing events."""

    def test_process_events_creates_alert(self, db_session):
        """Test that processing events creates alert when threshold exceeded."""
        now = datetime.now(timezone.utc)

        # Create baseline (60-70 min ago): 2% defect rate
        baseline_events = []
        for i in range(100):
            minutes_ago = 60 + (i % 10)
            result = "fail" if i < 2 else "pass"
            event = InspectionEvent(
                event_id=uuid4(),
                timestamp=now - timedelta(minutes=minutes_ago),
                line_id="line-1",
                machine_id="machine-1a",
                sku="SKU-TEST",
                result=result,
                confidence=0.92
            )
            baseline_events.append(event)

        # Create current window (last 10 min): 12% defect rate (6/50)
        current_events = []
        for i in range(50):
            result = "fail" if i < 6 else "pass"
            event = InspectionEvent(
                event_id=uuid4(),
                timestamp=now - timedelta(minutes=i % 10),
                line_id="line-1",
                machine_id="machine-1a",
                sku="SKU-TEST",
                result=result,
                confidence=0.92
            )
            current_events.append(event)

        db_session.add_all(baseline_events + current_events)
        db_session.commit()

        # Process events
        alert = process_events_for_line(db_session, "line-1")

        assert alert is not None
        assert alert.severity in ["warning", "critical"]
        assert alert.value > alert.baseline

    def test_process_events_no_alert_normal(self, db_session):
        """Test no alert created when defect rate normal."""
        now = datetime.now(timezone.utc)

        # Create baseline events (60-70 min ago): 2% defect rate
        for i in range(50):
            minutes_ago = 60 + (i % 10)
            result = "fail" if i < 1 else "pass"
            event = InspectionEvent(
                event_id=uuid4(),
                timestamp=now - timedelta(minutes=minutes_ago),
                line_id="line-1",
                machine_id="machine-1a",
                sku="SKU-TEST",
                result=result,
                confidence=0.92
            )
            db_session.add(event)

        # Create current events (last 10 min): 2% defect rate (same as baseline)
        for i in range(50):
            result = "fail" if i < 1 else "pass"
            event = InspectionEvent(
                event_id=uuid4(),
                timestamp=now - timedelta(minutes=i % 10),
                line_id="line-1",
                machine_id="machine-1a",
                sku="SKU-TEST",
                result=result,
                confidence=0.92
            )
            db_session.add(event)

        db_session.commit()

        alert = process_events_for_line(db_session, "line-1")
        assert alert is None

    def test_process_events_respects_cooldown(self, db_session):
        """Test cooldown prevents duplicate alerts."""
        now = datetime.now(timezone.utc)

        # Create existing active alert
        existing = Alert(
            alert_id=uuid4(),
            created_at=now - timedelta(minutes=2),
            line_id="line-1",
            metric="defect_rate",
            value=0.15,
            baseline=0.03,
            severity="critical",
            reason="Existing alert",
            evidence={},
            status="active"
        )
        db_session.add(existing)

        # Create events that would trigger alert
        for i in range(20):
            event = InspectionEvent(
                event_id=uuid4(),
                timestamp=now - timedelta(minutes=i % 5),
                line_id="line-1",
                machine_id="machine-1a",
                sku="SKU-TEST",
                result="fail",
                confidence=0.92
            )
            db_session.add(event)

        db_session.commit()

        # Should not create new alert due to cooldown
        alert = process_events_for_line(db_session, "line-1")
        assert alert is None

        # Verify only one alert exists
        alerts = db_session.query(Alert).filter_by(line_id="line-1").all()
        assert len(alerts) == 1
