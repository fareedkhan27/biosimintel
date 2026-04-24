"""Indication Intelligence API routes.

Provides:
  - JSON heatmap matrix + strategic metrics
  - Full-page HTML heatmap view
  - Email-safe HTML table fragment
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.indication_heatmap import IndicationLandscape
from app.schemas.regulatory_risk import RegulatoryRiskProfile
from app.services.indication_heatmap import build_indication_landscape
from app.services.predictive_timeline import format_stage
from app.services.regulatory_risk import calculate_regulatory_risk_weights

router = APIRouter(tags=["Indication Intelligence"])

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["format_stage"] = format_stage


def _vulnerability_styles(index: int) -> tuple[str, str, str]:
    """Return (color, background_color, label) for vulnerability index."""
    if index < 40:
        return "#065f46", "#ecfdf5", "Low Risk"
    if index < 60:
        return "#92400e", "#fef3c7", "Moderate Risk"
    if index < 80:
        return "#9a3412", "#fff7ed", "Elevated Risk"
    return "#991b1b", "#fef2f2", "High Risk"


def _generate_insights(landscape: IndicationLandscape) -> list[str]:
    """Auto-generate strategic narrative bullets from landscape data."""
    insights: list[str] = []

    # Most active competitor
    if landscape.competitors:
        most_active = max(landscape.competitors, key=lambda c: c.breadth_score)
        insights.append(
            f"{most_active.name} is the most active competitor across "
            f"{most_active.breadth_score} indication(s) (focus: {most_active.focus_type})."
        )

    # Highest threat concentration
    max_heat = 0
    top_indication = ""
    for row in landscape.matrix:
        for cell in row:
            if cell and cell.heat_score > max_heat:
                max_heat = cell.heat_score
                top_indication = cell.indication
    if top_indication:
        insights.append(
            f"The highest threat concentration is in {top_indication} "
            f"with a heat score of {max_heat}."
        )

    # White space insight
    if landscape.white_space_indications:
        first_ws = landscape.white_space_indications[0]
        insights.append(
            f"Consider prioritizing market access strategy for {first_ws} "
            "where no biosimilar activity has been detected."
        )

    return insights


@router.get("/intelligence/heatmap", response_model=IndicationLandscape)
async def get_heatmap_json(
    molecule_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> IndicationLandscape:
    """Returns full heatmap matrix + strategic metrics as JSON."""
    return await build_indication_landscape(molecule_id, db)


@router.get("/intelligence/heatmap/view", response_class=HTMLResponse)
async def get_heatmap_view(
    request: Request,
    molecule_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Renders the full-page HTML heatmap view."""
    landscape = await build_indication_landscape(molecule_id, db)
    vi_color, vi_bg, vi_label = _vulnerability_styles(landscape.vulnerability_index)
    insights = _generate_insights(landscape)

    return templates.TemplateResponse(
        request,
        "heatmap.html",
        {
            "landscape": landscape,
            "vi_color": vi_color,
            "vi_bg": vi_bg,
            "vi_label": vi_label,
            "insights": insights,
        },
    )


@router.get("/intelligence/heatmap/enhanced", response_model=RegulatoryRiskProfile)
async def get_enhanced_heatmap(
    molecule_id: UUID,
    include_patents: bool = True,
    db: AsyncSession = Depends(get_db),
) -> RegulatoryRiskProfile:
    """Returns heatmap data enriched with patent cliff overlay."""
    if include_patents:
        return await calculate_regulatory_risk_weights(molecule_id, db)
    # Fallback to empty patent list if patents excluded
    from datetime import UTC, datetime
    return RegulatoryRiskProfile(
        molecule_id=molecule_id,
        patent_cliffs=[],
        pathway_weights={},
        generated_at=datetime.now(UTC),
    )


@router.get("/intelligence/heatmap/email-fragment", response_class=HTMLResponse)
async def get_heatmap_email_fragment(
    molecule_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Returns ONLY the HTML table fragment for embedding in emails."""
    landscape = await build_indication_landscape(molecule_id, db)

    if not landscape.indications:
        return HTMLResponse(
            content=(
                '<div style="text-align:center;padding:32px;border:2px dashed #cbd5e1;'
                'border-radius:8px;font-family:system-ui,sans-serif;color:#64748b;">'
                "No Indication-Level Intelligence Available. Competitive activity is being monitored. "
                "This section will populate as clinical trial and regulatory data is ingested."
                "</div>"
            ),
            status_code=200,
        )

    vi_color, vi_bg, _vi_label = _vulnerability_styles(landscape.vulnerability_index)
    insights = _generate_insights(landscape)

    executive_summary = (
        f"{landscape.molecule_name} faces concentrated competition in "
        f"{len(landscape.contested_indications)} indication(s), with "
        f"{len(landscape.white_space_indications)} white-space opportunity(ies) remaining. "
        f"Overall vulnerability index: {landscape.vulnerability_index}/100."
    )

    # Render via Jinja2 (re-use the email template)
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["format_stage"] = format_stage
    template = env.get_template("heatmap_email_fragment.html")
    html = template.render(
        landscape=landscape,
        executive_summary=executive_summary,
        vi_bg=vi_bg,
        vi_fg=vi_color,
        insights=insights,
    )

    return HTMLResponse(content=html, status_code=200)
