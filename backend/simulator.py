from __future__ import annotations

import asyncio
import os
from typing import Any

from anthropic import AsyncAnthropic

from backend.models import (
    Campaign,
    Persona,
    PersonaJourney,
    StageContent,
    StageKind,
    StageReaction,
    StageScores,
    STAGE_LABELS,
)
from backend.extractor import resolve_stage_text
from backend.prompts import (
    EVALUATION_INSTRUCTIONS,
    FINAL_SUMMARY_INSTRUCTIONS,
    persona_system_block,
    product_context_block,
    prior_journey_block,
    stage_header,
    ad_stage_text,
    build_stage_content_text,
)
from backend.llm import (
    accumulate_usage,
    chat_json,
    is_ollama_model,
)


DEFAULT_MODEL = os.environ.get("CROWDM_MODEL", "claude-opus-4-7")
DEFAULT_CONCURRENCY = int(os.environ.get("CROWDM_CONCURRENCY", "4"))
MAX_TOKENS = 1024


def _ephemeral() -> dict:
    return {"type": "ephemeral"}


def _system_blocks(persona: Persona, use_cache: bool) -> list[dict]:
    b1: dict = {"type": "text", "text": EVALUATION_INSTRUCTIONS}
    b2: dict = {"type": "text", "text": persona_system_block(persona.character_sheet)}
    if use_cache:
        b1["cache_control"] = _ephemeral()
        b2["cache_control"] = _ephemeral()
    return [b1, b2]


def _product_block(campaign: Campaign, use_cache: bool) -> dict:
    blk: dict = {
        "type": "text",
        "text": product_context_block(
            product_name=campaign.product.name,
            product_description=campaign.product.description,
            target_audience=campaign.product.target_audience,
            price=campaign.product.price,
            vertical=campaign.product.vertical,
        ),
    }
    if use_cache:
        blk["cache_control"] = _ephemeral()
    return blk


def _image_block(b64: str, media_type: str | None) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type or "image/png",
            "data": b64,
        },
    }


async def _stage_user_content(
    *,
    campaign: Campaign,
    stage: StageContent,
    prior_reactions: list[dict],
    use_cache: bool,
) -> list[dict]:
    content: list[dict] = [_product_block(campaign, use_cache)]
    content.append({"type": "text", "text": prior_journey_block(prior_reactions)})

    label = stage.label or STAGE_LABELS.get(stage.kind, stage.kind)

    if stage.kind == "ad":
        header = stage_header("ad")
        ad_text = ad_stage_text(campaign.ad.headline, campaign.ad.body, campaign.ad.cta)
        content.append({"type": "text", "text": f"{header}\n\n{ad_text}"})
        if campaign.ad.image_base64:
            content.append(_image_block(campaign.ad.image_base64, campaign.ad.image_media_type))
    else:
        header = f"CURRENT STAGE: {label}\n\nBelow is what you actually see on this stage. React as the persona would, then return the JSON response per the instructions."
        text = await resolve_stage_text(url=stage.url, html=stage.html, text=stage.text)
        body = build_stage_content_text(text=text, notes=stage.notes, url=stage.url)
        content.append({"type": "text", "text": f"{header}\n\n{body}"})
        if stage.screenshot_base64:
            content.append(_image_block(stage.screenshot_base64, stage.screenshot_media_type))

    return content


def _coerce_scores(raw: dict) -> StageScores:
    def clamp(v: Any) -> int:
        try:
            n = int(round(float(v)))
        except (TypeError, ValueError):
            n = 5
        return max(0, min(10, n))

    return StageScores(
        clarity=clamp(raw.get("clarity")),
        trust=clamp(raw.get("trust")),
        price_fit=clamp(raw.get("price_fit")),
        urgency=clamp(raw.get("urgency")),
        cta=clamp(raw.get("cta")),
    )


async def simulate_persona(
    *,
    model: str,
    campaign: Campaign,
    persona: Persona,
    anthropic_client: AsyncAnthropic | None,
    usage_total: dict,
) -> PersonaJourney:
    use_cache = not is_ollama_model(model)
    system_blocks = _system_blocks(persona, use_cache)
    prior_reactions: list[dict] = []
    stage_reactions: list[StageReaction] = []
    dropped_at: StageKind | None = None

    for stage in campaign.stages:
        user_content = await _stage_user_content(
            campaign=campaign, stage=stage, prior_reactions=prior_reactions, use_cache=use_cache
        )
        raw, usage = await chat_json(
            model=model,
            max_tokens=MAX_TOKENS,
            system_blocks=system_blocks,
            messages=[{"role": "user", "content": user_content}],
            anthropic_client=anthropic_client,
        )
        accumulate_usage(usage_total, usage)
        reaction = StageReaction(
            stage=stage.kind,
            reaction=str(raw.get("reaction", "")).strip(),
            continues=bool(raw.get("continues", False)),
            drop_reason=raw.get("drop_reason") or None,
            scores=_coerce_scores(raw.get("scores", {})),
            objections=[str(o) for o in (raw.get("objections") or [])],
        )
        stage_reactions.append(reaction)
        prior_reactions.append({"stage": stage.kind, "reaction": reaction.reaction})
        if not reaction.continues:
            dropped_at = stage.kind
            break

    converted = dropped_at is None and len(stage_reactions) == len(campaign.stages)

    summary_content: list[dict] = [
        _product_block(campaign, use_cache),
        {"type": "text", "text": prior_journey_block(prior_reactions)},
        {"type": "text", "text": FINAL_SUMMARY_INSTRUCTIONS},
    ]
    summary_raw, summary_usage = await chat_json(
        model=model,
        max_tokens=MAX_TOKENS,
        system_blocks=system_blocks,
        messages=[{"role": "user", "content": summary_content}],
        anthropic_client=anthropic_client,
    )
    accumulate_usage(usage_total, summary_usage)
    final_summary = str(summary_raw.get("final_summary", "")).strip()
    converted_from_llm = summary_raw.get("converted")
    if isinstance(converted_from_llm, bool):
        converted = converted_from_llm and dropped_at is None

    return PersonaJourney(
        persona_id=persona.id,
        persona_name=persona.name,
        archetype=persona.archetype,
        stages=stage_reactions,
        dropped_at=dropped_at,
        converted=converted,
        final_summary=final_summary,
    )


async def simulate_campaign(
    campaign: Campaign,
    personas: list[Persona],
    *,
    model: str | None = None,
    concurrency: int | None = None,
    anthropic_client: AsyncAnthropic | None = None,
) -> tuple[list[PersonaJourney], dict]:
    model = model or DEFAULT_MODEL
    if not is_ollama_model(model) and anthropic_client is None:
        anthropic_client = AsyncAnthropic()
    sem = asyncio.Semaphore(concurrency or DEFAULT_CONCURRENCY)
    usage_total: dict = {}

    async def _run(persona: Persona) -> PersonaJourney:
        async with sem:
            return await simulate_persona(
                model=model,
                campaign=campaign,
                persona=persona,
                anthropic_client=anthropic_client,
                usage_total=usage_total,
            )

    journeys = await asyncio.gather(*[_run(p) for p in personas])
    return list(journeys), usage_total
