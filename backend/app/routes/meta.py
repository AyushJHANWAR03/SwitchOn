"""Metadata API routes."""
from fastapi import APIRouter
from app.config import LINE_OPTIONS, SEVERITY_LEVELS, DEFECT_TYPES, RESULT_OPTIONS, ALERT_STATUSES

router = APIRouter()


@router.get("/meta")
async def get_metadata():
    """
    Get metadata and enumerations for the system.

    Returns:
        System enumerations and configuration
    """
    return {
        "lines": LINE_OPTIONS,
        "severities": SEVERITY_LEVELS,
        "defect_types": DEFECT_TYPES,
        "results": RESULT_OPTIONS,
        "alert_statuses": ALERT_STATUSES
    }
