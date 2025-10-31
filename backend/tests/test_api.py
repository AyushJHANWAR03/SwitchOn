"""Essential API tests."""
import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, InspectionEvent, Alert
from app.main import app
from app.database import get_db


@pytest.fixture
def db_session():
    """Create test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def override_get_db(db_session):
    """Override database dependency."""
    def _get_db():
        yield db_session
    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.clear()


class TestProducerAPI:
    """Test producer endpoint."""

    @pytest.mark.asyncio
    async def test_produce_single_event(self, override_get_db):
        """Test producing a single event."""
        mock_producer = AsyncMock()
        mock_producer.send_event = AsyncMock()

        with patch('app.routes.producer.get_producer', return_value=mock_producer):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post("/api/produce", json={
                    "line_id": "line-1",
                    "result": "pass",
                    "confidence": 0.95
                })
                assert response.status_code == 200
                data = response.json()
                assert "event_id" in data
                assert data["line_id"] == "line-1"

    @pytest.mark.asyncio
    async def test_produce_batch_events(self, override_get_db):
        """Test producing batch of events."""
        mock_producer = AsyncMock()
        mock_producer.send_batch = AsyncMock()

        with patch('app.routes.producer.get_producer', return_value=mock_producer):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post("/api/produce/batch", json={
                    "line_id": "line-1",
                    "result": "fail",
                    "count": 10
                })
                assert response.status_code == 200
                data = response.json()
                assert data["sent"] == 10


class TestAlertsAPI:
    """Test alerts CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_get_alerts(self, db_session, override_get_db):
        """Test getting list of alerts."""
        # Create test alert
        alert = Alert(
            alert_id=uuid4(),
            created_at=datetime.now(timezone.utc),
            line_id="line-1",
            metric="defect_rate",
            value=0.15,
            baseline=0.05,
            severity="critical",
            reason="Test alert",
            evidence={},
            status="active"
        )
        db_session.add(alert)
        db_session.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/alerts")
            assert response.status_code == 200
            data = response.json()
            assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_acknowledge_alert(self, db_session, override_get_db):
        """Test acknowledging an alert."""
        alert_id = uuid4()
        alert = Alert(
            alert_id=alert_id,
            created_at=datetime.now(timezone.utc),
            line_id="line-1",
            metric="defect_rate",
            value=0.15,
            baseline=0.05,
            severity="critical",
            reason="Test",
            evidence={},
            status="active"
        )
        db_session.add(alert)
        db_session.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/alerts/{alert_id}/acknowledge",
                json={"acknowledged_by": "operator1"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "acknowledged"

    @pytest.mark.asyncio
    async def test_resolve_alert(self, db_session, override_get_db):
        """Test resolving an alert."""
        alert_id = uuid4()
        alert = Alert(
            alert_id=alert_id,
            created_at=datetime.now(timezone.utc),
            line_id="line-1",
            metric="defect_rate",
            value=0.15,
            baseline=0.05,
            severity="critical",
            reason="Test",
            evidence={},
            status="active"
        )
        db_session.add(alert)
        db_session.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                f"/api/alerts/{alert_id}/resolve",
                json={"resolved_by": "operator1", "notes": "Fixed"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "resolved"


class TestMetricsAPI:
    """Test metrics endpoints."""

    @pytest.mark.asyncio
    async def test_get_line_metrics(self, db_session, override_get_db):
        """Test getting metrics for a line."""
        # Create test events
        now = datetime.now(timezone.utc)
        for i in range(10):
            event = InspectionEvent(
                event_id=uuid4(),
                timestamp=now - timedelta(minutes=i),
                line_id="line-1",
                machine_id="machine-1a",
                sku="SKU-TEST",
                result="fail" if i < 2 else "pass",
                confidence=0.92
            )
            db_session.add(event)
        db_session.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/metrics/line/line-1")
            assert response.status_code == 200
            data = response.json()
            assert "defect_rate" in data
            assert "total_inspected" in data

    @pytest.mark.asyncio
    async def test_get_meta(self, override_get_db):
        """Test getting metadata/enumerations."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/meta")
            assert response.status_code == 200
            data = response.json()
            assert "lines" in data
            assert "severities" in data
