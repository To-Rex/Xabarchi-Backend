"""Liveness and readiness probes (mounted at the root, no /api/v1 prefix)."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.infrastructure.db.session import async_session_factory
from app.infrastructure.redis.client import get_redis

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness: the process is up. No dependencies touched."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(response: Response) -> dict[str, str]:
    """Readiness: verifies PostgreSQL (SELECT 1) and Redis (PING)."""
    checks: dict[str, str] = {}
    healthy = True

    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - readiness must never crash
        checks["database"] = f"error: {exc.__class__.__name__}"
        healthy = False

    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc.__class__.__name__}"
        healthy = False

    checks["status"] = "ok" if healthy else "degraded"
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return checks
