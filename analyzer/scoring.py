"""
评分卡 — 100分制，新手卖家视角
核心改变：
  - 需求强度：BSR排名优先，评论数适中（不是越多越好）
  - 竞争可打：专门奖励低评论竞争环境
  - 利润空间：基于真实成本结构
  - 新手适配度：增加"新手进入难度"维度
"""
import logging

log = logging.getLogger(__name__)

# 新手友好价格区间
PRICE_SWEET_MIN = 15.0
PRICE_SWEET_MAX = 60.0


def score_demand(product: dict) -> dict:
    """
    需求强度 (0-20)
    BSR = 有人买的信号；评论数适中（200-2000）= 市场成熟但未饱和
    """
    bsr = product.get("bsr") or 99999
    review_count = product.get("review_count") or 0

    # BSR分（越低越好，说明卖得动）
    if bsr <= 500:
        bsr_score = 12
    elif bsr <= 2000:
        bsr_score = 10
    elif bsr <= 5000:
        bsr_score = 8
    elif bsr <= 20000:
        bsr_score = 5
    elif bsr <= 50000:
        bsr_score = 3
    else:
        bsr_score = 1

    # 评论数分（新手视角：甜蜜区间是200-2000，证明有市场但不饱和）
    if 200 <= review_count <= 2000:
        review_score = 8   # 最佳区间
    elif 100 <= review_count < 200:
        review_score = 6   # 市场刚起步，可以做
    elif 2001 <= review_count <= 5000:
        review_score = 5   # 有市场但竞争激烈
    elif 50 <= review_count < 100:
        review_score = 4   # 太新，不确定
    elif review_count > 5000:
        review_score = 2   # 头部产品，新手进不去
    else:
        review_score = 1

    total = min(20, bsr_score + review_score)
    return {
        "score": total,
        "max": 20,
        "bsr": bsr,
        "review_count": review_count,
        "detail": f"BSR #{bsr:,}（{bsr_score}分），评论数{review_count}（{review_score}分）",
    }


def score_competition(gates: dict) -> dict:
    """
    竞争可打程度 (0-20)
    新手视角：门1（无垄断）+ 门2（有低评论链接）最重要
    """
    gate1 = gates.get("market_concentration", {})
    gate2 = gates.get("entry_barrier", {})
    gate3 = gates.get("price_fit", {})

    # 门1：无品牌垄断（0-10）
    share = gate1.get("top_brand_share", 1.0)
    if not gate1.get("passed"):
        g1_score = 0
    elif share <= 0.30:
        g1_score = 10   # 市场高度分散
    elif share <= 0.45:
        g1_score = 8
    elif share <= 0.55:
        g1_score = 6
    else:
        g1_score = 4    # 接近阈值，勉强通过

    # 门2：有低评论链接可切入（0-8）
    beatable = gate2.get("beatable_count", 0)
    very_new  = gate2.get("very_new_count", 0)
    if not gate2.get("passed"):
        g2_score = 0
    elif very_new >= 2:
        g2_score = 8    # 有超新链接，极好机会
    elif beatable >= 4:
        g2_score = 7
    elif beatable >= 2:
        g2_score = 5
    else:
        g2_score = 2

    # 门3：价格适配（0-2 bonus）
    g3_bonus = 2 if gate3.get("passed") else 0

    total = min(20, g1_score + g2_score + g3_bonus)
    return {
        "score": total,
        "max": 20,
        "detail": f"品牌集中度{g1_score}分，可切入链接{g2_score}分",
    }


def score_profit(product: dict, config: dict) -> dict:
    """
    利润空间 (0-20)
    基于亚马逊真实费用结构估算净利润
    """
    price = product.get("price") or 0
    if price <= 0:
        return {"score": 0, "max": 20, "detail": "无售价"}

    pm = config["profit_model"]
    referral = price * pm.get("amazon_referral_fee_pct", 0.15)  # 大部分类目15%
    fba = pm.get("fba_fee_usd", 3.86)

    # COGS估算：中国货源一般是售价的20-30%
    cogs_pct = 0.25
    cogs = price * cogs_pct

    # 头程运费估算（小件空运约$2/件）
    shipping = 2.0

    net_profit = price - referral - fba - cogs - shipping
    margin_pct = net_profit / price if price > 0 else 0

    # 额外：价格在甜蜜区间加分
    price_bonus = 2 if PRICE_SWEET_MIN <= price <= PRICE_SWEET_MAX else 0

    if margin_pct >= 0.40 and net_profit >= 10:
        base = 18
    elif margin_pct >= 0.30 and net_profit >= 7:
        base = 14
    elif margin_pct >= 0.20 and net_profit >= 5:
        base = 9
    elif margin_pct >= 0.10 and net_profit >= 3:
        base = 5
    else:
        base = 0

    total = min(20, base + price_bonus)
    return {
        "score": total,
        "max": 20,
        "estimated_net_profit_usd": round(net_profit, 2),
        "gross_margin_pct": round(margin_pct * 100, 1),
        "selling_price": price,
        "detail": f"${price}售价，估算净利${net_profit:.1f}（利润率{margin_pct:.0%}）",
    }


