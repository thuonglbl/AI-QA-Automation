"""Database connectivity health checks."""

from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import text

from ai_qa.config import AppSettings
from ai_qa.db.session import create_db_engine


@dataclass(frozen=True)
class DatabaseHealth:
    """Serializable database readiness result."""

    status: str
    latency_ms: float | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, str | float | None]:
        """Return a response-safe dictionary without credentials."""
        payload: dict[str, str | float | None] = {
            "status": self.status,
            "latency_ms": self.latency_ms,
        }
        if self.error:
            payload["error"] = self.error
        return payload


def check_database_health(settings: AppSettings | None = None) -> DatabaseHealth:
    """Run a lightweight SELECT 1 readiness check against PostgreSQL."""
    settings = settings or AppSettings()
    if not settings.database_url and not settings.database_password:
        return DatabaseHealth(status="not_configured")

    start = perf_counter()
    try:
        engine = create_db_engine(settings)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        latency_ms = round((perf_counter() - start) * 1000, 2)
        return DatabaseHealth(status="healthy", latency_ms=latency_ms)
    except Exception:
        latency_ms = round((perf_counter() - start) * 1000, 2)
        return DatabaseHealth(
            status="unhealthy", latency_ms=latency_ms, error="database_unreachable"
        )
