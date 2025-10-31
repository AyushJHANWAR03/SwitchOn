"""Application configuration."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings."""

    # Database
    database_url: str = "postgresql+psycopg://switchon:switchon@localhost:5433/switchon_db"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:19092"
    kafka_topic_events: str = "inspection_events"
    kafka_consumer_group: str = "switchon-consumer-group"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Detection Windows
    min_events: int = 5
    window_minutes: int = 10
    baseline_minutes: int = 60
    cooldown_minutes: int = 5

    # Alert Thresholds
    threshold_info_factor: float = 1.5
    threshold_info_absolute: float = 0.02
    threshold_warning_factor: float = 2.0
    threshold_warning_absolute: float = 0.05
    threshold_critical_factor: float = 3.0
    threshold_critical_absolute: float = 0.10

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Enumerations
LINE_OPTIONS = ["line-1", "line-2", "line-3", "line-4"]
SEVERITY_LEVELS = ["info", "warning", "critical"]
DEFECT_TYPES = ["scratch", "dent", "discoloration", "misalignment", "missing_component"]
RESULT_OPTIONS = ["pass", "fail"]
ALERT_STATUSES = ["active", "acknowledged", "escalated", "resolved"]
