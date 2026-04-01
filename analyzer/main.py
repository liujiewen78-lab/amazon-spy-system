"""
Analyzer Main — Reads raw scraped data, runs 4-gate analysis + scoring, outputs report JSON.
"""

import json
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scrapers"))

from filters import run_all_gates
from scoring import calculate_total_score
from review_analyzer import ReviewAnalyzer

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config" / "rules.json"
SNAPSHOTS_DIR = BASE_DIR / "data" / "snapshots"
DATA_DIR = BASE_DIR / "data"


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def find_latest_raw() -> Path | None:
    """Find the most recently created raw snapshot file."""
    raw_files = sorted(SNAPSHOTS_DIR.glob("*_raw.json"), reverse=True)
    return raw_files[0] if raw_files else None


def find_prev_report() -> dict | None:
    """Load the previous hourly report for delta comparison."""
    report_files = sorted(SNAPSHOTS_DIR.glob("*_report.json"), reverse=True)
    if len(report_files) >= 2:
        with open(report_files[1]) as f:
            return json.load(f)
    return None


def build_opportunity_summary(product: dict, gates: dict, scorecard: dict, tier: str) -> str:
    """Generate a one-sentence opportunity summary."""
    title_short = product.get("title", "")[:40]
    price = product.get("price", 0)
    total = scorecard["total"]
    tier_labels = {
        "blue_ocean": "蓝海机会",
        "red_ocean_beatable": "可切入红海",
        "red_ocean_avoid": "建议放弃"
    }
    tier_label = tier_labels.get(tier, tier)

    gate4 = gates.get("review_pain_points", {})
    pain = gate4.get("top_pain_point", "")
    pain_str = f"，主要痛点：{pain}可改造" if pain else ""

    return f"{tier_label}｜${price:.0f}售价，综合评分{total}分{pain_str}。"


def build_top3_evidence(product: dict, gates: dict) -> list[str]:
    gate1 = gates.get("market_concentration", {})
    gate2 = gates.get("entry_barrier", {})
    gate4 = gates.get("review_pain_points", {})

    evidence = []
    if gate1.get("top_brand_share"):
        evidence.append(f"市场集中度：头部品牌占比约 {gate1['top_brand_share']:.0%}")
    if gate2.get("low_review_listings") is not None:
        evidence.append(f"进入门槛：Top10中有 {gate2['low_review_listings']} 个低评论竞品")
    if gate4.get("top_pain_point"):
        evidence.append(f"评论痛点：用户频繁抱怨「{gate4['top_pain_point']}」，有改造空间")
    if not evidence:
        evidence.append(f"BSR排名: #{product.get('bsr', 'N/A')}")

    return evidence[:3]


def build_top3_risks(product: dict, gates: dict, scorecard: dict) -> list[str]:
    risks = []
    gate1 = gates.get("market_concentration", {})
    compliance = scorecard["breakdown"].get("compliance_risk", {})

    if gate1.get("warning"):
        risks.append(f"市场集中度高：{gate1.get('top_brand', 'Unknown')} 占主导")
    if not gates.get("entry_barrier", {}).get("passed"):
        risks.append("进入门槛：Top10竞品评论数普遍偏高，新品难以快速突围")
    if compliance.get("score", 10) <= 4:
        risks.append("合规风险：标题含潜在认证要求词，需核实证书要求")
    if not risks:
        risks.append("竞争一般，需靠差异化打法切入")

    return risks[:3]


