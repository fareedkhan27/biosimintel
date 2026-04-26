from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    competitors,
    ema_epar,
    email_v2,
    epo,
    events,
    geo_intelligence,
    health,
    indications,
    intelligence,
    jobs,
    molecules,
    noise,
    openfda,
    press_release,
    pubmed,
    sec_filings,
    threat_matrix,
    timeline,
    uspto,
    webhooks,
    who_ictrp,
)

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(molecules.router, prefix="/molecules", tags=["molecules"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(competitors.router, prefix="/competitors", tags=["competitors"])
api_router.include_router(intelligence.router, prefix="/intelligence", tags=["intelligence"])
api_router.include_router(email_v2.router, prefix="/intelligence", tags=["email-v2"])
api_router.include_router(geo_intelligence.router, tags=["geo-intelligence"])
api_router.include_router(noise.router, tags=["noise"])
api_router.include_router(indications.router, tags=["Indication Intelligence"])
api_router.include_router(timeline.router, tags=["Predictive Timeline"])
api_router.include_router(alerts.router, tags=["Intelligence Alerts"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(sec_filings.router, tags=["sec-edgar"])
api_router.include_router(threat_matrix.router, prefix="/threat-matrix", tags=["threat-matrix"])
api_router.include_router(ema_epar.router, tags=["ema-epar"])
api_router.include_router(openfda.router, tags=["openfda"])
api_router.include_router(pubmed.router, tags=["pubmed"])
api_router.include_router(uspto.router, tags=["uspto"])
api_router.include_router(epo.router, tags=["epo"])
api_router.include_router(who_ictrp.router, tags=["who-ictrp"])
api_router.include_router(press_release.router, tags=["press-release"])
