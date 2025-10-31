"""Seed database with baseline data."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, InspectionEvent
from app.config import get_settings, LINE_OPTIONS

settings = get_settings()


def seed_baseline_data():
    """Seed database with baseline events for each line."""
    print("🌱 Seeding database with baseline data...")

    # Create engine and session
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        now = datetime.now(timezone.utc)

        # Create baseline events for each line (60-120 minutes ago)
        # This gives us historical data to establish baseline defect rates
        events = []

        for line_id in LINE_OPTIONS:
            print(f"  Seeding {line_id}...")

            # Create 200 events per line over the past 2 hours
            for i in range(200):
                minutes_ago = 60 + (i % 60)  # Between 60-120 minutes ago

                # 2% baseline defect rate
                result = "fail" if i % 50 == 0 else "pass"

                event = InspectionEvent(
                    event_id=uuid4(),
                    timestamp=now - timedelta(minutes=minutes_ago),
                    line_id=line_id,
                    machine_id=f"machine-{line_id}a",
                    sku=f"SKU-{10000 + i}",
                    result=result,
                    confidence=0.92 if result == "pass" else 0.85,
                    defect_type="scratch" if result == "fail" else None,
                    severity=None
                )
                events.append(event)

        # Bulk insert
        session.add_all(events)
        session.commit()

        print(f"✅ Seeded {len(events)} baseline events across {len(LINE_OPTIONS)} lines")
        print(f"   Baseline defect rate: ~2%")

    except Exception as e:
        session.rollback()
        print(f"❌ Error seeding data: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_baseline_data()
