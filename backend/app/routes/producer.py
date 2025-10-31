"""Producer API routes."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.kafka_producer import KafkaProducerService, create_inspection_event_message

router = APIRouter()

# Global producer instance (in production, use dependency injection)
producer = None


async def get_producer():
    """Get or create producer instance."""
    global producer
    if producer is None:
        producer = KafkaProducerService()
        await producer.start()
    return producer


class ProduceEventRequest(BaseModel):
    """Request model for producing single event."""
    line_id: str
    result: str
    confidence: Optional[float] = 0.90
    machine_id: Optional[str] = None
    sku: Optional[str] = None
    defect_type: Optional[str] = None
    severity: Optional[str] = None


class ProduceBatchRequest(BaseModel):
    """Request model for producing batch of events."""
    line_id: str
    result: str
    count: int = 10
    confidence: Optional[float] = 0.90
    defect_type: Optional[str] = None
    severity: Optional[str] = None


@router.post("/produce")
async def produce_event(request: ProduceEventRequest):
    """
    Produce a single inspection event to Kafka.

    Args:
        request: Event data

    Returns:
        Created event data
    """
    try:
        # Create event message
        event_data = create_inspection_event_message(
            line_id=request.line_id,
            result=request.result,
            confidence=request.confidence,
            machine_id=request.machine_id,
            sku=request.sku,
            defect_type=request.defect_type,
            severity=request.severity
        )

        # Send to Kafka
        prod = await get_producer()
        await prod.send_event(event_data)

        return event_data

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to produce event: {str(e)}")


@router.post("/produce/batch")
async def produce_batch(request: ProduceBatchRequest):
    """
    Produce batch of inspection events to Kafka.

    Args:
        request: Batch configuration

    Returns:
        Summary of sent events
    """
    try:
        events = []
        for _ in range(request.count):
            event_data = create_inspection_event_message(
                line_id=request.line_id,
                result=request.result,
                confidence=request.confidence,
                defect_type=request.defect_type,
                severity=request.severity
            )
            events.append(event_data)

        # Send batch to Kafka
        prod = await get_producer()
        await prod.send_batch(events)

        return {
            "sent": len(events),
            "line_id": request.line_id,
            "result": request.result
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to produce batch: {str(e)}")
