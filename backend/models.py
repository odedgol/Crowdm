from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


StageKind = Literal["ad", "landing_a", "landing_b", "structure", "price", "checkout", "item"]

STAGE_ORDER: list[StageKind] = ["ad", "landing_a", "landing_b", "structure", "price", "checkout", "item"]

STAGE_LABELS: dict[StageKind, str] = {
    "ad": "Native ad",
    "landing_a": "Landing page A",
    "landing_b": "Landing page B",
    "structure": "Structure / offer page",
    "price": "Price page",
    "checkout": "Checkout",
    "item": "Item / product",
}


class AdCreative(BaseModel):
    headline: str
    body: str = ""
    cta: str = ""
    image_base64: Optional[str] = None
    image_media_type: Optional[str] = None


class StageContent(BaseModel):
    kind: StageKind
    label: Optional[str] = None
    url: Optional[str] = None
    html: Optional[str] = None
    text: Optional[str] = None
    screenshot_base64: Optional[str] = None
    screenshot_media_type: Optional[str] = None
    notes: Optional[str] = None


class Persona(BaseModel):
    id: str
    name: str
    archetype: str
    character_sheet: str
    icon: Optional[str] = None


class ProductContext(BaseModel):
    name: str
    description: str
    target_audience: str
    price: str
    vertical: str = "e-commerce / physical products"


class Campaign(BaseModel):
    label: str
    product: ProductContext
    ad: AdCreative
    stages: list[StageContent]


class SimulationRequest(BaseModel):
    campaigns: list[Campaign] = Field(..., min_length=1, max_length=2)
    personas: list[Persona] = Field(..., min_length=1)
    model: Optional[str] = None
    concurrency: Optional[int] = Field(default=None, ge=1, le=16)


class StageScores(BaseModel):
    clarity: int = Field(ge=0, le=10)
    trust: int = Field(ge=0, le=10)
    price_fit: int = Field(ge=0, le=10)
    urgency: int = Field(ge=0, le=10)
    cta: int = Field(ge=0, le=10)


class StageReaction(BaseModel):
    stage: StageKind
    reaction: str
    continues: bool
    drop_reason: Optional[str] = None
    scores: StageScores
    objections: list[str] = []


class PersonaJourney(BaseModel):
    persona_id: str
    persona_name: str
    archetype: str
    stages: list[StageReaction]
    dropped_at: Optional[StageKind] = None
    converted: bool = False
    final_summary: str = ""


class StageAggregate(BaseModel):
    stage: StageKind
    label: str
    entered: int
    continued: int
    drop_off_rate: float
    mean_scores: StageScores


IssueCategory = Literal["URGENCY", "TRUST", "PRICE", "CLARITY", "CTA", "FRICTION", "OTHER"]


class TopIssue(BaseModel):
    title: str
    stage: Optional[StageKind] = None
    category: IssueCategory = "OTHER"
    frequency: int
    example_quotes: list[str] = []
    recommendation: str = ""


class ABVerdict(BaseModel):
    overall_winner: str
    overall_reasoning: str
    per_persona: list[dict]


class CampaignReport(BaseModel):
    campaign_label: str
    personas: list[PersonaJourney]
    stage_aggregates: list[StageAggregate]
    top_issues: list[TopIssue]
    conversion_rate: float


class SimulationResult(BaseModel):
    reports: list[CampaignReport]
    ab_verdict: Optional[ABVerdict] = None
    token_usage: dict
