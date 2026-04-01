"""
四个门过滤器 — 专为新手卖家设计
核心原则：
  - 门1 市场集中度：头部品牌不能垄断（<60% 才过）
  - 门2 进入门槛：Top10 中要有低评论数产品（<500 reviews）
  - 门3 价格战检测：价格区间过于集中 = 红海价格战，排除
  - 门4 评论痛点：要有明确可改造痛点
三层输出：blue_ocean / red_ocean_beatable / red_ocean_avoid
"""

import logging
from typing import Literal

log = logging.getLogger(__name__)

Tier = Literal["blue_ocean", "red_ocean_beatable", "red_ocean_avoid"]

# 新手友好价格区间（过低利润差，过高资金压力）
PRICE_MIN = 15.0
PRICE_MAX = 60.0

# 头部品牌评论数阈值——超过这个的算"老链接"
HIGH_REVIEW_THRESHOLD = 500
# Top10 中至少要有这么多"可切入"链接（低评论）
MIN_BEATABLE_LISTINGS = 2


def analyze_market_concentration(competitors: list[dict], threshold: float = 0.60) -> dict:
    """
    门1：市场集中度
    用评论数×评分估算各品牌相对销量占比。
    头部单品牌 >60% → FAIL（新手根本插不进去）
    同时检测是否已进入价格战（Top10 均价极度收敛）
    """
    if not competitors:
        return {"passed": True, "top_brand_share": 0.0, "detail": "无竞品数据，默认通过"}

    top10 = competitors[:10]

    # 品牌占比
    brand_scores: dict[str, float] = {}
    total_score = 0.0
    for c in top10:
        brand = (c.get("brand") or "Unknown").strip()
        score = (c.get("review_count") or 0) * max(c.get("rating") or 3.0, 1.0)
        brand_scores[brand] = brand_scores.get(brand, 0.0) + score
        total_score += score

    if total_score == 0:
        return {"passed": True, "top_brand_share": 0.0, "detail": "无法计算"}

    top_brand = max(brand_scores, key=brand_scores.get)
    top_share = brand_scores[top_brand] / total_score

    # 价格战检测：Top10 价格极差 < $3 且均价 < $20 → 价格战红海
    prices = [c.get("price") or 0 for c in top10 if (c.get("price") or 0) > 0]
    price_war = False
    price_war_reason = ""
    if len(prices) >= 5:
        price_range = max(prices) - min(prices)
        avg_price = sum(prices) / len(prices)
        if price_range < 3.0 and avg_price < 20.0:
            price_war = True
            price_war_reason = f"价格极差仅${price_range:.1f}，均价${avg_price:.1f}，已陷价格战"

    passed = top_share <= threshold and not price_war
    return {
        "passed": passed,
        "top_brand": top_brand,
        "top_brand_share": round(top_share, 3),
        "threshold": threshold,
        "price_war": price_war,
        "price_war_reason": price_war_reason,
        "detail": f"{top_brand} 占约 {top_share:.0%} 估算销量" + (f"；{price_war_reason}" if price_war else ""),
        "warning": not passed,
    }


def analyze_entry_barrier(competitors: list[dict],
                           high_review_threshold: int = HIGH_REVIEW_THRESHOLD) -> dict:
    """
    门2：进入门槛
    Top10 中 <500 评论的链接 >= 2 个 → 有机会切入
    同时检测：是否所有Top10都是老链接（>2000评论）→ 新手完全没机会
    """
    if not competitors:
        return {"passed": True, "beatable_count": 0, "detail": "无竞品数据"}

    top10 = competitors[:10]
    beatable = [c for c in top10 if (c.get("review_count") or 0) < high_review_threshold]
    very_new  = [c for c in top10 if (c.get("review_count") or 0) < 200]
    entrenched = [c for c in top10 if (c.get("review_count") or 0) > 2000]

    # 全部都是老链接 → 红海
    all_entrenched = len(entrenched) >= 8

    passed = len(beatable) >= MIN_BEATABLE_LISTINGS and not all_entrenched

    return {
        "passed": passed,
        "beatable_count": len(beatable),
        "very_new_count": len(very_new),
        "entrenched_count": len(entrenched),
        "all_entrenched": all_entrenched,
        "detail": (
            f"Top10中{len(beatable)}个低评论链接（<{high_review_threshold}）"
            + ("，全是老链接新手无法突破" if all_entrenched else "")
        ),
        "warning": not passed,
    }


