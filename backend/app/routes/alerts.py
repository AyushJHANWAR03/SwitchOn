"""Alerts API routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone
from app.database import get_db
from app.models import Alert

router = APIRouter()


class AlertResponse(BaseModel):
    """Alert response model."""
    alert_id: str
    created_at: str
    line_id: str
    severity: str
    value: float
    baseline: Optional[float]
    reason: Optional[str]
    status: str
    acknowledged_by: Optional[str]
    assigned_to: Optional[str]
    resolved_by: Optional[str]
    notes: Optional[str]

    class Config:
        from_attributes = True


class AcknowledgeRequest(BaseModel):
    """Acknowledge alert request."""
    acknowledged_by: str


class AssignRequest(BaseModel):
    """Assign alert request."""
    assigned_to: str


class ResolveRequest(BaseModel):
    """Resolve alert request."""
    resolved_by: str
    notes: Optional[str] = None


@router.get("/alerts", response_model=List[AlertResponse])
async def get_alerts(
    status: Optional[str] = None,
    line_id: Optional[str] = None,
    severity: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get list of alerts with optional filters.

    Args:
        status: Filter by status
        line_id: Filter by line
        severity: Filter by severity
        db: Database session

    Returns:
        List of alerts
    """
    query = db.query(Alert)

    if status:
        query = query.filter(Alert.status == status)
    if line_id:
        query = query.filter(Alert.line_id == line_id)
    if severity:
        query = query.filter(Alert.severity == severity)

    alerts = query.order_by(Alert.created_at.desc()).all()

    return [
        AlertResponse(
            alert_id=str(alert.alert_id),
            created_at=alert.created_at.isoformat(),
            line_id=alert.line_id,
            severity=alert.severity,
            value=alert.value,
            baseline=alert.baseline,
            reason=alert.reason,
            status=alert.status,
            acknowledged_by=alert.acknowledged_by,
            assigned_to=alert.assigned_to,
            resolved_by=alert.resolved_by,
            notes=alert.notes
        )
        for alert in alerts
    ]


@router.get("/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: UUID, db: Session = Depends(get_db)):
    """Get single alert by ID."""
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return AlertResponse(
        alert_id=str(alert.alert_id),
        created_at=alert.created_at.isoformat(),
        line_id=alert.line_id,
        severity=alert.severity,
        value=alert.value,
        baseline=alert.baseline,
        reason=alert.reason,
        status=alert.status,
        acknowledged_by=alert.acknowledged_by,
        assigned_to=alert.assigned_to,
        resolved_by=alert.resolved_by,
        notes=alert.notes
    )


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: UUID,
    request: AcknowledgeRequest,
    db: Session = Depends(get_db)
):
    """Acknowledge an alert."""
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = "acknowledged"
    alert.acknowledged_by = request.acknowledged_by
    alert.acknowledged_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(alert)

    return AlertResponse(
        alert_id=str(alert.alert_id),
        created_at=alert.created_at.isoformat(),
        line_id=alert.line_id,
        severity=alert.severity,
        value=alert.value,
        baseline=alert.baseline,
        reason=alert.reason,
        status=alert.status,
        acknowledged_by=alert.acknowledged_by,
        assigned_to=alert.assigned_to,
        resolved_by=alert.resolved_by,
        notes=alert.notes
    )


@router.post("/alerts/{alert_id}/assign", response_model=AlertResponse)
async def assign_alert(
    alert_id: UUID,
    request: AssignRequest,
    db: Session = Depends(get_db)
):
    """Assign an alert to an operator."""
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.assigned_to = request.assigned_to
    db.commit()
    db.refresh(alert)

    return AlertResponse(
        alert_id=str(alert.alert_id),
        created_at=alert.created_at.isoformat(),
        line_id=alert.line_id,
        severity=alert.severity,
        value=alert.value,
        baseline=alert.baseline,
        reason=alert.reason,
        status=alert.status,
        acknowledged_by=alert.acknowledged_by,
        assigned_to=alert.assigned_to,
        resolved_by=alert.resolved_by,
        notes=alert.notes
    )


@router.post("/alerts/{alert_id}/escalate", response_model=AlertResponse)
async def escalate_alert(alert_id: UUID, db: Session = Depends(get_db)):
    """Escalate an alert."""
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = "escalated"
    db.commit()
    db.refresh(alert)

    return AlertResponse(
        alert_id=str(alert.alert_id),
        created_at=alert.created_at.isoformat(),
        line_id=alert.line_id,
        severity=alert.severity,
        value=alert.value,
        baseline=alert.baseline,
        reason=alert.reason,
        status=alert.status,
        acknowledged_by=alert.acknowledged_by,
        assigned_to=alert.assigned_to,
        resolved_by=alert.resolved_by,
        notes=alert.notes
    )


@router.post("/alerts/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: UUID,
    request: ResolveRequest,
    db: Session = Depends(get_db)
):
    """Resolve an alert."""
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = "resolved"
    alert.resolved_by = request.resolved_by
    alert.resolved_at = datetime.now(timezone.utc)
    alert.notes = request.notes

    db.commit()
    db.refresh(alert)

    return AlertResponse(
        alert_id=str(alert.alert_id),
        created_at=alert.created_at.isoformat(),
        line_id=alert.line_id,
        severity=alert.severity,
        value=alert.value,
        baseline=alert.baseline,
        reason=alert.reason,
        status=alert.status,
        acknowledged_by=alert.acknowledged_by,
        assigned_to=alert.assigned_to,
        resolved_by=alert.resolved_by,
        notes=alert.notes
    )
