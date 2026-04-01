"""
评分卡 — 100分制，七个维度
"""

import logging

log = logging.getLogger(__name__)

WEIGHTS = {
    "demand_strength": 20,
    "competition_beatable": 20,
    "profit_margin": 20,
    "supply_chain_complexity": 10,
    "compliance_risk": 10,
    "review_pain_improvable": 10,
    "content_viral_potential": 10,
}


def score_demand(product: dict) -> dict:
    """需求强度 (0-20)"""
    bsr = product.get("bsr") or 99999
    review_count = product.get("review_count") or 0

    # BSR score: lower BSR = higher demand
    if bsr <= 1000:
        bsr_score = 10
    elif bsr <= 5000:
        bsr_score = 8
    elif bsr <= 20000:
        bsr_score = 6
    elif bsr <= 50000:
        bsr_score = 4
    elif bsr <= 100000:
        bsr_score = 2
    else:
        bsr_score = 1

    # Review volume as demand proxy
    if review_count >= 5000:
        review_score = 10
    elif review_count >= 1000:
        review_score = 8
    elif review_count >= 500:
        review_score = 6
    elif review_count >= 200:
        review_score = 4
    elif review_count >= 50:
        review_score = 2
    else:
        review_score = 1

    raw = bsr_score + review_score
    score = min(20, raw)
    return {"score": score, "max": 20, "bsr": bsr, "review_count": review_count}


def score_competition(gates: dict) -> dict:
    """竞争可打程度 (0-20)"""
    gates_passed = sum([
        gates.get("market_concentration", {}).get("passed", False),
        gates.get("entry_barrier", {}).get("passed", False),
        gates.get("keyword_opportunity", {}).get("passed", False),
    ])

    score_map = {3: 20, 2: 14, 1: 7, 0: 0}
    score = score_map.get(gates_passed, 0)
    return {"score": score, "max": 20, "gates_passed": f"{gates_passed}/3"}


def score_profit(product: dict, config: dict) -> dict:
    """利润空间 (0-20)"""
    price = product.get("price") or 0
    if price <= 0:
        return {"score": 0, "max": 20, "detail": "No price data"}

    pm = config["profit_model"]
    referral = price * pm["amazon_referral_fee_pct"]
    fba = pm["fba_fee_usd"]

    # Estimate COGS at 30% of selling price for typical Chinese-sourced goods
    estimated_cogs = price * 0.30
    net_profit = price - referral - fba - estimated_cogs
    gross_margin = (price - estimated_cogs) / price if price > 0 else 0

    if gross_margin >= 0.55 and net_profit >= 8:
        score = 20
    elif gross_margin >= 0.45 and net_profit >= 5:
        score = 16
    elif gross_margin >= 0.35 and net_profit >= 3:
        score = 10
    elif gross_margin >= 0.25:
        score = 5
    else:
        score = 0

    return {
        "score": score,
        "max": 20,
        "estimated_net_profit_usd": round(net_profit, 2),
        "gross_margin_pct": round(gross_margin * 100, 1),
        "selling_price": price,
    }


def score_supply_chain(product: dict) -> dict:
    """供应链复杂度 (0-10, 越简单分越高)"""
    title = (product.get("title") or "").lower()
    price = product.get("price") or 0

    # Complexity signals
    complex_signals = [
        "electronic", "battery", "electric", "motor", "pump",
        "glass", "ceramic", "fragile", "liquid", "bulky"
    ]
    simple_signals = [
        "bag", "case", "cover", "strap", "clip", "hook",
        "organizer", "holder", "pouch", "wallet", "keychain"
    ]

    complexity_score = sum(1 for s in complex_signals if s in title)
    simplicity_score = sum(1 for s in simple_signals if s in title)

    # Lower price often = simpler product
    price_factor = 1 if price < 30 else (0.7 if price < 60 else 0.4)

    raw = max(0, (simplicity_score * 2 - complexity_score * 1.5)) * price_factor
    score = min(10, max(0, int(raw + 5)))  # Base 5, adjust

    return {"score": score, "max": 10, "detail": f"+{simplicity_score} simple, -{complexity_score} complex signals"}


def score_compliance(product: dict) -> dict:
    """合规风险 (0-10, 风险越低分越高)"""
    title = (product.get("title") or "").lower()
    category = (product.get("bsr_category") or "").lower()

    risk_signals = [
        "battery", "lithium", "electric", "laser", "medical", "fda",
        "baby", "infant", "food", "dietary", "supplement", "chemical"
    ]
    risk_count = sum(1 for s in risk_signals if s in title or s in category)

    if risk_count == 0:
        score = 10
    elif risk_count == 1:
        score = 7
    elif risk_count == 2:
        score = 4
    else:
        score = 0

    return {"score": score, "max": 10, "risk_signals_found": risk_count}


def score_review_pain_points(gate4: dict) -> dict:
    """评论痛点可改造性 (0-10)"""
    if not gate4:
        return {"score": 3, "max": 10}

    pain_count = gate4.get("pain_point_count", 0)
    improvable = gate4.get("improvable", False)

    if improvable and pain_count >= 3:
        score = 10
    elif improvable and pain_count >= 2:
        score = 8
    elif improvable:
        score = 6
    elif pain_count >= 1:
        score = 3
    else:
        score = 1

    return {"score": score, "max": 10, "pain_count": pain_count, "improvable": improvable}


def score_viral_potential(product: dict) -> dict:
    """内容传播潜力 (0-10)"""
    title = (product.get("title") or "").lower()
    price = product.get("price") or 0

    viral_signals = [
        "gift", "cute", "funny", "unique", "personalized", "custom",
        "aesthetic", "trendy", "cool", "creative", "handmade", "artisan",
        "novelty", "surprise", "wedding", "birthday"
    ]
    viral_count = sum(1 for s in viral_signals if s in title)

    # Sweet spot for impulse buy / gifting: $15-45
    if 15 <= price <= 45:
        price_bonus = 3
    elif 10 <= price <= 60:
        price_bonus = 2
    else:
        price_bonus = 0

    score = min(10, viral_count * 2 + price_bonus + 2)  # Base 2
    return {"score": score, "max": 10, "viral_signals": viral_count}


def calculate_total_score(product: dict, gates: dict, gate4: dict, config: dict) -> dict:
    """Calculate full scorecard for a product."""
    s_demand = score_demand(product)
    s_comp = score_competition(gates)
    s_profit = score_profit(product, config)
    s_supply = score_supply_chain(product)
    s_compliance = score_compliance(product)
    s_pain = score_review_pain_points(gate4)
    s_viral = score_viral_potential(product)

    total = (
        s_demand["score"] +
        s_comp["score"] +
        s_profit["score"] +
        s_supply["score"] +
        s_compliance["score"] +
        s_pain["score"] +
        s_viral["score"]
    )

    return {
        "total": total,
        "max": 100,
        "breakdown": {
            "demand_strength": s_demand,
            "competition_beatable": s_comp,
            "profit_margin": s_profit,
            "supply_chain_complexity": s_supply,
            "compliance_risk": s_compliance,
            "review_pain_improvable": s_pain,
            "content_viral_potential": s_viral,
        }
    }
