"""Kafka producer service."""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4
from aiokafka import AIOKafkaProducer
from app.config import get_settings, LINE_OPTIONS, RESULT_OPTIONS, DEFECT_TYPES

logger = logging.getLogger(__name__)
settings = get_settings()


def create_inspection_event_message(
    line_id: str,
    result: str,
    confidence: float = 0.90,
    machine_id: Optional[str] = None,
    sku: Optional[str] = None,
    defect_type: Optional[str] = None,
    severity: Optional[str] = None
) -> Dict:
    """
    Create an inspection event message.

    Args:
        line_id: Production line ID
        result: Inspection result ('pass' or 'fail')
        confidence: Confidence score (0.0 to 1.0)
        machine_id: Machine identifier
        sku: Stock keeping unit
        defect_type: Type of defect if failed
        severity: Severity level if failed

    Returns:
        Event message dictionary

    Raises:
        ValueError: If validation fails
    """
    # Validate line_id
    if line_id not in LINE_OPTIONS:
        raise ValueError(f"line_id must be one of {LINE_OPTIONS}, got: {line_id}")

    # Validate result
    if result not in RESULT_OPTIONS:
        raise ValueError(f"result must be one of {RESULT_OPTIONS}, got: {result}")

    # Validate defect_type if provided
    if defect_type is not None and defect_type not in DEFECT_TYPES:
        raise ValueError(f"defect_type must be one of {DEFECT_TYPES}, got: {defect_type}")

    # Auto-generate machine_id if not provided
    if machine_id is None:
        machine_id = f"machine-{line_id}a"

    # Generate event
    event = {
        "event_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "line_id": line_id,
        "machine_id": machine_id,
        "sku": sku,
        "result": result,
        "confidence": confidence,
        "defect_type": defect_type,
        "severity": severity
    }

    return event


class KafkaProducerService:
    """Kafka producer service for sending inspection events."""

    def __init__(self):
        """Initialize Kafka producer service."""
        self.bootstrap_servers = settings.kafka_bootstrap_servers
        self.topic = settings.kafka_topic_events
        self.producer: Optional[AIOKafkaProducer] = None

    async def start(self):
        """Start the Kafka producer."""
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            compression_type='gzip',
            acks='all'  # Wait for all replicas
        )
        await self.producer.start()
        logger.info(f"Kafka producer started: {self.bootstrap_servers}")

    async def stop(self):
        """Stop the Kafka producer."""
        if self.producer:
            await self.producer.stop()
            logger.info("Kafka producer stopped")

    async def send_event(self, event_data: Dict) -> None:
        """
        Send a single event to Kafka.

        Args:
            event_data: Event dictionary

        Raises:
            Exception: If send fails
        """
        if not self.producer:
            raise RuntimeError("Producer not started. Call start() first.")

        try:
            await self.producer.send_and_wait(
                self.topic,
                event_data
            )
            logger.debug(f"Sent event {event_data.get('event_id')} to {self.topic}")
        except Exception as e:
            logger.error(f"Failed to send event: {e}")
            raise

    async def send_batch(self, events: List[Dict]) -> None:
        """
        Send a batch of events to Kafka.

        Args:
            events: List of event dictionaries
        """
        for event in events:
            await self.send_event(event)

    async def __aenter__(self):
        """Context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.stop()
