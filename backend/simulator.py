from __future__ import annotations

import asyncio
import json
import os
import re
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


DEFAULT_MODEL = os.environ.get("CROWDM_MODEL", "claude-opus-4-7")
DEFAULT_CONCURRENCY = int(os.environ.get("CROWDM_CONCURRENCY", "4"))
MAX_TOKENS = 1024


def _ephemeral() -> dict:
    return {"type": "ephemeral"}


def _system_blocks(persona: Persona) -> list[dict]:
    return [
        {"type": "text", "text": EVALUATION_INSTRUCTIONS, "cache_control": _ephemeral()},
        {"type": "text", "text": persona_system_block(persona.character_sheet), "cache_control": _ephemeral()},
    ]


def _product_block(campaign: Campaign) -> dict:
    return {
        "type": "text",
        "text": product_context_block(
            product_name=campaign.product.name,
            product_description=campaign.product.description,
            target_audience=campaign.product.target_audience,
            price=campaign.product.price,
            vertical=campaign.product.vertical,
        ),
        "cache_control": _ephemeral(),
    }


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
) -> list[dict]:
    content: list[dict] = [_product_block(campaign)]
    content.append({"type": "text", "text": prior_journey_block(prior_reactions)})

    if stage.kind == "ad":
        header = stage_header("ad")
        ad_text = ad_stage_text(campaign.ad.headline, campaign.ad.body, campaign.ad.cta)
        content.append({"type": "text", "text": f"{header}\n\n{ad_text}"})
        if campaign.ad.image_base64:
            content.append(_image_block(campaign.ad.image_base64, campaign.ad.image_media_type))
    else:
        header = stage_header(stage.kind)
        text = await resolve_stage_text(url=stage.url, html=stage.html, text=stage.text)
        body = build_stage_content_text(text=text, notes=stage.notes, url=stage.url)
        content.append({"type": "text", "text": f"{header}\n\n{body}"})
        if stage.screenshot_base64:
            content.append(_image_block(stage.screenshot_base64, stage.screenshot_media_type))

    return content


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = _JSON_RE.search(raw)
        if not match:
            raise
        return json.loads(match.group(0))


def _extract_text(message: Any) -> str:
    chunks: list[str] = []
    for block in message.content:
        if getattr(block, "type", None) == "text":
            chunks.append(block.text)
    return "\n".join(chunks)


def _accumulate_usage(usage_total: dict, usage: Any) -> None:
    for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
        val = getattr(usage, key, None) or 0
        usage_total[key] = usage_total.get(key, 0) + val


async def _call_claude(
    client: AsyncAnthropic,
    *,
    model: str,
    system_blocks: list[dict],
    user_content: list[dict],
    usage_total: dict,
) -> dict:
    message = await client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system_blocks,
        messages=[{"role": "user", "content": user_content}],
    )
    _accumulate_usage(usage_total, message.usage)
    raw = _extract_text(message)
    try:
        return _parse_json(raw)
    except json.JSONDecodeError:
        repair = await client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system_blocks,
            messages=[
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "That response was not valid JSON. Resend ONLY the JSON object, no prose."},
            ],
        )
        _accumulate_usage(usage_total, repair.usage)
        return _parse_json(_extract_text(repair))


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
    client: AsyncAnthropic,
    *,
    model: str,
    campaign: Campaign,
    persona: Persona,
    usage_total: dict,
) -> PersonaJourney:
    system_blocks = _system_blocks(persona)
    prior_reactions: list[dict] = []
    stage_reactions: list[StageReaction] = []
    dropped_at: StageKind | None = None

    for stage in campaign.stages:
        user_content = await _stage_user_content(
            campaign=campaign, stage=stage, prior_reactions=prior_reactions
        )
        raw = await _call_claude(
            client,
            model=model,
            system_blocks=system_blocks,
            user_content=user_content,
            usage_total=usage_total,
        )
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
        _product_block(campaign),
        {"type": "text", "text": prior_journey_block(prior_reactions)},
        {"type": "text", "text": FINAL_SUMMARY_INSTRUCTIONS},
    ]
    summary_raw = await _call_claude(
        client,
        model=model,
        system_blocks=system_blocks,
        user_content=summary_content,
        usage_total=usage_total,
    )
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
) -> tuple[list[PersonaJourney], dict]:
    client = AsyncAnthropic()
    model = model or DEFAULT_MODEL
    sem = asyncio.Semaphore(concurrency or DEFAULT_CONCURRENCY)
    usage_total: dict = {}

    async def _run(persona: Persona) -> PersonaJourney:
        async with sem:
            return await simulate_persona(
                client, model=model, campaign=campaign, persona=persona, usage_total=usage_total
            )

    journeys = await asyncio.gather(*[_run(p) for p in personas])
    return list(journeys), usage_total
