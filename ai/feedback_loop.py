"""
AI Feedback Loop — bridge between AI enrichment and prediction engine.

Flow:
  Day N:  predict.py → ai_enrich_gha.py → save_ai_scores()
  Day N+1: predict.py → load_ai_scores() → adjust prediction confidence → predict

Usage:
  from ai.feedback_loop import load_ai_adjustments, save_ai_scores
  adjustments = load_ai_adjustments(league_key)
  # pass adjustments into calculate_prediction()
"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AI_SCORES_FILE = REPO_ROOT / "predictions" / "ai_scores.json"


def load_ai_adjustments(league_key: str = "") -> dict[str, dict]:
    """Load AI enrichment scores from previous run.

    Returns dict mapping match name → {"ai_score": int, "ai_summary": str, ...}
    """
    if not AI_SCORES_FILE.exists():
        return {}
    try:
        with open(AI_SCORES_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    # Filter by league if specified
    if league_key:
        return {k: v for k, v in data.items() if v.get("league") == league_key}
    return data


def save_ai_scores(enriched_items: list[dict], league_key: str = ""):
    """Save AI enrichment scores for next prediction run.

    Args:
        enriched_items: output from analyse_batch() — each item has
            name, ai_score, ai_summary, ai_notes, source
        league_key: league identifier for filtering
    """
    existing = load_ai_adjustments()
    for item in enriched_items:
        name = item.get("name", "")
        if not name:
            continue
        # Skip mock data
        notes = item.get("ai_notes", "")
        if "mock" in notes:
            continue
        existing[name] = {
            "ai_score": item.get("ai_score", 50),
            "ai_summary": item.get("ai_summary", ""),
            "ai_notes": notes,
            "league": league_key or item.get("source", ""),
            "source": item.get("source", ""),
        }

    AI_SCORES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AI_SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
    print(f"[AI Feedback] Saved {len(existing)} AI scores to {AI_SCORES_FILE}")


def adjust_prediction(prediction: dict, ai_adjustments: dict[str, dict]) -> dict:
    """Apply AI enrichment scores to adjust prediction confidence.

    Formula:
      adjusted_confidence = base_confidence * (0.7 + 0.3 * ai_score/100)

    This means:
      ai_score=100 → boost confidence by 30%
      ai_score=50  → no change
      ai_score=0   → reduce confidence by 30%

    Returns adjusted prediction dict (mutated copy).
    """
    match_name = prediction.get("match", "")
    adj = ai_adjustments.get(match_name)
    if not adj:
        return prediction

    ai_score = adj.get("ai_score", 50)
    base_conf = prediction.get("confidence_score", 0.5)

    # Adjustment factor: 0.7 to 1.3 (center at 50)
    factor = 0.7 + 0.3 * (ai_score / 100)
    adjusted_conf = min(base_conf * factor, 1.0)

    prediction["confidence_score"] = round(adjusted_conf, 3)
    prediction["ai_adjusted"] = True
    prediction["ai_score_used"] = ai_score
    prediction["ai_adjustment_factor"] = round(factor, 3)

    # Also adjust stars based on new confidence
    from core.config import THRESHOLDS
    if adjusted_conf >= THRESHOLDS["star_5"]:
        prediction["stars"] = "5-star"
    elif adjusted_conf >= THRESHOLDS["star_4"]:
        prediction["stars"] = "4-star"
    elif adjusted_conf >= THRESHOLDS["star_3"]:
        prediction["stars"] = "3-star"
    elif adjusted_conf >= THRESHOLDS["star_2"]:
        prediction["stars"] = "2-star"
    else:
        prediction["stars"] = "1-star"

    return prediction
