# 🏭 SwitchOn Backend Demo

**Real-time AI Inspection Monitoring & Alerting System**

A production-ready backend demonstration showcasing event-driven architecture, anomaly detection, and real-time alerting for industrial AI inspection systems.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Running the Demo](#running-the-demo)
- [API Documentation](#api-documentation)
- [Testing](#testing)
- [Project Structure](#project-structure)

---

## 🎯 Overview

This project simulates a **real-world AI inspection system** for manufacturing:

- **AI models** inspect products on assembly lines, detecting defects in real-time
- **Kafka/Redpanda** ingests inspection events at scale
- **Detection engine** analyzes defect rates, compares to baseline, and triggers alerts
- **REST APIs** provide CRUD operations for alerts and metrics
- **Real-time dashboard** displays live metrics and alert management

### Key Capabilities

✅ **Event-Driven Architecture** - Kafka-based stream processing
✅ **Anomaly Detection** - Multi-threshold alerting (info/warning/critical)
✅ **Real-Time Updates** - WebSocket broadcasting
✅ **Idempotency** - Duplicate event handling
✅ **Cooldown Logic** - Smart alert deduplication
✅ **Comprehensive Testing** - **68 tests passing** with TDD approach

---

## 🏗️ Architecture

```
┌─────────────────────┐
│  Mock Producer UI   │  (Streamlit)
│  (Test Harness)     │
└──────────┬──────────┘
           │ HTTP POST /api/produce
           ▼
┌─────────────────────┐
│   FastAPI Backend   │
│   (Producer API)    │
└──────────┬──────────┘
           │ Publish
           ▼
    ┌──────────────┐
    │   Redpanda   │  Topic: inspection_events
    │   (Kafka)    │
    └──────┬───────┘
           │ Subscribe
           ▼
┌─────────────────────┐      ┌──────────────────┐
│  Kafka Consumer     │─────▶│   PostgreSQL     │
│  + Detector Engine  │      │   (Events +      │
└──────────┬──────────┘      │    Alerts)       │
           │                 └──────────────────┘
           │ WebSocket Broadcast
           ▼
    ┌──────────────┐
    │  Dashboard   │  (Streamlit)
    │  (Monitoring)│
    └──────────────┘
```

### Data Flow

1. **Mock Producer** generates inspection events → FastAPI Producer API
2. **Producer API** validates & publishes to Kafka `inspection_events` topic
3. **Consumer Service** subscribes to Kafka, persists events to PostgreSQL
4. **Detection Engine** analyzes events, calculates defect rates, triggers alerts
5. **WebSocket** broadcasts live updates to dashboard
6. **Dashboard** displays metrics, alerts, and allows operator actions

---

## ✨ Features

### Detection Engine

- **Baseline Calculation**: Compares current defect rate vs. historical baseline
- **Multi-Level Thresholds**:
  - **Info**: 1.5x baseline, ≥2% absolute
  - **Warning**: 2.0x baseline, ≥5% absolute
  - **Critical**: 3.0x baseline, ≥10% absolute
- **Sliding Window**: Configurable time windows (default: 10 min current, 60 min baseline)
- **Cooldown**: Prevents duplicate alerts within 5-minute window
- **Evidence Collection**: Stores failing event IDs and defect types

### Alert Lifecycle

```
active → acknowledged → [assigned] → escalated → resolved
```

- **Acknowledge**: Operator confirms awareness
- **Assign**: Assign to specific operator
- **Escalate**: Trigger webhook/notification
- **Resolve**: Close with notes

### APIs

- **Producer**: `POST /api/produce`, `POST /api/produce/batch`
- **Alerts**: `GET /api/alerts`, `POST /api/alerts/{id}/acknowledge|assign|escalate|resolve`
- **Metrics**: `GET /api/metrics/line/{line_id}`, `GET /api/metrics/summary`
- **Meta**: `GET /api/meta` (enumerations)
- **WebSocket**: `ws://localhost:8000/ws` (live updates)

---

## 🛠️ Tech Stack

| Category | Technology |
|----------|------------|
| **Backend** | FastAPI, Python 3.12 |
| **Database** | PostgreSQL + SQLAlchemy |
| **Messaging** | Redpanda (Kafka-compatible) |
| **Frontend** | Streamlit |
| **Testing** | pytest, pytest-asyncio |
| **Deployment** | Docker Compose |

---

## 🚀 Getting Started

### Prerequisites

- **Docker** & **Docker Compose**
- **Python 3.12**
- **Git**

### Installation

```bash
# Clone repository
git clone <repo-url>
cd SwitchOn

# Start infrastructure (PostgreSQL + Redpanda)
docker-compose up -d

# Wait for services to be ready (~30s)
docker-compose ps

# Set up backend
cd backend
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Seed baseline data
python seed_data.py

# Set up UI
cd ../ui
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 🎬 Running the Demo

### Step 1: Start Backend API

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

### Step 2: Start Kafka Consumer

```bash
# In a new terminal
cd backend
source venv/bin/activate
python run_consumer.py
```

Expected output:
```
INFO - Starting Kafka Consumer Service...
INFO - Kafka consumer started: localhost:19092, topic: inspection_events
```

### Step 3: Start Mock Producer UI

```bash
# In a new terminal
cd ui
source venv/bin/activate
streamlit run mock_producer.py
```

Opens at: http://localhost:8501

### Step 4: Start Dashboard

```bash
# In a new terminal
cd ui
source venv/bin/activate
streamlit run dashboard.py --server.port 8502
```

Opens at: http://localhost:8502

---

## 🧪 Demo Scenarios

### Scenario 1: Normal Operation

1. Open **Mock Producer** (http://localhost:8501)
2. Select **Line-1**, Result: **pass**
3. Click **"Send Burst (50 events)"**
4. Open **Dashboard** (http://localhost:8502)
5. ✅ Observe: ~0-2% defect rate, **no alerts**

### Scenario 2: Critical Spike (Trigger Alert)

1. In **Mock Producer**, select **Line-2**, Result: **fail**
2. Click **"🔴 Critical Spike"** (sends 50 failures)
3. Wait 5-10 seconds
4. In **Dashboard**, observe:
   - 🔴 **Critical alert** appears
   - Defect rate jumps to ~100%
   - Alert reason: "Defect rate X.X% is 20x baseline"
5. Click **"✅ Acknowledge"** on the alert
6. Click **"✔️ Resolve"**

### Scenario 3: Gradual Degradation

1. Send **45 pass + 5 fail** events (Minor Issues button)
2. Wait 30s
3. Send **40 pass + 10 fail** events
4. Wait 30s
5. 🟡 **Warning alert** should appear (~20% defect rate)

---

## 📚 API Documentation

### Interactive Docs

Once backend is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Example API Calls

#### Produce Single Event

```bash
curl -X POST http://localhost:8000/api/produce \
  -H "Content-Type: application/json" \
  -d '{
    "line_id": "line-1",
    "result": "fail",
    "confidence": 0.87,
    "defect_type": "scratch"
  }'
```

#### Get Active Alerts

```bash
curl http://localhost:8000/api/alerts?status=active
```

#### Acknowledge Alert

```bash
curl -X POST http://localhost:8000/api/alerts/{alert_id}/acknowledge \
  -H "Content-Type: application/json" \
  -d '{"acknowledged_by": "operator1"}'
```

---

## 🧪 Testing

### Run All Tests

```bash
cd backend
source venv/bin/activate
pytest tests/ -v
```

**Expected**: **68 tests passing** ✅

### Test Coverage

```bash
pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html
```

### Test Structure

| Module | Tests | Description |
|--------|-------|-------------|
| `test_models.py` | 11 | Database models, CRUD operations |
| `test_detector.py` | 21 | Detection engine, thresholds, cooldown |
| `test_kafka_producer.py` | 12 | Kafka producer, event validation |
| `test_kafka_consumer.py` | 17 | Kafka consumer, persistence, idempotency |
| `test_api.py` | 7 | FastAPI endpoints, alert lifecycle |

---

## 📂 Project Structure

```
SwitchOn/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app
│   │   ├── models.py            # SQLAlchemy models
│   │   ├── database.py          # DB connection
│   │   ├── config.py            # Settings
│   │   ├── detector.py          # Anomaly detection engine
│   │   ├── kafka_producer.py    # Producer service
│   │   ├── kafka_consumer.py    # Consumer service + WebSocket
│   │   └── routes/              # API endpoints
│   │       ├── producer.py
│   │       ├── alerts.py
│   │       ├── metrics.py
│   │       └── meta.py
│   ├── tests/                   # 68 tests (TDD)
│   ├── run_consumer.py          # Consumer runner
│   ├── seed_data.py             # Baseline data seeder
│   └── requirements.txt
├── ui/
│   ├── mock_producer.py         # Streamlit mock UI
│   ├── dashboard.py             # Streamlit dashboard
│   └── requirements.txt
├── docker-compose.yml           # PostgreSQL + Redpanda
└── README.md                    # This file
```

---

## 🎯 Key Design Decisions

### Why Redpanda over Kafka?

- **Lighter footprint** for local development
- **Kafka-compatible** API (easy migration)
- **Faster startup** (<10s vs 30-60s)

### Why SQLAlchemy + PostgreSQL?

- **ACID compliance** for alert lifecycle
- **JSONB support** for flexible evidence storage
- **Strong indexing** for time-series queries

### Why Streamlit for UI?

- **Rapid prototyping** (<2 hours per UI)
- **Python-native** (no context switch)
- **Auto-reload** for fast iteration
- **Good enough for demo**, can migrate to React later

### Detection Engine Philosophy

- **Baseline-relative** (not absolute) - adapts to each line's normal defect rate
- **Multiple thresholds** - info/warning/critical for graduated response
- **Cooldown logic** - prevents alert fatigue
- **Evidence collection** - enables root cause analysis

---

## 🔮 Future Enhancements

### V1 (MVP+)

- [ ] EWMA/CUSUM statistical anomaly detection
- [ ] Slack/email alert routing
- [ ] React dashboard with real-time charts
- [ ] Role-based access control (RBAC)
- [ ] Grafana dashboards for long-term analytics

### V2 (Production)

- [ ] TimescaleDB for time-series optimization
- [ ] Kubernetes deployment
- [ ] Prometheus + Grafana observability
- [ ] Multi-region support
- [ ] ML-based defect classification

---

## 👤 Author

Built with ❤️ following **Test-Driven Development (TDD)** principles.

**Contact**: [Your Name]

---

## 📄 License

This is a portfolio/demo project. Feel free to use as reference.

---

## 🙏 Acknowledgments

- **SwitchOn** for the problem domain inspiration
- **FastAPI** community for excellent async support
- **Redpanda** for making Kafka development easier
- **Streamlit** for rapid UI prototyping

---

**⭐ If this helped you, please star the repo!**
