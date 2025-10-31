"""Kafka consumer service."""
import json
import logging
from datetime import datetime
from typing import Dict, Optional, List
from uuid import UUID
from aiokafka import AIOKafkaConsumer
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models import InspectionEvent, Alert
from app.database import SessionLocal
from app.detector import process_events_for_line
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class WebSocketManager:
    """Manager for WebSocket connections."""

    def __init__(self):
        """Initialize WebSocket manager."""
        self.active_connections: List = []

    def connect(self, websocket):
        """Add a WebSocket connection."""
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: Dict):
        """
        Broadcast message to all connected clients.

        Args:
            message: Message dictionary to broadcast
        """
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to connection: {e}")
                disconnected.append(connection)

        # Remove disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


# Global WebSocket manager instance
ws_manager = WebSocketManager()


def parse_event_message(message_value: bytes) -> Dict:
    """
    Parse Kafka message value to event dictionary.

    Args:
        message_value: Raw message bytes from Kafka

    Returns:
        Event dictionary

    Raises:
        json.JSONDecodeError: If message is not valid JSON
    """
    return json.loads(message_value.decode('utf-8'))


def persist_event(db: Session, event_data: Dict) -> Optional[InspectionEvent]:
    """
    Persist inspection event to database.

    Args:
        db: Database session
        event_data: Event data dictionary

    Returns:
        Created InspectionEvent or None if duplicate

    Raises:
        ValueError: If required fields are missing or invalid
        TypeError: If timestamp format is invalid
    """
    try:
        # Parse timestamp
        timestamp_str = event_data.get("timestamp")
        if timestamp_str:
            # Handle both ISO format with and without 'Z'
            timestamp_str = timestamp_str.replace('Z', '+00:00')
            timestamp = datetime.fromisoformat(timestamp_str)
        else:
            raise ValueError("timestamp is required")

        # Parse UUID
        event_id_str = event_data.get("event_id")
        if not event_id_str:
            raise ValueError("event_id is required")

        event_id = UUID(event_id_str)

        # Create event
        event = InspectionEvent(
            event_id=event_id,
            timestamp=timestamp,
            line_id=event_data["line_id"],
            machine_id=event_data.get("machine_id"),
            sku=event_data.get("sku"),
            result=event_data["result"],
            confidence=event_data.get("confidence"),
            defect_type=event_data.get("defect_type"),
            severity=event_data.get("severity")
        )

        db.add(event)
        db.commit()
        db.refresh(event)

        logger.debug(f"Persisted event {event_id} for {event.line_id}")
        return event

    except IntegrityError as e:
        db.rollback()
        logger.warning(f"Duplicate event_id {event_data.get('event_id')}: {e}")
        return None  # Idempotent - skip duplicates
    except (ValueError, TypeError, KeyError) as e:
        db.rollback()
        logger.error(f"Failed to persist event: {e}")
        raise


def process_message(db: Session, message_value: bytes) -> None:
    """
    Process a Kafka message: parse, persist, detect, broadcast.

    Args:
        db: Database session
        message_value: Raw Kafka message bytes
    """
    try:
        # Parse message
        event_data = parse_event_message(message_value)

        # Persist event
        event = persist_event(db, event_data)
        if event is None:
            return  # Duplicate, skip processing

        # Run detection for this line
        alert = process_events_for_line(db, event.line_id)

        # Broadcast updates via WebSocket (non-blocking)
        # Note: In production, this would be async and use asyncio.create_task
        # For now, we'll handle this in the consumer loop

    except Exception as e:
        logger.error(f"Failed to process message: {e}")
        # In production, send to DLQ (Dead Letter Queue)
        raise


class KafkaConsumerService:
    """Kafka consumer service for processing inspection events."""

    def __init__(self):
        """Initialize Kafka consumer service."""
        self.bootstrap_servers = settings.kafka_bootstrap_servers
        self.topic = settings.kafka_topic_events
        self.group_id = settings.kafka_consumer_group
        self.consumer: Optional[AIOKafkaConsumer] = None

    async def start(self):
        """Start the Kafka consumer."""
        self.consumer = AIOKafkaConsumer(
            self.topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            auto_offset_reset='earliest',  # Start from beginning if no offset
            enable_auto_commit=True,
            value_deserializer=lambda m: m  # Keep as bytes, we'll parse manually
        )
        await self.consumer.start()
        logger.info(f"Kafka consumer started: {self.bootstrap_servers}, topic: {self.topic}")

    async def stop(self):
        """Stop the Kafka consumer."""
        if self.consumer:
            await self.consumer.stop()
            logger.info("Kafka consumer stopped")

    async def consume(self):
        """
        Consume messages from Kafka topic.

        Yields messages as they are received.
        """
        if not self.consumer:
            raise RuntimeError("Consumer not started. Call start() first.")

        try:
            async for message in self.consumer:
                yield message
        except Exception as e:
            logger.error(f"Error consuming messages: {e}")
            raise

    async def run(self):
        """
        Run the consumer loop.

        This is the main entry point for the consumer service.
        """
        await self.start()

        try:
            db = SessionLocal()
            try:
                async for message in self.consume():
                    try:
                        # Process message
                        process_message(db, message.value)

                        # Broadcast to WebSocket clients
                        event_data = parse_event_message(message.value)
                        await ws_manager.broadcast({
                            "type": "event",
                            "data": event_data
                        })

                    except Exception as e:
                        logger.error(f"Failed to process message: {e}")
                        # Continue processing other messages

            finally:
                db.close()

        except KeyboardInterrupt:
            logger.info("Consumer interrupted")
        finally:
            await self.stop()

    async def __aenter__(self):
        """Context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.stop()
