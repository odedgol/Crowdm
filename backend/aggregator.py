from __future__ import annotations

import json
from statistics import mean
from typing import Any

from anthropic import AsyncAnthropic

from backend.models import (
    ABVerdict,
    CampaignReport,
    PersonaJourney,
    StageAggregate,
    StageKind,
    StageScores,
    TopIssue,
    STAGE_LABELS,
)
from backend.prompts import CLUSTERING_PROMPT, AB_VERDICT_PROMPT
from backend.llm import accumulate_usage, chat_json


VALID_CATEGORIES = {"URGENCY", "TRUST", "PRICE", "CLARITY", "CTA", "FRICTION", "OTHER"}


def _mean_scores(reactions_scores: list[StageScores]) -> StageScores:
    if not reactions_scores:
        return StageScores(clarity=0, trust=0, price_fit=0, urgency=0, cta=0)
    return StageScores(
        clarity=round(mean(s.clarity for s in reactions_scores)),
        trust=round(mean(s.trust for s in reactions_scores)),
        price_fit=round(mean(s.price_fit for s in reactions_scores)),
        urgency=round(mean(s.urgency for s in reactions_scores)),
        cta=round(mean(s.cta for s in reactions_scores)),
    )


def build_stage_aggregates(
    journeys: list[PersonaJourney], ordered_stages: list[StageKind]
) -> list[StageAggregate]:
    aggregates: list[StageAggregate] = []
    for stage in ordered_stages:
        scores_for_stage: list[StageScores] = []
        continued = 0
        entered_here = 0
        for journey in journeys:
            for reaction in journey.stages:
                if reaction.stage == stage:
                    entered_here += 1
                    scores_for_stage.append(reaction.scores)
                    if reaction.continues:
                        continued += 1
                    break

        drop_rate = 1 - (continued / entered_here) if entered_here > 0 else 0.0
        aggregates.append(
            StageAggregate(
                stage=stage,
                label=STAGE_LABELS.get(stage, stage),
                entered=entered_here,
                continued=continued,
                drop_off_rate=round(drop_rate, 3),
                mean_scores=_mean_scores(scores_for_stage),
            )
        )

    return aggregates


def _conversion_rate(journeys: list[PersonaJourney]) -> float:
    if not journeys:
        return 0.0
    return round(sum(1 for j in journeys if j.converted) / len(journeys), 3)


async def cluster_top_issues(
    journeys: list[PersonaJourney],
    *,
    model: str,
    anthropic_client: AsyncAnthropic | None,
    usage_total: dict,
) -> list[TopIssue]:
    lines: list[str] = []
    for journey in journeys:
        for reaction in journey.stages:
            for obj in reaction.objections:
                lines.append(f"[{reaction.stage}] ({journey.archetype}) {obj}")
    if not lines:
        return []

    user_text = CLUSTERING_PROMPT + "\n\nOBJECTIONS TO CLUSTER:\n" + "\n".join(lines)
    try:
        data, usage = await chat_json(
            model=model,
            max_tokens=1500,
            system_blocks=[],
            messages=[{"role": "user", "content": user_text}],
            anthropic_client=anthropic_client,
        )
    except json.JSONDecodeError:
        return []
    accumulate_usage(usage_total, usage)

    issues: list[TopIssue] = []
    for item in data.get("issues", []):
        stage_val = item.get("stage")
        if stage_val not in STAGE_LABELS:
            stage_val = None
        category = str(item.get("category", "")).upper().strip()
        if category not in VALID_CATEGORIES:
            category = "OTHER"
        try:
            freq = int(item.get("frequency", 0))
        except (TypeError, ValueError):
            freq = 0
        issues.append(
            TopIssue(
                title=str(item.get("title", "")).strip() or "Issue",
                stage=stage_val,
                category=category,  # type: ignore[arg-type]
                frequency=freq,
                example_quotes=[str(q) for q in (item.get("example_quotes") or [])][:3],
                recommendation=str(item.get("recommendation", "")).strip(),
            )
        )
    return issues


async def build_campaign_report(
    campaign_label: str,
    journeys: list[PersonaJourney],
    ordered_stages: list[StageKind],
    *,
    model: str,
    anthropic_client: AsyncAnthropic | None,
    usage_total: dict,
) -> CampaignReport:
    return CampaignReport(
        campaign_label=campaign_label,
        personas=journeys,
        stage_aggregates=build_stage_aggregates(journeys, ordered_stages),
        top_issues=await cluster_top_issues(
            journeys, model=model, anthropic_client=anthropic_client, usage_total=usage_total
        ),
        conversion_rate=_conversion_rate(journeys),
    )


async def build_ab_verdict(
    report_a: CampaignReport,
    report_b: CampaignReport,
    *,
    model: str,
    anthropic_client: AsyncAnthropic | None,
    usage_total: dict,
) -> ABVerdict | None:
    payload: dict[str, Any] = {
        "campaign_A": report_a.model_dump(mode="json"),
        "campaign_B": report_b.model_dump(mode="json"),
    }
    user_text = AB_VERDICT_PROMPT + "\n\nINPUT:\n" + json.dumps(payload, indent=2)
    try:
        data, usage = await chat_json(
            model=model,
            max_tokens=1500,
            system_blocks=[],
            messages=[{"role": "user", "content": user_text}],
            anthropic_client=anthropic_client,
        )
    except json.JSONDecodeError:
        return None
    accumulate_usage(usage_total, usage)

    winner = data.get("overall_winner")
    if winner not in ("A", "B", "tie"):
        winner = "tie"
    return ABVerdict(
        overall_winner=winner,
        overall_reasoning=str(data.get("overall_reasoning", "")).strip(),
        per_persona=[dict(entry) for entry in (data.get("per_persona") or [])],
    )
