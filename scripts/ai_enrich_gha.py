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
sys.path.insert(0, str(REPO_ROOT))

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


def enrich_via_llm(predictions: list) -> tuple[str, list]:
    """Call LLM for enrichment, return (markdown_snippet, enriched_items)."""
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
        return "", []

    # 业务偏好配置化（P4）：优先读取环境变量 LP_AI_PRIORITIES（逗号分隔），
    # 否则使用 batch_pipeline 的 DEFAULT_AI_PRIORITIES，不再硬编码于此。
    env_priorities = os.environ.get("LP_AI_PRIORITIES")
    if env_priorities:
        priorities = [p.strip() for p in env_priorities.split(",") if p.strip()]
    else:
        from ai.batch_pipeline import DEFAULT_AI_PRIORITIES
        priorities = list(DEFAULT_AI_PRIORITIES)

    enriched = analyse_batch(
        items,
        context="Football match predictions for betting. Score each match by predicted value and confidence.",
        preference_prompt="",
        config={
            "ai": {
                "model": os.environ.get("LLM_MODEL") or "deepseek-v4-flash",
                "batch_size": 5,
                "rate_limit_seconds": 3,
                "min_score": 0,
            },
            "priorities": priorities,
        },
    )

    lines = ["", "=== AI 分析 ===", ""]
    for item in enriched:
        s = item.get("ai_score", 0)
        summary = item.get("ai_summary", "")
        notes = item.get("ai_notes", "")
        if "mock" in notes:
            return "", []  # mock data, skip
        lines.append(f"• {item['name']}  **{s}/100**  — {summary}")
    lines.append("")

    # 命中率小结并入每日推送（P5 产品建议）
    acc_block = _format_accuracy_summary(predictions)
    if acc_block:
        lines.insert(0, acc_block)

    return "\n".join(lines), enriched


def _format_accuracy_summary(predictions: list) -> str:
    """从各联赛预测输出中提取 accuracy_summary，生成 Markdown 小结。"""
    blocks = []
    for league_out in predictions:
        if not isinstance(league_out, dict):
            continue
        league_name = league_out.get("league", "?")
        acc = league_out.get("accuracy_summary") or {}
        if not acc:
            continue
        rows = []
        for window, a in acc.items():
            rows.append(
                f"{window}: 方向 {a['direction_accuracy']*100:.0f}% / "
                f"比分 {a['score_accuracy']*100:.0f}% / "
                f"大小球 {a['over_under_accuracy']*100:.0f}% (n={a['reconciled']})"
            )
        if rows:
            blocks.append(f"【{league_name} 命中率】\n" + "\n".join(f"  - {r}" for r in rows))
    if not blocks:
        return ""
    return "=== 近期命中率小结 ===\n" + "\n".join(blocks) + "\n"


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
    snippet, enriched_items = enrich_via_llm(predictions)
    if not snippet:
        print("[AI Enrich] No enrichment produced (mock or empty)")
        return

    # Save AI scores for next prediction run (feedback loop)
    if enriched_items:
        from ai.feedback_loop import save_ai_scores
        save_ai_scores(enriched_items, league_key="")

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
    try:
        main()
    except Exception as e:
        import traceback
        print(f"[AI Enrich] ❌ 错误: {e}")
        print(f"[AI Enrich] 详细: {traceback.format_exc()}")
        print(f"[AI Enrich] 提示: 检查依赖安装 (pip install -r requirements.txt) 或 LLM_API_KEY 配置")
        sys.exit(1)