def run():
    config = load_config()
    raw_path = find_latest_raw()
    if not raw_path:
        log.error("No raw data file found. Run scraper first.")
        return

    log.info(f"Analyzing: {raw_path}")
    with open(raw_path) as f:
        raw_data = json.load(f)

    products = raw_data.get("products", [])
    log.info(f"Total candidates to analyze: {len(products)}")

    review_analyzer = ReviewAnalyzer(use_ai=True)
    results = []

    for product in products:
        try:
            # Analyze reviews
            reviews = product.get("reviews_sample", [])
            review_analysis = review_analyzer.analyze_reviews(reviews)

            # Run 4-gate analysis
            gate_results = run_all_gates(product, review_analysis, config)
            tier = gate_results["tier"]
            gates = gate_results["gates"]

            # Skip hard red flags
            if tier == "red_ocean_avoid" and len(results) > 15:
                continue

            # Score
            scorecard = calculate_total_score(product, gates, gates.get("review_pain_points", {}), config)

            # Build output
            result = {
                "asin": product.get("asin"),
                "title": product.get("title"),
                "brand": product.get("brand", "Unknown"),
                "price": product.get("price"),
                "rating": product.get("rating"),
                "review_count": product.get("review_count"),
                "bsr": product.get("bsr"),
                "bsr_category": product.get("bsr_category"),
                "keyword": product.get("keyword"),
                "source_page": product.get("source_page"),
                "tier": tier,
                "total_score": scorecard["total"],
                "score_breakdown": scorecard["breakdown"],
                "gates": gates,
                "opportunity_summary": build_opportunity_summary(product, gates, scorecard, tier),
                "top3_evidence": build_top3_evidence(product, gates),
                "top3_risks": build_top3_risks(product, gates, scorecard),
                "entry_strategy": (gates.get("keyword_opportunity", {}).get("opportunity_keywords") or ["差异化改款切入"])[0],
                "review_insights": review_analysis,
            }
            results.append(result)

        except Exception as e:
            log.warning(f"Failed to analyze {product.get('asin')}: {e}")

    # Sort by score, filter to top 10 per tier
    results.sort(key=lambda x: x["total_score"], reverse=True)
    top10 = results[:10]

    # Load previous report for delta
    prev_report = find_prev_report()
    prev_scores = {}
    if prev_report:
        for item in prev_report.get("top10", []):
            prev_scores[item["asin"]] = {
                "score": item.get("total_score", 0),
                "rank": item.get("rank", 0),
                "review_count": item.get("review_count", 0),
            }

    # Add delta
    for i, item in enumerate(top10):
        item["rank"] = i + 1
        asin = item["asin"]
        if asin in prev_scores:
            prev = prev_scores[asin]
            item["delta"] = {
                "score_change": item["total_score"] - prev["score"],
                "rank_change": prev["rank"] - (i + 1),
                "review_count_change": (item.get("review_count") or 0) - prev["review_count"],
            }
        else:
            item["delta"] = {"score_change": 0, "rank_change": 0, "review_count_change": 0, "is_new": True}

    # Build report
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    hour_tag = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")

    report = {
        "report_id": timestamp,
        "generated_at": timestamp,
        "prev_report_id": prev_report.get("report_id") if prev_report else None,
        "total_analyzed": len(products),
        "total_passed_filters": len(results),
        "top10": top10,
        "tier_summary": {
            "blue_ocean": sum(1 for r in results if r["tier"] == "blue_ocean"),
            "red_ocean_beatable": sum(1 for r in results if r["tier"] == "red_ocean_beatable"),
            "red_ocean_avoid": sum(1 for r in results if r["tier"] == "red_ocean_avoid"),
        }
    }

    # Save snapshot
    report_path = SNAPSHOTS_DIR / f"{hour_tag}_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Update latest.json (front-end reads this)
    latest_path = DATA_DIR / "latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Update index.json (list of all snapshots for history)
    index_path = DATA_DIR / "index.json"
    existing_index = []
    if index_path.exists():
        with open(index_path) as f:
            existing_index = json.load(f)

    existing_index.insert(0, {
        "report_id": timestamp,
        "hour_tag": hour_tag,
        "file": f"snapshots/{hour_tag}_report.json",
        "top10_summary": [{"rank": r["rank"], "asin": r["asin"], "title": r["title"][:40],
                            "tier": r["tier"], "score": r["total_score"]} for r in top10],
    })
    existing_index = existing_index[:168]  # Keep 7 days = 168 hours

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(existing_index, f, ensure_ascii=False, indent=2)

    log.info(f"Report saved: {report_path}")
    log.info(f"Top 10: {[r['total_score'] for r in top10]}")
    log.info("Analysis complete.")


if __name__ == "__main__":
    run()
