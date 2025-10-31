"""Tests for Kafka consumer."""
import pytest
import json
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, InspectionEvent, Alert
from app.kafka_consumer import (
    KafkaConsumerService,
    parse_event_message,
    persist_event,
    process_message,
    WebSocketManager
)


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestParseEventMessage:
    """Tests for parsing Kafka event messages."""

    def test_parse_valid_message(self):
        """Test parsing a valid event message."""
        message_value = json.dumps({
            "event_id": str(uuid4()),
            "timestamp": "2024-01-01T12:00:00Z",
            "line_id": "line-1",
            "machine_id": "machine-1a",
            "sku": "SKU-12345",
            "result": "pass",
            "confidence": 0.95,
            "defect_type": None,
            "severity": None
        }).encode('utf-8')

        event_data = parse_event_message(message_value)

        assert "event_id" in event_data
        assert event_data["line_id"] == "line-1"
        assert event_data["result"] == "pass"
        assert event_data["confidence"] == 0.95

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON."""
        with pytest.raises(json.JSONDecodeError):
            parse_event_message(b"not valid json")

    def test_parse_missing_required_fields(self):
        """Test parsing message with missing fields."""
        message_value = json.dumps({
            "event_id": str(uuid4()),
            # Missing other required fields
        }).encode('utf-8')

        event_data = parse_event_message(message_value)
        assert "event_id" in event_data
        # Should still parse, validation happens later


class TestPersistEvent:
    """Tests for persisting events to database."""

    def test_persist_valid_event(self, db_session):
        """Test persisting a valid event."""
        event_data = {
            "event_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "line_id": "line-1",
            "machine_id": "machine-1a",
            "sku": "SKU-12345",
            "result": "pass",
            "confidence": 0.95,
            "defect_type": None,
            "severity": None
        }

        event = persist_event(db_session, event_data)

        assert event is not None
        assert event.line_id == "line-1"
        assert event.result == "pass"

        # Verify it's in DB
        retrieved = db_session.query(InspectionEvent).filter_by(
            event_id=event.event_id
        ).first()
        assert retrieved is not None

    def test_persist_fail_event(self, db_session):
        """Test persisting a failure event."""
        event_data = {
            "event_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "line_id": "line-2",
            "machine_id": "machine-2a",
            "sku": "SKU-67890",
            "result": "fail",
            "confidence": 0.87,
            "defect_type": "scratch",
            "severity": "warning"
        }

        event = persist_event(db_session, event_data)

        assert event.result == "fail"
        assert event.defect_type == "scratch"
        assert event.severity == "warning"

    def test_persist_duplicate_event_id(self, db_session):
        """Test handling duplicate event IDs (idempotency)."""
        event_id = uuid4()
        event_data = {
            "event_id": str(event_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "line_id": "line-1",
            "machine_id": "machine-1a",
            "sku": "SKU-TEST",
            "result": "pass",
            "confidence": 0.90
        }

        # Persist first time
        event1 = persist_event(db_session, event_data)
        assert event1 is not None

        # Try to persist again with same event_id
        event2 = persist_event(db_session, event_data)

        # Should handle gracefully (skip or return existing)
        count = db_session.query(InspectionEvent).filter_by(event_id=event_id).count()
        assert count == 1  # Only one record

    def test_persist_invalid_timestamp(self, db_session):
        """Test handling invalid timestamp format."""
        event_data = {
            "event_id": str(uuid4()),
            "timestamp": "invalid-timestamp",
            "line_id": "line-1",
            "result": "pass"
        }

        # Should handle gracefully or raise specific error
        with pytest.raises((ValueError, TypeError)):
            persist_event(db_session, event_data)


class TestProcessMessage:
    """Tests for processing messages (persist + detect)."""

    def test_process_message_creates_event(self, db_session):
        """Test that processing a message creates an event."""
        message_value = json.dumps({
            "event_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "line_id": "line-1",
            "result": "pass",
            "confidence": 0.95
        }).encode('utf-8')

        process_message(db_session, message_value)

        events = db_session.query(InspectionEvent).all()
        assert len(events) == 1

    def test_process_message_triggers_detection(self, db_session):
        """Test that processing triggers detection engine."""
        now = datetime.now(timezone.utc)

        # Create baseline events
        for i in range(50):
            event = InspectionEvent(
                event_id=uuid4(),
                timestamp=now - timedelta(minutes=60 + (i % 10)),
                line_id="line-1",
                machine_id="machine-1a",
                sku="SKU-TEST",
                result="fail" if i < 1 else "pass",
                confidence=0.92
            )
            db_session.add(event)
        db_session.commit()

        # Process messages that should trigger alert (high failure rate)
        for i in range(20):
            message_value = json.dumps({
                "event_id": str(uuid4()),
                "timestamp": (now - timedelta(minutes=i % 10)).isoformat(),
                "line_id": "line-1",
                "result": "fail",  # All failures
                "confidence": 0.85
            }).encode('utf-8')

            process_message(db_session, message_value)

        # Check if alert was created
        alerts = db_session.query(Alert).filter_by(line_id="line-1").all()
        assert len(alerts) >= 1
        assert alerts[0].severity in ["warning", "critical"]

    def test_process_message_respects_cooldown(self, db_session):
        """Test that detection respects cooldown period."""
        now = datetime.now(timezone.utc)

        # Create existing alert
        existing_alert = Alert(
            alert_id=uuid4(),
            created_at=now - timedelta(minutes=2),
            line_id="line-1",
            metric="defect_rate",
            value=0.15,
            baseline=0.03,
            severity="critical",
            reason="Test alert",
            evidence={},
            status="active"
        )
        db_session.add(existing_alert)
        db_session.commit()

        # Process more failures
        for i in range(10):
            message_value = json.dumps({
                "event_id": str(uuid4()),
                "timestamp": now.isoformat(),
                "line_id": "line-1",
                "result": "fail",
                "confidence": 0.85
            }).encode('utf-8')

            process_message(db_session, message_value)

        # Should not create duplicate alert
        alerts = db_session.query(Alert).filter_by(line_id="line-1").all()
        assert len(alerts) == 1  # Only the original alert


class TestWebSocketManager:
    """Tests for WebSocket manager."""

    def test_add_connection(self):
        """Test adding WebSocket connection."""
        manager = WebSocketManager()
        mock_ws = Mock()

        manager.connect(mock_ws)
        assert mock_ws in manager.active_connections

    def test_remove_connection(self):
        """Test removing WebSocket connection."""
        manager = WebSocketManager()
        mock_ws = Mock()

        manager.connect(mock_ws)
        manager.disconnect(mock_ws)
        assert mock_ws not in manager.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_to_connections(self):
        """Test broadcasting message to all connections."""
        manager = WebSocketManager()

        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        manager.connect(mock_ws1)
        manager.connect(mock_ws2)

        message = {"type": "event", "data": {"test": "data"}}
        await manager.broadcast(message)

        mock_ws1.send_json.assert_called_once_with(message)
        mock_ws2.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_handles_disconnected(self):
        """Test broadcast handles disconnected clients."""
        manager = WebSocketManager()

        mock_ws_ok = AsyncMock()
        mock_ws_broken = AsyncMock()
        mock_ws_broken.send_json.side_effect = Exception("Connection closed")

        manager.connect(mock_ws_ok)
        manager.connect(mock_ws_broken)

        message = {"type": "test"}
        await manager.broadcast(message)

        # Should remove broken connection
        assert mock_ws_broken not in manager.active_connections
        assert mock_ws_ok in manager.active_connections


class TestKafkaConsumerService:
    """Tests for Kafka consumer service."""

    @pytest.fixture
    def mock_consumer(self):
        """Mock aiokafka consumer."""
        consumer = AsyncMock()
        consumer.start = AsyncMock()
        consumer.stop = AsyncMock()

        # Mock async iteration
        async def mock_iter():
            # Simulate receiving messages
            for i in range(3):
                mock_msg = MagicMock()
                mock_msg.value = json.dumps({
                    "event_id": str(uuid4()),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "line_id": "line-1",
                    "result": "pass",
                    "confidence": 0.90
                }).encode('utf-8')
                yield mock_msg

        consumer.__aiter__ = lambda self: mock_iter()
        return consumer

    @pytest.mark.asyncio
    async def test_init_service(self):
        """Test service initialization."""
        service = KafkaConsumerService()
        assert service.topic == "inspection_events"
        assert service.bootstrap_servers == "localhost:19092"

    @pytest.mark.asyncio
    async def test_start_stop(self, mock_consumer):
        """Test starting and stopping consumer."""
        service = KafkaConsumerService()

        with patch('app.kafka_consumer.AIOKafkaConsumer', return_value=mock_consumer):
            await service.start()
            mock_consumer.start.assert_called_once()

            await service.stop()
            mock_consumer.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_consume_messages(self, mock_consumer, db_session):
        """Test consuming and processing messages from Kafka."""
        service = KafkaConsumerService()

        with patch('app.kafka_consumer.AIOKafkaConsumer', return_value=mock_consumer):
            await service.start()

            # Manually process the messages
            count = 0
            async for message in service.consume():
                process_message(db_session, message.value)
                count += 1
                if count >= 3:
                    break

            # Verify events were persisted
            events = db_session.query(InspectionEvent).all()
            assert len(events) == 3

            await service.stop()
