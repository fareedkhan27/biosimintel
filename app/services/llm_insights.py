from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.core.logging import get_logger
from app.models.llm_insight_cache import LlmInsightCache
from app.models.molecule import Molecule
from app.schemas.llm_insights import InsightResult
from app.schemas.predictive_timeline import LaunchTimeline
from app.schemas.regulatory_risk import RegulatoryRiskProfile
from app.services.ai.client import AIClient
from app.services.indication_heatmap import build_indication_landscape
from app.services.intelligence_alerts import detect_threshold_breaches
from app.services.predictive_timeline import build_launch_timeline
from app.services.regulatory_risk import calculate_regulatory_risk_weights

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are the Chief Competitive Intelligence Officer at a global pharmaceutical company. You are briefing the Vice President of Market Access and the executive leadership team.

Your tone is: authoritative, strategically sharp, confident but never speculative. You speak with the precision of a McKinsey partner and the domain expertise of a pharma veteran.

Rules:
1. You analyze ONLY the verified data provided below. You NEVER invent competitors, trials, patents, or dates.
2. If data is incomplete, you acknowledge it confidently: "With current intelligence..." rather than guessing.
3. Every insight must connect to a strategic implication — not just "what" but "so what."
4. Use active voice. Avoid hedging words like "maybe," "possibly," "might." Use "signals," "indicates," "positions for," "threatens."
5. Reference specific competitor names, indication names, and patent numbers explicitly.
6. Frame recommendations as strategic imperatives with clear ownership: "Market Access should..." "The team must..." "Priority action:"""""

USER_PROMPT_TEMPLATE = """
## EXECUTIVE COMPETITIVE INTELLIGENCE BRIEFING
Prepared for: VP, Market Access | Date: {report_date}
Molecule: {molecule_name}

### VERIFIED INTELLIGENCE DATA
{context_json}

### YOUR TASK
Write an executive briefing that a VP can read in 20 seconds and act on immediately.

1. **EXECUTIVE SUMMARY** (Max 25 words, bold, decisive)
   - State the competitive posture in one sentence.
   - Example good: "Nivolumab faces early-stage biosimilar pressure concentrated in Melanoma, with four uncontested indications offering defensive runway."
   - Example bad: "There are some competitors and they are doing things in different places."

2. **STRATEGIC INSIGHTS** (Exactly 3 bullets, 20-35 words each)
   - Each bullet must name a real competitor and a real indication from the data.
   - Connect the fact to a strategic implication.
   - Pattern: "[Competitor] is [action] in [Indication], which [strategic implication]."
   - Example good: "Henlius is the only competitor building a multi-indication portfolio across HCC and Melanoma, signaling long-term commitment rather than opportunistic entry."
   - Example bad: "Henlius is active in some indications."

3. **EXECUTIVE RECOMMENDATIONS** (Exactly 2 bullets, action-oriented, 20-30 words each)
   - Each must be a specific, prioritized action.
   - Pattern: "[Action verb] [what] in [where] by [when/why]."
   - Example good: "Secure early payer agreements in ESCC and NSCLC immediately — both remain uncontested with patent protection extending to 2028-2032."
   - Example bad: "Think about some strategies for different places."

4. **CONFIDENCE ASSESSMENT**
   - "high" if vulnerability index < 40 and no imminent launches
   - "medium" if vulnerability index 40-70 or launches within 24 months
   - "elevated" if vulnerability index > 70 or launches within 12 months

Return ONLY valid JSON:
{{
  "executive_summary": "string (max 25 words, bold tone)",
  "key_insights": ["string (20-35 words)", "string (20-35 words)", "string (20-35 words)"],
  "recommended_actions": ["string (20-30 words)", "string (20-30 words)"],
  "confidence": "high" | "medium" | "elevated"
}}

