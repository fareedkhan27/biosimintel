from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.predictive_timeline import LaunchTimeline
from app.services.predictive_timeline import build_launch_timeline, format_stage

router = APIRouter(tags=["Predictive Timeline"])

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["format_stage"] = format_stage


@router.get("/intelligence/timeline", response_model=LaunchTimeline)
async def get_launch_timeline(
    molecule_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> LaunchTimeline:
    """Returns predictive launch timeline for a molecule."""
    return await build_launch_timeline(molecule_id, db)


@router.get("/intelligence/timeline/view", response_class=HTMLResponse)
async def get_timeline_view(
    request: Request,
    molecule_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Renders a Gantt-style timeline HTML view."""
    timeline = await build_launch_timeline(molecule_id, db)
    return templates.TemplateResponse(
        request,
        "timeline.html",
        {"timeline": timeline},
    )
