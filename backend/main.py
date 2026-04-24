from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.aggregator import build_ab_verdict, build_campaign_report
from backend.extractor import resolve_stage_text
from backend.llm import OllamaUnavailable, is_ollama_model
from backend.models import SimulationRequest, SimulationResult
from backend.personas import PERSONA_BANK
from backend.simulator import DEFAULT_MODEL, simulate_campaign


load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"

app = FastAPI(title="Crowdm — Native Ads Audience Simulator", version="0.2.0")


class PreviewRequest(BaseModel):
    url: Optional[str] = None
    html: Optional[str] = None
    text: Optional[str] = None


@app.get("/api/personas")
async def list_personas() -> dict:
    return {
        "personas": [
            {
                "id": p.id,
                "name": p.name,
                "archetype": p.archetype,
                "character_sheet": p.character_sheet,
                "icon": p.icon or "👤",
            }
            for p in PERSONA_BANK
        ]
    }


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "default_model": DEFAULT_MODEL,
        "has_anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "ollama_base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
    }


@app.post("/api/preview_stage")
async def preview_stage(req: PreviewRequest) -> dict:
    text = await resolve_stage_text(url=req.url, html=req.html, text=req.text)
    if text is None:
        return {"ok": False, "text": None, "word_count": 0, "char_count": 0}
    words = len(text.split())
    return {
        "ok": True,
        "text": text,
        "word_count": words,
        "char_count": len(text),
    }


@app.post("/api/simulate", response_model=SimulationResult)
async def simulate(req: SimulationRequest) -> SimulationResult:
    model = req.model or DEFAULT_MODEL

    if not is_ollama_model(model) and not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=400,
            detail="ANTHROPIC_API_KEY not set. Either set it in your environment, or pick an ollama:<model> in the config.",
        )

    personas = req.personas
    seen_ids: set[str] = set()
    for p in personas:
        if not p.character_sheet.strip():
            raise HTTPException(status_code=400, detail=f"Persona {p.name!r} is missing a character sheet")
        if p.id in seen_ids:
            raise HTTPException(status_code=400, detail=f"Duplicate persona id: {p.id}")
        seen_ids.add(p.id)

    anthropic_client = None if is_ollama_model(model) else AsyncAnthropic()
    usage_total: dict = {}
    concurrency = req.concurrency

    async def _run_one(campaign):
        journeys, usage = await simulate_campaign(
            campaign,
            personas,
            model=model,
            concurrency=concurrency,
            anthropic_client=anthropic_client,
        )
        for key, val in usage.items():
            usage_total[key] = usage_total.get(key, 0) + val
        ordered_stages = [s.kind for s in campaign.stages]
        report = await build_campaign_report(
            campaign.label,
            journeys,
            ordered_stages,
            model=model,
            anthropic_client=anthropic_client,
            usage_total=usage_total,
        )
        return report

    try:
        reports = await asyncio.gather(*[_run_one(c) for c in req.campaigns])
    except OllamaUnavailable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ab = None
    if len(reports) == 2:
        ab = await build_ab_verdict(
            reports[0],
            reports[1],
            model=model,
            anthropic_client=anthropic_client,
            usage_total=usage_total,
        )

    return SimulationResult(reports=list(reports), ab_verdict=ab, token_usage=usage_total)


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def root() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/mocks")
    async def mocks_redirect() -> RedirectResponse:
        return RedirectResponse(url="/static/mocks/index.html")
