from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    competitors,
    events,
    health,
    indications,
    intelligence,
    jobs,
    molecules,
    sec_filings,
    timeline,
    webhooks,
)

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(molecules.router, prefix="/molecules", tags=["molecules"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(competitors.router, prefix="/competitors", tags=["competitors"])
api_router.include_router(intelligence.router, prefix="/intelligence", tags=["intelligence"])
api_router.include_router(indications.router, tags=["Indication Intelligence"])
api_router.include_router(timeline.router, tags=["Predictive Timeline"])
api_router.include_router(alerts.router, tags=["Intelligence Alerts"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(sec_filings.router, tags=["sec-edgar"])
