from __future__ import annotations

import asyncio
import os
from pathlib import Path

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.aggregator import build_ab_verdict, build_campaign_report
from backend.models import SimulationRequest, SimulationResult
from backend.personas import PERSONA_BANK
from backend.simulator import DEFAULT_MODEL, simulate_campaign


load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"

app = FastAPI(title="Crowdm — Native Ads Audience Simulator", version="0.1.0")


@app.get("/api/personas")
async def list_personas() -> dict:
    return {
        "personas": [
            {"id": p.id, "name": p.name, "archetype": p.archetype, "character_sheet": p.character_sheet}
            for p in PERSONA_BANK
        ]
    }


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "model": DEFAULT_MODEL,
        "has_api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


@app.post("/api/simulate", response_model=SimulationResult)
async def simulate(req: SimulationRequest) -> SimulationResult:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=400, detail="ANTHROPIC_API_KEY not set in environment")
    personas = req.personas
    seen_ids = set()
    for p in personas:
        if not p.character_sheet.strip():
            raise HTTPException(status_code=400, detail=f"Persona {p.name!r} is missing a character sheet")
        if p.id in seen_ids:
            raise HTTPException(status_code=400, detail=f"Duplicate persona id: {p.id}")
        seen_ids.add(p.id)

    model = req.model or DEFAULT_MODEL
    client = AsyncAnthropic()
    usage_total: dict = {}

    async def _run_one(campaign):
        journeys, usage = await simulate_campaign(campaign, personas, model=model)
        for key, val in usage.items():
            usage_total[key] = usage_total.get(key, 0) + val
        ordered_stages = [s.kind for s in campaign.stages]
        report = await build_campaign_report(
            campaign.label,
            journeys,
            ordered_stages,
            client,
            model=model,
            usage_total=usage_total,
        )
        return report

    reports = await asyncio.gather(*[_run_one(c) for c in req.campaigns])

    ab = None
    if len(reports) == 2:
        ab = await build_ab_verdict(
            reports[0], reports[1], client, model=model, usage_total=usage_total
        )

    return SimulationResult(reports=list(reports), ab_verdict=ab, token_usage=usage_total)


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def root() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")
