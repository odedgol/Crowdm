from __future__ import annotations

from backend.models import StageKind, STAGE_LABELS


EVALUATION_INSTRUCTIONS = """You are role-playing as a specific real-feeling online shopper evaluating a native-ads funnel for an e-commerce product. You will be shown one funnel stage at a time, in order. Your job is to react exactly as this persona would — not as an advertising expert and not as a generic reviewer.

Rules you must follow on every stage:

1. Stay in character. Use first-person voice. React emotionally and practically, the way this persona would in 10-30 seconds of actually looking at the page on their phone or laptop.

2. Be specific. Refer to things you actually see in the content (headline wording, price, image details, copy phrases, missing info). Generic reactions are not useful.

3. Decide honestly whether you would continue to the next stage. A persona who hates ads will bounce from most funnels — that is signal, not a problem. Do not fake-continue to be polite.

4. Score the stage from your persona's point of view on 5 dimensions, each 0-10:
   - clarity: is the message and next step obvious?
   - trust: does it feel credible and safe?
   - price_fit: does the perceived value match what you expect to pay (for stages without visible price, score based on what price the page is setting you up for)
   - urgency: is there a compelling reason to act now? (no artificial urgency scoring — real urgency only)
   - cta: is the next action clear and compelling?

5. List specific objections — concrete things that made you hesitate or bounce. Use verbatim-style fragments, not generic advertising critique.

Respond ONLY as a single valid JSON object matching this exact schema, no prose outside the JSON:

{
  "reaction": "2-4 sentences in first person describing what I feel, notice, and think at this stage",
  "continues": true | false,
  "drop_reason": "if continues is false, one sentence on why I bounced; else null",
  "scores": {
    "clarity": 0-10,
    "trust": 0-10,
    "price_fit": 0-10,
    "urgency": 0-10,
    "cta": 0-10
  },
  "objections": ["short verbatim-style objection", "another one"]
}
"""


FINAL_SUMMARY_INSTRUCTIONS = """The persona has finished walking the funnel (either converted or bounced). Summarize in 2-3 sentences, in the persona's first-person voice, what the overall experience was and what would have made them more likely to convert. Respond ONLY as a single valid JSON object:

{
  "final_summary": "2-3 sentences in first person",
  "converted": true | false
}
"""


def persona_system_block(character_sheet: str) -> str:
    return f"You are role-playing the following specific shopper. Fully inhabit this persona:\n\n{character_sheet}\n\nYou will be asked to react to one funnel stage at a time. Stay in this persona's voice and priorities across every stage."


def product_context_block(product_name: str, product_description: str, target_audience: str, price: str, vertical: str) -> str:
    return (
        "CAMPAIGN CONTEXT (stable across this entire funnel walk):\n"
        f"- Product: {product_name}\n"
        f"- Vertical: {vertical}\n"
        f"- Target audience the advertiser has in mind: {target_audience}\n"
        f"- Stated price: {price}\n"
        f"- Product description provided by the advertiser: {product_description}\n\n"
        "Note: the persona does not automatically know any of this. The persona only learns what each funnel stage actually reveals. Use this context only as ground truth for your evaluation, not as things the persona already knows."
    )


def prior_journey_block(prior: list[dict]) -> str:
    if not prior:
        return "PRIOR JOURNEY: This is the first stage you are seeing. You have not yet visited any other page in this funnel."
    lines = ["PRIOR JOURNEY (what you already saw and thought, in order):"]
    for entry in prior:
        lines.append(f"- {STAGE_LABELS.get(entry['stage'], entry['stage'])}: {entry['reaction']}")
    return "\n".join(lines)


def stage_header(stage: StageKind) -> str:
    label = STAGE_LABELS.get(stage, stage)
    return f"CURRENT STAGE: {label}\n\nBelow is what you actually see on this stage. React as the persona would, then return the JSON response per the instructions."


def ad_stage_text(headline: str, body: str, cta: str) -> str:
    parts = [f"Headline: {headline}"]
    if body:
        parts.append(f"Body: {body}")
    if cta:
        parts.append(f"CTA button: {cta}")
    parts.append("(This is being shown inside a native-ad slot on a publisher site, mixed among editorial content.)")
    return "\n".join(parts)


def build_stage_content_text(*, text: str | None, notes: str | None, url: str | None) -> str:
    parts: list[str] = []
    if url:
        parts.append(f"(Source URL: {url})")
    if text:
        parts.append(text)
    if notes:
        parts.append(f"Advertiser notes on this stage: {notes}")
    if not parts:
        parts.append("(No extracted text — rely on the screenshot image if one was provided.)")
    return "\n\n".join(parts)


CLUSTERING_PROMPT = """You are analyzing objections raised by a simulated synthetic audience during a native-ads funnel evaluation. Cluster the objections into 5-8 distinct recurring issues. For each cluster provide a short title, a category, the funnel stage most associated with it (or null if cross-cutting), the number of times it was raised (frequency), 1-3 verbatim example quotes, and a concrete recommendation the advertiser could implement.

Categories (pick the single best fit):
- URGENCY: artificial scarcity, countdown timers, fake deadlines
- TRUST: credibility gaps, missing proof, sketchy design, missing reviews/about/warranty
- PRICE: price too high, pricing confusion, hidden fees, surprise costs
- CLARITY: unclear message, confusing copy, missing information
- CTA: weak or unclear call-to-action, button copy, friction clicking forward
- FRICTION: checkout problems, forced signup, slow pages, broken flow
- OTHER: anything that does not fit the above

Respond ONLY as a single valid JSON object:

{
  "issues": [
    {
      "title": "short title, 4-8 words",
      "category": "URGENCY" | "TRUST" | "PRICE" | "CLARITY" | "CTA" | "FRICTION" | "OTHER",
      "stage": "ad" | "landing_a" | "landing_b" | "structure" | "price" | "checkout" | "item" | null,
      "frequency": integer,
      "example_quotes": ["verbatim-style quote", "..."],
      "recommendation": "one concrete action the advertiser can take"
    }
  ]
}

Order the issues by frequency descending. Do not invent objections not present in the input.
"""


AB_VERDICT_PROMPT = """You are comparing two campaign variants (A and B) that were evaluated by the same set of synthetic personas walking the same funnel structure. Given the two campaign reports, decide per-persona which variant served that persona better, and declare an overall winner.

Respond ONLY as a single valid JSON object:

{
  "overall_winner": "A" | "B" | "tie",
  "overall_reasoning": "2-3 sentences explaining the overall call",
  "per_persona": [
    {
      "persona_id": "...",
      "persona_name": "...",
      "winner": "A" | "B" | "tie",
      "reason": "one sentence"
    }
  ]
}
"""
