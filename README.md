# Crowdm — Native Ads Audience Simulator

A local tool that walks a bank of synthetic e-commerce shoppers through your native-ads funnel (ad → landing A → landing B → structure → price → checkout → item) and tells you where and why each persona drops off. Produces per-persona reactions, stage drop-off, quality scores, top issues, and optional A/B verdicts.

**Directional qualitative insight.** Not a CTR/CVR predictor. Use this to catch messaging gaps, trust issues, and funnel friction before you spend real traffic budget — not to replace real A/B tests.

## What you get

- **Per-stage drop-off** — which personas leave at which step, and why.
- **Persona reactions** — first-person reactions from 10 e-commerce archetypes (impulse scroller, deal hunter, skeptical researcher, gift shopper, gadget enthusiast, brand-loyal, budget parent, premium buyer, first-time buyer, cart-abandoner).
- **Quality scores** — clarity, trust, price-fit, urgency, CTA strength (0–10) per stage.
- **Top issues** — clustered objections with concrete recommendations.
- **A/B verdict** — winner per persona and overall when you submit two variants.

## Setup

```bash
cd Crowdm
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# edit .env and paste your ANTHROPIC_API_KEY
```

## Run

```bash
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
uvicorn backend.main:app --reload --port 8000
```

Then open http://localhost:8000 in your browser.

## Using the UI

1. Fill in **Product & audience** (name, price as shown to the user, target audience, description).
2. Fill in the **Ad creative** (headline, body, CTA, optional image).
3. For each **funnel stage** you have, provide a URL (we'll fetch and extract readable text), pasted text/HTML, or a screenshot. Disable stages you don't have.
4. Pick the **personas** you want to test (6 selected by default).
5. Optionally enable **A/B** and fill in variant-B overrides.
6. Click **Run simulation**. Expect ~30–90 seconds depending on persona count.
7. Review the report: funnel drop-off chart, top issues with recommendations, and each persona's full journey.

Click **Load demo campaign** to try a prefilled example (the AuroraGlow sunrise alarm).

## CLI / headless use

```bash
curl -sX POST http://localhost:8000/api/simulate \
  -H 'Content-Type: application/json' \
  -d @samples/demo_campaign.json | jq
```

## Configuration

Environment variables (set in `.env`):

- `ANTHROPIC_API_KEY` — required.
- `CROWDM_MODEL` — defaults to `claude-opus-4-7`. Set to `claude-sonnet-4-6` for faster/cheaper runs.
- `CROWDM_CONCURRENCY` — parallel personas per campaign, default `4`.

## Cost

Each persona takes 1 call per enabled stage + 1 final summary call. With default 6 personas × 5 stages = ~36 calls per campaign. Prompt caching (applied to the evaluation instructions, persona sheet, and product context) drops this substantially after the first persona — expect most input tokens to be cache reads, not full-rate input.

Token usage is included in every simulation response.

## Honest limits

- Synthetic audiences are directional. They catch obvious messaging/UX/funnel issues, not edge cases of real-world behavior.
- Personas are English-speaking US-style shoppers. Non-US / non-English campaigns will be less accurate.
- URL fetching only pulls static HTML. Pages that render primarily via JS need a screenshot or pasted text.
- Not a replacement for real A/B tests with live traffic.

## Layout

```
backend/      # FastAPI backend, Claude API client, simulation + aggregation
frontend/     # Single-page UI (Alpine.js + Tailwind + Chart.js via CDN)
samples/      # Example campaign payload
```
