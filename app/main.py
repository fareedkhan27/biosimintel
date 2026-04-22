from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.exceptions import (
    AIClientException,
    IngestionException,
    NotFoundException,
    ValidationException,
)
from app.core.logging import configure_logging
from app.db.session import engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    yield
    await engine.dispose()


app = FastAPI(
    title="Biosim",
    description="Deterministic-first competitive intelligence for pharmaceutical biosimilar monitoring",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api/v1")


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
