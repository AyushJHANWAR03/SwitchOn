"""FastAPI application."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from app.routes import producer, alerts, metrics, meta
from app.kafka_consumer import ws_manager
from app.database import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting SwitchOn Backend API")
    init_db()
    yield
    # Shutdown
    logger.info("Shutting down SwitchOn Backend API")


app = FastAPI(
    title="SwitchOn Backend API",
    description="Real-time inspection monitoring and alerting system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(producer.router, prefix="/api", tags=["Producer"])
app.include_router(alerts.router, prefix="/api", tags=["Alerts"])
app.include_router(metrics.router, prefix="/api", tags=["Metrics"])
app.include_router(meta.router, prefix="/api", tags=["Meta"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "SwitchOn Backend API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for live updates."""
    await websocket.accept()
    ws_manager.connect(websocket)

    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