### EXAMPLE 1 — Low Threat Posture
INPUT: vulnerability_index=15, contested=[], competitors=[Amgen pre-clinical], white_spaces=[Melanoma, NSCLC, RCC]
OUTPUT:
{{
  "executive_summary": "Nivolumab maintains a favorable competitive position with minimal biosimilar activity detected across all tracked indications.",
  "key_insights": [
    "Amgen remains in pre-clinical development with no near-term launch pathway, indicating limited immediate pricing pressure.",
    "All major indications remain uncontested, providing a strategic window to strengthen payer relationships before competitive entry.",
    "Patent protection extends to 2028-2032 across the portfolio, supporting sustained market access leverage."
  ],
  "recommended_actions": [
    "Accelerate long-term payer contracting in NSCLC and RCC to entrench formulary position before any competitive signals emerge.",
    "Maintain competitive surveillance at current cadence — no immediate resource reallocation required."
  ],
  "confidence": "high"
}}

### EXAMPLE 2 — Elevated Threat Posture
INPUT: vulnerability_index=78, contested=[Melanoma, NSCLC], competitors=[Sandoz phase3, Amgen phase3], imminent_launches=[Sandoz 2028-Q2]
OUTPUT:
{{
  "executive_summary": "Nivolumab faces concentrated biosimilar pressure in Melanoma and NSCLC with high-confidence launches expected within 24 months.",
  "key_insights": [
    "Sandoz and Amgen are both in Phase 3 for Melanoma, creating a dual-entry threat scenario that will compress pricing power rapidly.",
    "The Melanoma patent cliff (US9073996, March 2028) aligns precisely with Sandoz's estimated launch window, confirming strategic timing by competitors.",
    "NSCLC remains contested but less advanced — only pre-clinical activity detected, offering 18-24 months of defensive preparation time."
  ],
  "recommended_actions": [
    "Initiate emergency pricing defense simulations for Melanoma targeting Q1 2028, modeling dual-entry scenarios with 40-60% price erosion.",
    "Secure exclusive payer agreements in NSCLC immediately to lock in formulary position before any competitor reaches Phase 2."
  ],
  "confidence": "elevated"
}}
"""


@dataclass
class _FallbackInsights:
    summary: str
    bullets: list[str]
    actions: list[str]


def _generate_template_insights(context: dict[str, Any]) -> _FallbackInsights:
    """Generate deterministic VP-grade fallback insights when LLM is unavailable."""
    molecule_name = context.get("molecule_name", "the molecule")
    contested = context.get("contested_zones", [])
    white_spaces = context.get("white_spaces", [])
    competitors = context.get("competitor_profiles", [])
    imminent = context.get("imminent_launches", [])
    vulnerability = context.get("vulnerability_index", 50)
    patent_cliffs = context.get("patent_cliffs", [])

    # Executive summary: bold, decisive, ≤ 25 words
    if vulnerability < 40:
        summary = f"{molecule_name.title()} maintains a favorable position with limited biosimilar pressure across tracked indications."
    elif vulnerability < 70:
        summary = f"{molecule_name.title()} faces emerging biosimilar competition in {contested[0] if contested else 'key indications'} with defensive runway remaining."
    else:
        summary = f"{molecule_name.title()} faces concentrated biosimilar pressure with high-confidence launches expected within 24 months."

    # Key insights: exactly 3, naming real competitors and indications
    bullets: list[str] = []
    if competitors:
        most_active = max(competitors, key=lambda c: c.get("breadth", 0))
        stage = most_active.get("current_stage", "unknown")
        bullets.append(
            f"{most_active['name']} is the most active competitor across {most_active['breadth']} indication(s) "
            f"at {stage} stage, signaling { 'near-term threat' if stage in ('Phase 3', 'BLA Filed', 'Approved') else 'early-stage interest' }."
        )
    if contested:
        bullets.append(
            f"Highest threat concentration is in {contested[0]}, requiring immediate pricing and access strategy review."
        )
    if imminent:
        imm = imminent[0]
        bullets.append(
            f"{imm['competitor']} positions for {imm['quarter']} launch in {imm['indication']}, "
            f"compressing market access leverage within {imm['months']} months."
        )
    if white_spaces and len(bullets) < 3:
        bullets.append(
            f"{white_spaces[0]} remains uncontested, offering a strategic window to secure payer agreements before competitive entry."
        )
    if patent_cliffs and len(bullets) < 3:
        pc = patent_cliffs[0]
        bullets.append(
            f"Patent {pc.get('patent_number', 'N/A')} expires {pc.get('expiry_date', 'soon')}, "
            f"aligning competitive launch incentives with loss-of-exclusivity timing."
        )
    while len(bullets) < 3:
        bullets.append("Continue competitive surveillance for new entrants and stage advancements.")

    # Recommendations: exactly 2, action-oriented with clear ownership
    actions: list[str] = []
    if contested:
        actions.append(
            f"Initiate pricing defense simulations for {contested[0]} immediately, modeling dual-entry scenarios with 40-60% price erosion."
        )
    if white_spaces:
        actions.append(
            f"Secure exclusive payer agreements in {white_spaces[0]} before any competitor reaches Phase 2, locking in formulary position."
        )
    if len(actions) < 2:
        actions.append("Accelerate long-term payer contracting across uncontested indications to entrench market position.")
    if len(actions) < 2:
        actions.append("Maintain competitive surveillance at current cadence — no immediate resource reallocation required.")

    return _FallbackInsights(summary=summary, bullets=bullets, actions=actions)


def _validate_insights(raw_json: dict[str, Any], context: dict[str, Any]) -> bool:
    """Ensure every named entity in the LLM output exists in the input context.

    Word-count checks are advisory only — we do NOT fall back to templates for
    minor formatting issues. Only entity hallucination triggers fallback.
    """
    valid_competitors = {c["name"] for c in context.get("competitor_profiles", [])}
    valid_indications = set(
        context.get("contested_zones", [])
        + context.get("white_spaces", [])
        + context.get("all_indications", [])
    )
    valid_molecules = {context.get("molecule_name", "")}

    all_text = " ".join(
        [
            raw_json.get("executive_summary", ""),
            *raw_json.get("key_insights", []),
            *raw_json.get("recommended_actions", []),
        ]
    )

    words = re.findall(r"[A-Z][a-zA-Z]{2,}", all_text)
    allowed_generic = {
        # Platform / org
        "Biosim", "Market", "Access", "Competitive", "Intelligence",
        "FDA", "EMA", "US", "EU", "The", "This", "Team", "Director",
        "Global", "Pharma", "Company", "Strategic", "Executive", "Summary",
        "Vice", "President", "Leadership", "Board",
        # Structural words
        "Key", "Insights", "Recommended", "Actions", "For", "And", "Or",
        "In", "With", "By", "To", "Of", "On", "At", "From", "Is", "Are",
        "Has", "Have", "Should", "Consider", "Monitor", "Review", "Evaluate",
        "Prioritize", "Engage", "Prepare", "Assess", "Track", "Watch", "Alert",
        # Competitive terms
        "Risk", "Threat", "Opportunity", "Launch", "Competition", "Competitor",
        "Indication", "Patent", "Cliff", "Biosimilar", "Clinical", "Trial",
        "Regulatory", "Filing", "Phase", "Preclinical", "Pre", "Post",
        "Approach", "Strategy", "Pricing", "Reimbursement", "Formulary",
        "Payer", "Entry", "Window", "Period", "Months", "Years", "Quarter",
        "Scenario", "Erosion", "Defense", "Agreement", "Contract", "Lock",
        "Imperative", "Priority", "Action", "Surveillance", "Resource",
        "Portfolios", "Portfolio", "Commitment", "Concentrated", "Limited",
        "Immediate", "Near", "Term", "Long", "Short", "Current", "Future",
        # Months
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
        # Numbers / quantities
        "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
        "First", "Second", "Third", "Dual", "Multiple", "Single",
        # Geography
        "North", "South", "East", "West", "American", "European", "Asian",
        "Pacific", "Atlantic", "India", "China", "Japan", "Germany", "France",
        "United", "Kingdom", "Spain", "Italy", "Australia", "Canada", "Brazil",
        # Time
        "Day", "Week", "Month", "Year", "Today", "Yesterday", "Tomorrow",
        "Annual", "Quarterly", "Weekly", "Daily",
        # Verbs / actions
        "Secure", "Initiate", "Accelerate", "Maintain", "Strengthen", "Entrench",
        "Modeling", "Simulations", "Position", "Signal", "Indicate", "Threaten",
        "Develop", "Building", "Create", "Creating", "Offer", "Offering",
        "Run", "Running", "Provide", "Providing", "Support", "Supporting",
        "Drive", "Driving", "Push", "Pushing", "Pull", "Pulling",
        # Misc business / medical
        "Data", "Information", "Report", "Analysis", "Research", "Development",
        "Manufacturing", "Commercial", "Sales", "Revenue", "Profit", "Margin",
        "Price", "Cost", "Value", "Volume", "Share", "Growth", "Decline",
        "Positive", "Negative", "Neutral", "Stable", "Unstable", "Volatile",
        "Product", "Drug", "Molecule", "Asset", "Compound",
        "Patient", "Patients", "Provider", "Providers", "Hospital", "Hospitals",
        "Treatment", "Treatments", "Therapy", "Therapies", "Dose", "Dosing",
        "Safety", "Efficacy", "Efficacious", "Effective", "Effectiveness",
        "Adverse", "Event", "Events", "Reaction", "Reactions", "Side",
        "Benefit", "Benefits", "Outcome", "Outcomes", "Result", "Results",
        "Study", "Studies", "Investigator", "Investigators", "Site", "Sites",
        "Enrollment", "Recruitment", "Cohort", "Cohorts", "Arm", "Arms",
        "Endpoint", "Endpoints", "Biomarker", "Biomarkers", "Genomic", "Genomics", "Proteomic", "Proteomics", "Transcriptomic",
        "Cell", "Cells", "Tissue", "Tissues", "Organ", "Organs", "System",
        "Body", "Bodies", "Health", "Healthy", "Disease", "Diseases",
        "Condition", "Conditions", "Disorder", "Disorders", "Syndrome",
        "Pathway", "Pathways", "Mechanism", "Mechanisms", "Target", "Targets",
        "Receptor", "Receptors", "Enzyme", "Enzymes", "Protein", "Proteins",
        "Gene", "Genes", "Mutation", "Mutations", "Variant", "Variants",
        "Expression", "Expressions", "Level", "Levels", "Activity",
        "Inhibition", "Inhibitor", "Inhibitors", "Agonist", "Agonists",
        "Antagonist", "Antagonists", "Modulator", "Modulators",
        "Antibody", "Antibodies", "Vaccine", "Vaccines", "Cellular",
        "Immune", "Immunity", "Immunogenicity", "Immunogenic",
        "Tolerance", "Tolerability", "Toxicity", "Toxic", "Tox",
        "Pharmacokinetic", "Pharmacokinetics", "Pharmacodynamic",
        "Pharmacodynamics", "Exposure", "Exposures", "Clearance",
        "Half", "Life", "Lives", "Elimination", "Excretion",
        "Absorption", "Distribution", "Metabolism", "Bioavailability",
        "Area", "Under", "Curve", "Peak", "Trough", "Steady",
        "State", "States", "Loading", "Maintenance", "Doses",
        "Escalation", "De", "Reduction", "Titration", "Titrations",
        # Additional common sentence-start words
        "All", "Each", "Every", "Some", "Most", "Many", "Few", "Several",
        "Both", "Neither", "Either", "None", "Any", "Other", "Another",
        "Such", "Same", "Different", "Various", "Certain", "Specific",
        "Particular", "General", "Overall", "Total", "Full", "Partial",
        "Complete", "Incomplete", "Final", "Initial", "Original", "New",
        "Old", "Recent", "Latest", "Earlier", "Later", "Soon", "Now",
        "Then", "When", "Where", "Why", "How", "What", "Who", "Which",
        "Whose", "Whom", "That", "These", "Those", "Thus", "Therefore",
        "Hence", "Consequently", "Accordingly", "Subsequently", "Finally",
        "Additionally", "Furthermore", "Moreover", "Nevertheless", "However",
        "Nonetheless", "Notwithstanding", "Regardless", "Irrespective",
        "Despite", "Although", "Though", "While", "Whereas", "Because",
        "Since", "As", "If", "Unless", "Until", "Before", "After", "During",
        "Throughout", "Across", "Within", "Without", "Beyond",
        "Above", "Below", "Over", "Between", "Among", "Amongst",
        "Against", "Toward", "Towards", "Through", "Into", "Onto", "Upon",
        "Off", "Out", "Up", "Down", "Back", "Forward", "Ahead", "Behind",
        "Beside", "Besides", "Except", "Including", "Excluding", "Regarding",
        "Concerning", "Respecting", "Touching", "Pending", "Following",
        "Preceding", "Previous", "Subsequent", "Concurrent", "Simultaneous",
    }

    # Build a single list of all valid names for substring checking
    all_valid_names = [n for n in (valid_competitors | valid_indications | valid_molecules) if n]

    for word in words:
        if word in allowed_generic:
            continue
        word_lower = word.lower()
        # Check if this word appears as a substring in any valid name
        if any(word_lower in v.lower() for v in all_valid_names):
            continue
        # Heuristic: if it looks like a proper noun not in our allow-list, flag it
        logger.warning(f"Potential hallucination detected: {word}")
        return False

    # Confidence validation
    confidence = raw_json.get("confidence", "").lower()
    if confidence not in {"high", "medium", "elevated"}:
        logger.warning(f"Invalid confidence value: {confidence}")
        return False

    return True


def _build_context(
    molecule: Molecule,
    landscape: Any,
    timeline: LaunchTimeline,
    risk_profile: RegulatoryRiskProfile,
    alert_report: Any,
) -> dict[str, Any]:
    """Build the structured context object fed to the LLM."""
    competitor_profiles = []
    for comp in landscape.competitors:
        # Find matching estimates
        ests = [e for e in timeline.estimates if str(e.competitor_id) == str(comp.id)]
        est = ests[0] if ests else None
        competitor_profiles.append(
            {
                "name": comp.name,
                "breadth": comp.breadth_score,
                "focus_type": comp.focus_type,
                "max_heat_score": comp.depth_score,
                "current_stage": est.current_stage if est else "unknown",
                "events_last_90_days": est.events_last_90_days if est else 0,
                "estimated_launch_quarter": est.estimated_launch_quarter if est else "unknown",
                "launch_confidence": est.confidence_level if est else "low",
            }
        )

    patent_cliffs = []
    for pc in risk_profile.patent_cliffs:
        patent_cliffs.append(
            {
                "indication": pc.indication,
                "patent_number": pc.patent_number,
                "expiry_date": str(pc.expiry_date),
                "days_remaining": pc.days_to_expiry,
                "competitors_active": pc.competitors_active,
            }
        )

    alerts = []
    for alert in alert_report.alerts:
        alerts.append(
            {
                "type": alert.alert_type,
                "severity": alert.severity,
                "description": alert.description,
            }
        )

    imminent = [
        {
            "competitor": e.competitor_name,
            "indication": e.indication,
            "quarter": e.estimated_launch_quarter,
            "months": e.months_to_launch,
        }
        for e in timeline.imminent_threats
    ]

    return {
        "molecule_name": molecule.molecule_name or "Unknown",
        "report_date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "vulnerability_index": landscape.vulnerability_index,
        "vulnerability_trend": "stable",
        "indications_tracked": len(landscape.indications),
        "competitors_active": len(landscape.competitors),
        "contested_zones": landscape.contested_indications,
        "white_spaces": landscape.white_space_indications,
        "all_indications": list(landscape.indications),
        "competitor_profiles": competitor_profiles,
        "patent_cliffs": patent_cliffs,
        "imminent_launches": imminent,
        "alerts": alerts,
    }


async def generate_executive_narrative(
    molecule_id: UUID,
    db: AsyncSession,
    force_refresh: bool = False,
) -> InsightResult:
    """Generate a guarded, cached, validated executive narrative for a molecule."""
    molecule_result = await db.execute(select(Molecule).where(Molecule.id == molecule_id))
    molecule = molecule_result.scalar_one_or_none()
    if molecule is None:
        raise NotFoundException("Molecule")

    # Step 1: Collect context data
    landscape = await build_indication_landscape(molecule_id, db)
    timeline = await build_launch_timeline(molecule_id, db)
    risk_profile = await calculate_regulatory_risk_weights(molecule_id, db)
    alert_report = await detect_threshold_breaches(molecule_id, db)

    # Step 2: Build structured context JSON
    context = _build_context(molecule, landscape, timeline, risk_profile, alert_report)

    # Step 3: Compute context hash
    context_hash = hashlib.sha256(
        json.dumps(context, sort_keys=True).encode()
    ).hexdigest()[:32]
    cache_key = f"{str(molecule_id)[:8]}:{context_hash}"

    # Step 4: Check cache
    if not force_refresh:
        cache_result = await db.execute(
            select(LlmInsightCache).where(LlmInsightCache.cache_key == cache_key)
        )
        cached = cache_result.scalar_one_or_none()
        if cached:
            logger.info("LLM insight cache hit", cache_key=cache_key)
            return InsightResult(
                executive_summary=str(cached.executive_summary),
                key_insights=list(cached.key_insights) if cached.key_insights else [],
                recommended_actions=list(cached.recommended_actions) if cached.recommended_actions else [],
                confidence="high",
                model_used=str(cached.model_used),
                tokens_input=int(cached.tokens_input),
                tokens_output=int(cached.tokens_output),
                cost_usd=float(cached.cost_usd),
                from_cache=True,
                fallback=False,
                generated_at=cached.created_at or datetime.now(UTC),  # type: ignore[arg-type]
            )

    # Step 5: Build LLM prompt
    context_json = json.dumps(context, indent=2)
    user_prompt = USER_PROMPT_TEMPLATE.format(
        context_json=context_json,
        report_date=datetime.now(UTC).strftime("%Y-%m-%d"),
        molecule_name=context.get("molecule_name", "Unknown"),
    )

    # Step 6: Call OpenRouter
    client = AIClient()
    raw_json: dict[str, Any] = {}
    fallback = False
    try:
        response = await client.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        # Parse JSON content
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        raw_json = json.loads(content)

        # Step 7: Validate output
        if not _validate_insights(raw_json, context):
            logger.warning("LLM output failed validation, using fallback")
            fallback = True
            fb = _generate_template_insights(context)
            raw_json = {
                "executive_summary": fb.summary,
                "key_insights": fb.bullets,
                "recommended_actions": fb.actions,
                "confidence": "medium",
            }
        model_used = response.model
        tokens_input = response.tokens_input
        tokens_output = response.tokens_output
        cost_usd = response.cost_usd
    except Exception as exc:
        logger.warning("LLM generation failed, using fallback", error=str(exc))
        fallback = True
        fb = _generate_template_insights(context)
        raw_json = {
            "executive_summary": fb.summary,
            "key_insights": fb.bullets,
            "recommended_actions": fb.actions,
            "confidence": "medium",
        }
        model_used = "fallback"
        tokens_input = 0
        tokens_output = 0
        cost_usd = 0.0

    # Step 8: Cache result (upsert — delete existing if force_refresh)
    existing = await db.execute(
        select(LlmInsightCache).where(LlmInsightCache.cache_key == cache_key)
    )
    old_entry = existing.scalar_one_or_none()
    if old_entry:
        await db.delete(old_entry)
        await db.flush()

    cache_entry = LlmInsightCache(
        molecule_id=molecule_id,
        cache_key=cache_key,
        context_hash=context_hash,
        executive_summary=raw_json.get("executive_summary", ""),
        key_insights=raw_json.get("key_insights", []),
        recommended_actions=raw_json.get("recommended_actions", []),
        model_used=model_used,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=cost_usd,
    )
    db.add(cache_entry)
    await db.commit()

    return InsightResult(
        executive_summary=raw_json.get("executive_summary", ""),
        key_insights=raw_json.get("key_insights", []),
        recommended_actions=raw_json.get("recommended_actions", []),
        confidence=raw_json.get("confidence", "medium"),
        model_used=model_used,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=cost_usd,
        from_cache=False,
        fallback=fallback,
        generated_at=datetime.now(UTC),
    )
