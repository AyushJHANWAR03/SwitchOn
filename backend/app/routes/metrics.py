"""Metrics API routes."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from app.database import get_db
from app.models import InspectionEvent
from app.detector import calculate_defect_rate

router = APIRouter()


@router.get("/metrics/line/{line_id}")
async def get_line_metrics(line_id: str, db: Session = Depends(get_db)):
    """
    Get current metrics for a production line.

    Args:
        line_id: Production line ID
        db: Database session

    Returns:
        Current metrics for the line
    """
    now = datetime.now(timezone.utc)

    # Last 10 minutes
    window_start = now - timedelta(minutes=10)
    recent_events = db.query(InspectionEvent).filter(
        InspectionEvent.line_id == line_id,
        InspectionEvent.timestamp >= window_start
    ).all()

    # Calculate metrics
    total_inspected = len(recent_events)
    total_failed = sum(1 for e in recent_events if e.result == "fail")
    defect_rate = calculate_defect_rate(recent_events)

    # Last event timestamp
    last_event = db.query(InspectionEvent).filter(
        InspectionEvent.line_id == line_id
    ).order_by(InspectionEvent.timestamp.desc()).first()

    last_updated = last_event.timestamp.isoformat() if last_event else None

    return {
        "line_id": line_id,
        "defect_rate": defect_rate,
        "total_inspected": total_inspected,
        "total_failed": total_failed,
        "window_minutes": 10,
        "last_updated": last_updated
    }


@router.get("/metrics/summary")
async def get_summary_metrics(db: Session = Depends(get_db)):
    """
    Get summary metrics for all lines.

    Returns:
        Summary metrics across all lines
    """
    from app.config import LINE_OPTIONS

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=10)

    summary = {}
    for line_id in LINE_OPTIONS:
        recent_events = db.query(InspectionEvent).filter(
            InspectionEvent.line_id == line_id,
            InspectionEvent.timestamp >= window_start
        ).all()

        summary[line_id] = {
            "total_inspected": len(recent_events),
            "defect_rate": calculate_defect_rate(recent_events),
            "status": "online" if recent_events else "offline"
        }

    return summary