def analyze_price_fit(product: dict) -> dict:
    """
    门3（替换关键词门）：价格适配度
    新手视角：$15-$60 是最友好区间
    - 太低（<$15）：利润几乎为零，打不起价格战
    - 太高（>$60）：资金压力大、消费者决策慢、退货率高
    同时检测售价是否合理（不能是$0）
    """
    price = product.get("price") or 0.0

    if price <= 0:
        return {"passed": False, "detail": "无售价数据", "warning": True, "price": 0}

    in_range = PRICE_MIN <= price <= PRICE_MAX

    # 生成长尾关键词建议（保留原门3逻辑）
    keyword = product.get("keyword", "")
    base_words = keyword.split()
    long_tails = []
    if len(base_words) <= 4:
        long_tails = [
            f"{keyword} for women",
            f"{keyword} gift",
            f"best {keyword} 2025",
            f"{keyword} lightweight",
            f"portable {keyword}",
        ]

    return {
        "passed": in_range,
        "price": price,
        "price_min": PRICE_MIN,
        "price_max": PRICE_MAX,
        "in_sweet_spot": in_range,
        "opportunity_keywords": long_tails,
        "detail": (
            f"${price:.0f} — " +
            ("✓ 在新手友好区间" if in_range else
             f"{'过低，利润空间危险' if price < PRICE_MIN else '过高，资金压力大'}")
        ),
        "warning": not in_range,
    }


def analyze_review_pain_points(review_analysis: dict) -> dict:
    """
    门4：评论痛点可改造性
    有明确可改造痛点 → passed（这是差异化的核心）
    """
    if not review_analysis:
        return {"passed": False, "detail": "无评论分析数据"}

    improvable = review_analysis.get("improvable", False)
    pain_points = review_analysis.get("pain_points", [])
    top_pain = pain_points[0] if pain_points else None

    return {
        "passed": improvable,
        "improvable": improvable,
        "top_pain_point": top_pain.get("category") if top_pain else None,
        "pain_point_count": len(pain_points),
        "detail": review_analysis.get("summary", ""),
        "warning": not improvable,
    }


def determine_tier(gate1: dict, gate2: dict, gate3: dict, gate4: dict) -> Tier:
    """
    分层判断（新手优先逻辑）：
    - red_ocean_avoid：门1失败（品牌垄断/价格战）OR 门2失败（全是老链接）
    - blue_ocean：四门全过
    - red_ocean_beatable：有机会但需要差异化
    """
    # 硬失败
    if not gate1["passed"]:
        return "red_ocean_avoid"
    if not gate2["passed"]:
        return "red_ocean_avoid"

    # 全过
    if gate1["passed"] and gate2["passed"] and gate3["passed"] and gate4["passed"]:
        return "blue_ocean"

    return "red_ocean_beatable"


def run_all_gates(product: dict, review_analysis: dict, config: dict) -> dict:
    """运行全部四个门，返回综合结果。"""
    competitors = product.get("competitors_top10", [])
    mc = config["market_concentration"]
    eb = config["entry_barrier"]

    gate1 = analyze_market_concentration(competitors, mc.get("red_threshold", 0.60))
    gate2 = analyze_entry_barrier(competitors, eb.get("high_review_threshold", HIGH_REVIEW_THRESHOLD))
    gate3 = analyze_price_fit(product)
    gate4 = analyze_review_pain_points(review_analysis)

    tier = determine_tier(gate1, gate2, gate3, gate4)

    return {
        "tier": tier,
        "gates": {
            "market_concentration": gate1,
            "entry_barrier": gate2,
            "price_fit": gate3,          # 原 keyword_opportunity → 价格适配度
            "review_pain_points": gate4,
        },
        "gates_passed": sum([gate1["passed"], gate2["passed"], gate3["passed"], gate4["passed"]]),
    }
