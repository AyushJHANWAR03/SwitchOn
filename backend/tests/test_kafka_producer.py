"""Tests for Kafka producer."""
import pytest
import json
from datetime import datetime
from uuid import UUID
from unittest.mock import Mock, AsyncMock, patch
from app.kafka_producer import KafkaProducerService, create_inspection_event_message
from app.config import LINE_OPTIONS, RESULT_OPTIONS, DEFECT_TYPES


class TestCreateInspectionEventMessage:
    """Tests for creating inspection event messages."""

    def test_create_event_pass(self):
        """Test creating a PASS event message."""
        message = create_inspection_event_message(
            line_id="line-1",
            result="pass",
            confidence=0.95,
            machine_id="machine-1a",
            sku="SKU-12345"
        )

        assert isinstance(message["event_id"], str)
        UUID(message["event_id"])  # Validate it's a UUID
        assert message["line_id"] == "line-1"
        assert message["result"] == "pass"
        assert message["confidence"] == 0.95
        assert message["machine_id"] == "machine-1a"
        assert message["sku"] == "SKU-12345"
        assert message["defect_type"] is None
        assert "timestamp" in message

    def test_create_event_fail(self):
        """Test creating a FAIL event message with defect."""
        message = create_inspection_event_message(
            line_id="line-2",
            result="fail",
            confidence=0.87,
            defect_type="scratch",
            severity="warning"
        )

        assert message["result"] == "fail"
        assert message["defect_type"] == "scratch"
        assert message["severity"] == "warning"

    def test_create_event_auto_timestamp(self):
        """Test automatic timestamp generation."""
        before = datetime.utcnow()
        message = create_inspection_event_message(
            line_id="line-1",
            result="pass"
        )
        after = datetime.utcnow()

        timestamp = datetime.fromisoformat(message["timestamp"].replace('Z', '+00:00'))
        assert before <= timestamp.replace(tzinfo=None) <= after

    def test_create_event_validates_line_id(self):
        """Test validation of line_id."""
        with pytest.raises(ValueError, match="line_id must be one of"):
            create_inspection_event_message(
                line_id="invalid-line",
                result="pass"
            )

    def test_create_event_validates_result(self):
        """Test validation of result."""
        with pytest.raises(ValueError, match="result must be one of"):
            create_inspection_event_message(
                line_id="line-1",
                result="maybe"
            )

    def test_create_event_validates_defect_type(self):
        """Test validation of defect_type."""
        with pytest.raises(ValueError, match="defect_type must be one of"):
            create_inspection_event_message(
                line_id="line-1",
                result="fail",
                defect_type="unknown_defect"
            )


class TestKafkaProducerService:
    """Tests for Kafka producer service."""

    @pytest.fixture
    def mock_producer(self):
        """Mock aiokafka producer."""
        producer = AsyncMock()
        producer.start = AsyncMock()
        producer.stop = AsyncMock()
        producer.send_and_wait = AsyncMock()
        return producer

    @pytest.mark.asyncio
    async def test_init_service(self):
        """Test service initialization."""
        service = KafkaProducerService()
        assert service.topic == "inspection_events"
        assert service.bootstrap_servers == "localhost:19092"

    @pytest.mark.asyncio
    async def test_send_event(self, mock_producer):
        """Test sending an event to Kafka."""
        service = KafkaProducerService()

        with patch('app.kafka_producer.AIOKafkaProducer', return_value=mock_producer):
            await service.start()

            event_data = {
                "event_id": "test-uuid",
                "line_id": "line-1",
                "result": "pass",
                "timestamp": "2024-01-01T12:00:00Z"
            }

            await service.send_event(event_data)

            # Verify producer.send_and_wait was called
            mock_producer.send_and_wait.assert_called_once()
            call_args = mock_producer.send_and_wait.call_args

            assert call_args[0][0] == "inspection_events"  # topic
            sent_data = call_args[0][1]  # message value (dict before serialization)
            assert sent_data["event_id"] == "test-uuid"
            assert sent_data["line_id"] == "line-1"

            await service.stop()

    @pytest.mark.asyncio
    async def test_send_multiple_events(self, mock_producer):
        """Test sending multiple events."""
        service = KafkaProducerService()

        with patch('app.kafka_producer.AIOKafkaProducer', return_value=mock_producer):
            await service.start()

            for i in range(5):
                event_data = create_inspection_event_message(
                    line_id="line-1",
                    result="pass"
                )
                await service.send_event(event_data)

            assert mock_producer.send_and_wait.call_count == 5
            await service.stop()

    @pytest.mark.asyncio
    async def test_send_batch_events(self, mock_producer):
        """Test sending batch of events."""
        service = KafkaProducerService()

        with patch('app.kafka_producer.AIOKafkaProducer', return_value=mock_producer):
            await service.start()

            events = [
                create_inspection_event_message(line_id="line-1", result="pass")
                for _ in range(10)
            ]

            await service.send_batch(events)

            assert mock_producer.send_and_wait.call_count == 10
            await service.stop()

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_producer):
        """Test using service as context manager."""
        with patch('app.kafka_producer.AIOKafkaProducer', return_value=mock_producer):
            async with KafkaProducerService() as service:
                event_data = create_inspection_event_message(
                    line_id="line-1",
                    result="pass"
                )
                await service.send_event(event_data)

            # Verify start and stop were called
            mock_producer.start.assert_called_once()
            mock_producer.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling(self, mock_producer):
        """Test error handling when sending fails."""
        service = KafkaProducerService()
        mock_producer.send_and_wait.side_effect = Exception("Kafka error")

        with patch('app.kafka_producer.AIOKafkaProducer', return_value=mock_producer):
            await service.start()

            with pytest.raises(Exception, match="Kafka error"):
                await service.send_event({"test": "data"})

            await service.stop()
