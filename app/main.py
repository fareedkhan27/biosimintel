from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.exceptions import (
    AIClientException,
    IngestionException,
    NotFoundException,
    ValidationException,
)
from app.core.logging import configure_logging, get_logger
from app.db.session import engine
from app.routers.dashboard import router as dashboard_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()

    async def _noise_expiry_loop() -> None:
        while True:
            try:
                from app.services.noise_service import NoiseBlockService
                svc = NoiseBlockService()
                count = await svc.expire_old_noise()
                if count > 0:
                    logger.info("Expired old noise signals", count=count)
            except Exception as exc:
                logger.error("Noise expiry error", error=str(exc))
            await asyncio.sleep(86400)

    noise_task = asyncio.create_task(_noise_expiry_loop())
    del noise_task  # keep reference to prevent GC, but we don't need to await it
    yield
    await engine.dispose()


app = FastAPI(
    title="Biosim",
    description="Deterministic-first competitive intelligence for pharmaceutical biosimilar monitoring",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://biosimintel.com",
        "https://www.biosimintel.com",
        "https://dashboard.biosimintel.com",
        "https://api.biosimintel.com",
        "http://localhost:8001",
        "https://n8n.cloud",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1/dashboard")


@app.exception_handler(NotFoundException)
async def not_found_handler(_request: Any, exc: NotFoundException) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": exc.message})


@app.exception_handler(ValidationException)
async def validation_handler(_request: Any, exc: ValidationException) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": exc.message})


@app.exception_handler(AIClientException)
async def ai_client_handler(_request: Any, exc: AIClientException) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": exc.message})


@app.exception_handler(IngestionException)
async def ingestion_handler(_request: Any, exc: IngestionException) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": exc.message})
