"""
AI Enrichment for GHA — reads prediction output, enriches via LLM, appends to email body.
Usage: python scripts/ai_enrich_gha.py
Env: LLM_API_KEY, LLM_API_BASE, LLM_MODEL (optional — skip if none set)
"""
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

def load_predictions(path: str = "/tmp/predict_output.txt") -> list:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        raw = f.read().strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else [data]


def enrich_via_llm(predictions: list) -> str:
    """Call LLM for enrichment, return markdown snippet."""
    from ai.batch_pipeline import analyse_batch

    # Build items from predictions
    items = []
    for league in predictions:
        league_name = league.get("league", "?")
        preds = league.get("predictions", [])
        for p in preds[:5]:  # top 5 per league
            items.append({
                "name": p.get("match", "?"),
                "source": league_name,
                "url": "",
                "date_found": "",
                "direction": p.get("direction", "?"),
                "stars": p.get("stars", "?"),
                "confidence": p.get("confidence_note", ""),
            })

    if not items:
        return ""

    enriched = analyse_batch(
        items,
        context="Football match predictions for betting. Score each match by predicted value and confidence.",
        preference_prompt="",
        config={
            "ai": {
                "model": os.environ.get("LLM_MODEL", "deepseek-v4-flash"),
                "batch_size": 5,
                "rate_limit_seconds": 3,
                "min_score": 0,
            },
            "priorities": [
                "High confidence predictions preferred",
                "Underdog picks preferred",
                "Clear direction signals preferred",
            ],
        },
    )

    lines = ["", "=== AI 分析 ===", ""]
    for item in enriched:
        s = item.get("ai_score", 0)
        summary = item.get("ai_summary", "")
        notes = item.get("ai_notes", "")
        if "mock" in notes:
            return ""  # mock data, skip
        lines.append(f"• {item['name']}  **{s}/100**  — {summary}")
    lines.append("")
    return "\n".join(lines)


def main():
    predictions = load_predictions()
    if not predictions:
        print("[AI Enrich] No prediction data found, skipping")
        return

    api_key = os.environ.get("LLM_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
    if not api_key:
        print("[AI Enrich] No LLM_API_KEY set, skipping enrichment")
        return

    print(f"[AI Enrich] Loaded {len(predictions)} leagues, enriching...")
    snippet = enrich_via_llm(predictions)
    if not snippet:
        print("[AI Enrich] No enrichment produced (mock or empty)")
        return

    email_body_path = "/tmp/email_body.txt"
    if os.path.exists(email_body_path):
        with open(email_body_path) as f:
            existing = f.read()
        with open(email_body_path, "w") as f:
            f.write(existing + snippet)
        print(f"[AI Enrich] Appended enrichment to {email_body_path}")
    else:
        with open(email_body_path, "w") as f:
            f.write(snippet)
        print(f"[AI Enrich] Created {email_body_path} with enrichment")


if __name__ == "__main__":
    main()