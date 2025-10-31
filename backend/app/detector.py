"""Detection engine for anomaly and alert generation."""
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import uuid4
from sqlalchemy.orm import Session
from app.models import InspectionEvent, Alert
from app.config import get_settings

settings = get_settings()


def calculate_defect_rate(events: List[InspectionEvent]) -> float:
    """
    Calculate defect rate from a list of events.

    Args:
        events: List of inspection events

    Returns:
        Defect rate as float (0.0 to 1.0)
    """
    if not events:
        return 0.0

    total = len(events)
    failures = sum(1 for event in events if event.result == "fail")
    return failures / total


def get_baseline_defect_rate(
    db: Session,
    line_id: str,
    baseline_minutes: int = None
) -> float:
    """
    Calculate baseline defect rate for a line from historical data.

    Args:
        db: Database session
        line_id: Production line ID
        baseline_minutes: How many minutes of history to use

    Returns:
        Baseline defect rate
    """
    if baseline_minutes is None:
        baseline_minutes = settings.baseline_minutes

    # Get events from baseline window
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=baseline_minutes * 2)
    window_end = now - timedelta(minutes=baseline_minutes)

    baseline_events = db.query(InspectionEvent).filter(
        InspectionEvent.line_id == line_id,
        InspectionEvent.timestamp >= window_start,
        InspectionEvent.timestamp < window_end
    ).all()

    # Require minimum events for baseline
    if len(baseline_events) < settings.min_events:
        return 0.0

    return calculate_defect_rate(baseline_events)


def determine_severity(current_rate: float, baseline_rate: float) -> Optional[str]:
    """
    Determine alert severity based on current vs baseline rate.

    Args:
        current_rate: Current defect rate
        baseline_rate: Baseline defect rate

    Returns:
        Severity level ('info', 'warning', 'critical') or None
    """
    # Avoid division by zero
    if baseline_rate == 0:
        baseline_rate = 0.001

    factor = current_rate / baseline_rate

    # Check critical thresholds
    if (factor >= settings.threshold_critical_factor and
        current_rate >= settings.threshold_critical_absolute):
        return "critical"

    # Check warning thresholds
    if (factor >= settings.threshold_warning_factor and
        current_rate >= settings.threshold_warning_absolute):
        return "warning"

    # Check info thresholds
    if (factor >= settings.threshold_info_factor and
        current_rate >= settings.threshold_info_absolute):
        return "info"

    return None


def should_create_alert(
    current_rate: float,
    baseline_rate: float,
    event_count: int
) -> bool:
    """
    Determine if an alert should be created.

    Args:
        current_rate: Current defect rate
        baseline_rate: Baseline defect rate
        event_count: Number of events in current window

    Returns:
        True if alert should be created
    """
    # Must have minimum events
    if event_count < settings.min_events:
        return False

    # Must have severity
    severity = determine_severity(current_rate, baseline_rate)
    return severity is not None


def find_active_alert_in_cooldown(
    db: Session,
    line_id: str,
    metric: str,
    cooldown_minutes: int = None
) -> Optional[Alert]:
    """
    Find existing active alert within cooldown window.

    Args:
        db: Database session
        line_id: Production line ID
        metric: Metric name (e.g., 'defect_rate')
        cooldown_minutes: Cooldown window in minutes

    Returns:
        Existing alert if found, None otherwise
    """
    if cooldown_minutes is None:
        cooldown_minutes = settings.cooldown_minutes

    now = datetime.now(timezone.utc)
    cooldown_start = now - timedelta(minutes=cooldown_minutes)

    existing_alert = db.query(Alert).filter(
        Alert.line_id == line_id,
        Alert.metric == metric,
        Alert.status == "active",
        Alert.created_at >= cooldown_start
    ).first()

    return existing_alert


def create_alert_from_events(
    line_id: str,
    current_rate: float,
    baseline_rate: float,
    severity: str,
    events: List[InspectionEvent]
) -> Alert:
    """
    Create an alert object from events.

    Args:
        line_id: Production line ID
        current_rate: Current defect rate
        baseline_rate: Baseline defect rate
        severity: Alert severity
        events: Events that triggered the alert

    Returns:
        Alert object
    """
    # Collect evidence
    event_ids = [str(event.event_id) for event in events if event.result == "fail"]
    defect_types = list(set(
        event.defect_type for event in events
        if event.defect_type is not None
    ))

    evidence = {
        "event_ids": event_ids[:10],  # Limit to 10 samples
        "defect_types": defect_types,
        "total_inspected": len(events),
        "total_failed": len(event_ids)
    }

    # Generate reason
    factor = current_rate / baseline_rate if baseline_rate > 0 else float('inf')
    reason = (
        f"Defect rate {current_rate:.1%} is {factor:.1f}x baseline ({baseline_rate:.1%}). "
        f"Detected {len(event_ids)} failures in last {settings.window_minutes} minutes."
    )

    alert = Alert(
        alert_id=uuid4(),
        created_at=datetime.now(timezone.utc),
        line_id=line_id,
        metric="defect_rate",
        value=current_rate,
        baseline=baseline_rate,
        severity=severity,
        reason=reason,
        evidence=evidence,
        status="active"
    )

    return alert


def process_events_for_line(
    db: Session,
    line_id: str,
    window_minutes: int = None,
    baseline_minutes: int = None
) -> Optional[Alert]:
    """
    Process events for a line and create alert if needed.

    This is the main detection function that:
    1. Gets recent events in window
    2. Calculates current defect rate
    3. Gets baseline defect rate
    4. Determines if alert should be created
    5. Checks for existing alerts in cooldown
    6. Creates and returns new alert if needed

    Args:
        db: Database session
        line_id: Production line ID
        window_minutes: Current window size in minutes
        baseline_minutes: Baseline window size in minutes

    Returns:
        New alert if created, None otherwise
    """
    if window_minutes is None:
        window_minutes = settings.window_minutes
    if baseline_minutes is None:
        baseline_minutes = settings.baseline_minutes

    now = datetime.now(timezone.utc)

    # Get events in current window
    window_start = now - timedelta(minutes=window_minutes)
    current_events = db.query(InspectionEvent).filter(
        InspectionEvent.line_id == line_id,
        InspectionEvent.timestamp >= window_start
    ).all()

    # Check minimum events
    if len(current_events) < settings.min_events:
        return None

    # Calculate current defect rate
    current_rate = calculate_defect_rate(current_events)

    # Get baseline
    baseline_rate = get_baseline_defect_rate(db, line_id, baseline_minutes)

    # Check if alert should be created
    if not should_create_alert(current_rate, baseline_rate, len(current_events)):
        return None

    # Check for existing alert in cooldown
    existing_alert = find_active_alert_in_cooldown(db, line_id, "defect_rate")
    if existing_alert:
        return None  # Don't create duplicate

    # Determine severity
    severity = determine_severity(current_rate, baseline_rate)
    if severity is None:
        return None

    # Create new alert
    alert = create_alert_from_events(
        line_id=line_id,
        current_rate=current_rate,
        baseline_rate=baseline_rate,
        severity=severity,
        events=current_events
    )

    # Persist alert
    db.add(alert)
    db.commit()
    db.refresh(alert)

    return alert