def score_supply_chain(product: dict) -> dict:
    """
    供应链复杂度 (0-10，越简单分越高)
    新手首选：小件、无电池、无液体、无精密电子
    """
    title = (product.get("title") or "").lower()
    price = product.get("price") or 0

    # 复杂信号（扣分）
    complex_signals = [
        "electric", "battery", "motor", "pump", "hydraulic",
        "glass", "ceramic", "liquid", "fragile", "bluetooth",
        "wifi", "smart", "electronic", "LED display",
    ]
    # 简单信号（加分）
    simple_signals = [
        "bag", "case", "cover", "strap", "clip", "hook",
        "organizer", "holder", "pouch", "wallet", "keychain",
        "mat", "pad", "sleeve", "wrap", "band", "ring",
    ]

    neg = sum(1 for s in complex_signals if s in title)
    pos = sum(1 for s in simple_signals if s in title)

    # 价格越低一般越简单
    if price < 25:
        price_factor = 1.2
    elif price < 40:
        price_factor = 1.0
    else:
        price_factor = 0.8

    raw = (5 + pos * 1.5 - neg * 2.0) * price_factor
    score = max(0, min(10, int(raw)))
    return {
        "score": score,
        "max": 10,
        "detail": f"+{pos}简单信号，-{neg}复杂信号",
    }


def score_compliance(product: dict) -> dict:
    """
    合规风险 (0-10，风险越低分越高)
    高风险类目对新手是灾难，直接扣分
    """
    title = (product.get("title") or "").lower()
    category = (product.get("bsr_category") or "").lower()
    text = title + " " + category

    high_risk = ["battery", "lithium", "electric", "laser", "medical", "fda",
                 "baby", "infant", "food", "dietary", "supplement", "chemical",
                 "gun", "knife", "blade", "flammable"]
    med_risk   = ["bluetooth", "wifi", "smart", "electronic", "power bank"]

    high_count = sum(1 for s in high_risk if s in text)
    med_count  = sum(1 for s in med_risk  if s in text)

    if high_count >= 2:
        score = 0
    elif high_count == 1:
        score = 4
    elif med_count >= 2:
        score = 6
    elif med_count == 1:
        score = 8
    else:
        score = 10

    return {
        "score": score,
        "max": 10,
        "high_risk_signals": high_count,
        "med_risk_signals": med_count,
    }


def score_review_pain_points(gate4: dict) -> dict:
    """评论痛点可改造性 (0-10)"""
    if not gate4:
        return {"score": 2, "max": 10}

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

    return {"score": score, "max": 10, "pain_count": pain_count}


def score_viral_potential(product: dict) -> dict:
    """
    内容传播潜力 (0-10)
    适合短视频/图文种草的产品天然有流量优势
    """
    title = (product.get("title") or "").lower()
    price = product.get("price") or 0

    viral_signals = [
        "gift", "cute", "funny", "unique", "personalized", "custom",
        "aesthetic", "trendy", "cool", "creative", "handmade",
        "novelty", "surprise", "wedding", "birthday", "graduation",
        "minimalist", "portable", "compact", "foldable",
    ]
    count = sum(1 for s in viral_signals if s in title)

    # $20-45 是冲动消费最佳区间
    if 20 <= price <= 45:
        price_bonus = 4
    elif 15 <= price <= 55:
        price_bonus = 2
    else:
        price_bonus = 0

    score = min(10, count * 2 + price_bonus + 1)
    return {"score": score, "max": 10, "viral_signals": count}


def score_newbie_fit(product: dict, gates: dict) -> dict:
    """
    新手适配度 (0-10) — 新增维度
    综合考量：竞品评论总量、价格、供应链
    """
    competitors = product.get("competitors_top10", [])
    avg_competitor_reviews = (
        sum(c.get("review_count") or 0 for c in competitors[:10]) /
        max(len(competitors[:10]), 1)
    ) if competitors else 0

    price = product.get("price") or 0

    # 平均竞品评论数越低越好
    if avg_competitor_reviews < 200:
        review_score = 5
    elif avg_competitor_reviews < 500:
        review_score = 4
    elif avg_competitor_reviews < 1000:
        review_score = 3
    elif avg_competitor_reviews < 3000:
        review_score = 1
    else:
        review_score = 0

    # 价格适配
    price_score = 3 if PRICE_SWEET_MIN <= price <= PRICE_SWEET_MAX else 1

    # 首批备货成本友好（低价格 = 可以多试几款）
    budget_score = 2 if price < 35 else (1 if price < 50 else 0)

    total = min(10, review_score + price_score + budget_score)
    return {
        "score": total,
        "max": 10,
        "avg_competitor_reviews": int(avg_competitor_reviews),
        "detail": f"竞品均评论{int(avg_competitor_reviews)}个，价格${price}",
    }


def calculate_total_score(product: dict, gates: dict, gate4: dict, config: dict) -> dict:
    """计算完整评分卡（100分制，8个维度）。"""
    s_demand     = score_demand(product)
    s_comp       = score_competition(gates)
    s_profit     = score_profit(product, config)
    s_supply     = score_supply_chain(product)
    s_compliance = score_compliance(product)
    s_pain       = score_review_pain_points(gate4)
    s_viral      = score_viral_potential(product)
    s_newbie     = score_newbie_fit(product, gates)

    # 总分：前7维各自满分合计90，新手适配度10分，共100分
    total = (
        s_demand["score"] +
        s_comp["score"] +
        s_profit["score"] +
        s_supply["score"] +
        s_compliance["score"] +
        s_pain["score"] +
        s_viral["score"] +
        s_newbie["score"]
    )

    return {
        "total": total,
        "max": 100,
        "breakdown": {
            "demand_strength":        s_demand,
            "competition_beatable":   s_comp,
            "profit_margin":          s_profit,
            "supply_chain_complexity":s_supply,
            "compliance_risk":        s_compliance,
            "review_pain_improvable": s_pain,
            "content_viral_potential":s_viral,
            "newbie_fit":             s_newbie,
        },
    }
