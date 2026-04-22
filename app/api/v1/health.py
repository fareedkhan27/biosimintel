from __future__ import annotations

import redis.asyncio as redis
from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.schemas.health import HealthCheck

router = APIRouter()
logger = get_logger(__name__)


async def _check_database() -> dict[str, str]:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        logger.error("Database health check failed", error=str(exc))
        return {"status": "error", "detail": str(exc)}


async def _check_redis() -> dict[str, str]:
    try:
        client = redis.from_url(str(settings.REDIS_URL))
        await client.ping()
        await client.close()
        return {"status": "ok"}
    except Exception as exc:
        logger.error("Redis health check failed", error=str(exc))
        return {"status": "error", "detail": str(exc)}


@router.get("", response_model=HealthCheck)
async def health_check() -> HealthCheck:
    """Return application health status with dependency checks."""
    db_status = await _check_database()
    redis_status = await _check_redis()
    overall = "ok" if db_status["status"] == "ok" and redis_status["status"] == "ok" else "degraded"
    return HealthCheck(
        status=overall,
        version="0.1.0",
        dependencies={
            "database": db_status,
            "redis": redis_status,
        },
    )
