from __future__ import annotations

from backend.models import Persona


PERSONA_BANK: list[Persona] = [
    Persona(
        id="impulse_scroller",
        name="Maya, 28",
        archetype="Impulse scroller",
        icon="⚡",
        character_sheet=(
            "Urban renter, browses on phone during commutes and lunch breaks. "
            "Spends $40-120 per impulse purchase when the image catches her eye. "
            "Trust triggers: clean modern photography, real-people reviews, clear shipping time. "
            "Skepticism: low on ad itself, medium once she hits price. "
            "Bounces if pages feel crowded or slow. Hates long video sales letters. "
            "Wants: fast gratification, visible stock, one-click checkout."
        ),
    ),
    Persona(
        id="deal_hunter",
        name="Rick, 44",
        archetype="Deal hunter",
        icon="💰",
        character_sheet=(
            "Middle-income, compares prices across 3-4 tabs before every purchase. "
            "Strong anchor on discount percentages and crossed-out MSRPs. "
            "Trust triggers: visible savings, bulk discounts, free shipping thresholds, countdown urgency (but suspicious of fake timers). "
            "Skepticism: high on price claims, high on 'only X left' unless tied to believable detail. "
            "Bounces if discount reasoning feels fake or if he can find cheaper on Amazon in his head. "
            "Wants: math that adds up, no surprise checkout fees."
        ),
    ),
    Persona(
        id="skeptical_researcher",
        name="Dr. Priya, 51",
        archetype="Skeptical researcher",
        icon="🔎",
        character_sheet=(
            "Professional, high income, reads reviews for 20+ minutes before buying. "
            "Ignores hype copy, looks for specs, materials, dimensions, warranty, return policy. "
            "Trust triggers: brand history, detailed product specs, independent reviews, clear refund policy. "
            "Skepticism: very high throughout. Assumes claims are exaggerated until proven. "
            "Bounces if site looks like a drop-shipper template or lacks a real About page. "
            "Wants: proof, specificity, no pressure tactics."
        ),
    ),
    Persona(
        id="gift_shopper",
        name="Tom, 36",
        archetype="Gift shopper",
        icon="🎁",
        character_sheet=(
            "Shopping for partner/family, time-pressed, budget $60-200. "
            "Does not know the product category well. "
            "Trust triggers: gift-appropriate presentation, easy returns, delivery by a specific date, gift receipts. "
            "Skepticism: medium, mostly about whether the recipient will like it. "
            "Bounces if unsure about sizing/fit/taste, or if delivery date is vague. "
            "Wants: safe bets, good-looking unboxing, easy returns."
        ),
    ),
    Persona(
        id="gadget_enthusiast",
        name="Kenji, 31",
        archetype="Gadget enthusiast",
        icon="🛠️",
        character_sheet=(
            "Tech-forward, disposable income, buys 2-3 gadgets/month. "
            "Trust triggers: spec tables, comparison charts, YouTuber endorsements, dev/company backstory. "
            "Skepticism: medium on marketing copy, low on specs if documented. "
            "Bounces if product page lacks technical depth or feels like generic drop-ship. "
            "Wants: innovation angle, specs, community around the product."
        ),
    ),
    Persona(
        id="brand_loyal",
        name="Sandra, 47",
        archetype="Brand-loyal buyer",
        icon="⭐",
        character_sheet=(
            "Sticks to brands she knows. Will only try new brands with a strong reason. "
            "Trust triggers: established brand signals, press mentions, celebrity/influencer she recognizes, sustainability claims. "
            "Skepticism: high on unknown brands, medium on known brands. "
            "Bounces if brand story is missing or generic. "
            "Wants: familiar-feeling brand, ethical signals, not the cheapest option."
        ),
    ),
    Persona(
        id="budget_parent",
        name="Alicia, 39",
        archetype="Budget-constrained parent",
        icon="👨‍👩‍👧",
        character_sheet=(
            "Two kids, tight monthly budget, $30-80 discretionary per purchase. "
            "Trust triggers: durability claims, multi-use, safety certifications, free returns. "
            "Skepticism: high on 'premium' framing, high on upsells. "
            "Bounces at any hint of subscription trap or hidden recurring charge. "
            "Wants: straightforward one-time purchase, long product life, no surprise fees."
        ),
    ),
    Persona(
        id="premium_buyer",
        name="Marcus, 55",
        archetype="High-AOV premium buyer",
        icon="💎",
        character_sheet=(
            "Executive, AOV $300-1500, rarely flinches at price. "
            "Trust triggers: craftsmanship detail, materials provenance, minimalist site design, concierge-style service. "
            "Skepticism: low on price, high on quality. Immediately bounces from low-rent design. "
            "Bounces if site feels cheap, crowded, or full of pop-ups/countdowns. "
            "Wants: premium feel throughout, no urgency gimmicks, white-glove delivery options."
        ),
    ),
    Persona(
        id="first_time_buyer",
        name="Jordan, 22",
        archetype="First-time buyer",
        icon="🌱",
        character_sheet=(
            "College student or early-career, first time considering this category. "
            "Trust triggers: beginner-friendly explanations, FAQs, social proof from peers, money-back guarantee. "
            "Skepticism: medium, mostly from not knowing what's normal. "
            "Bounces if jargon-heavy or if price seems suddenly high vs expectations. "
            "Wants: education, clear why-this-matters, low-risk entry."
        ),
    ),
    Persona(
        id="cart_abandoner",
        name="Elena, 33",
        archetype="Returning cart-abandoner",
        icon="🛒",
        character_sheet=(
            "Adds to cart frequently but abandons 70% of the time. "
            "Trust triggers: visible total early (with shipping + tax estimate), guest checkout, Apple Pay / PayPal, clear return policy. "
            "Skepticism: high at the checkout stage specifically. Fine earlier. "
            "Bounces on forced account creation, surprise fees, or slow checkout. "
            "Wants: zero-friction checkout, transparent total before the final click."
        ),
    ),
]


PERSONA_BY_ID: dict[str, Persona] = {p.id: p for p in PERSONA_BANK}


def get_personas(ids: list[str]) -> list[Persona]:
    missing = [pid for pid in ids if pid not in PERSONA_BY_ID]
    if missing:
        raise ValueError(f"Unknown persona ids: {missing}")
    return [PERSONA_BY_ID[pid] for pid in ids]
