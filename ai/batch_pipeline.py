"""
Batch AI analysis pipeline: split items, enrich via Gemini, return scored items.
Adapted from ECC community data-scraper-agent skill.
"""
import json
from ai.llm_client import generate

# 业务评分偏好默认集（P4：改为可配置，避免硬编码在调用方源码中）。
# 可通过环境变量 LP_AI_PRIORITIES（逗号分隔）覆盖，或在调用时通过
# config["priorities"] 传入。
DEFAULT_AI_PRIORITIES: list[str] = [
    "High confidence predictions preferred",
    "Underdog picks preferred",
    "Clear direction signals preferred",
]

# 评分规则（rubric）默认文案，可通过 config["scoring_rubric"] 覆盖。
DEFAULT_SCORING_RUBRIC: str = (
    "Be concise. Score 90+=excellent match, 70-89=good, 50-69=ok, <50=weak."
)


def analyse_batch(
    items: list[dict],
    context: str = "",
    preference_prompt: str = "",
    config: dict = None,
) -> list[dict]:
    """Analyse items in batches. Returns items enriched with AI fields.

    Each item gets: ai_score (0-100), ai_summary, ai_notes.
    Items below min_score are filtered out.
    """
    config = config or {}
    ai_cfg = config.get("ai", {})
    model = ai_cfg.get("model", "gemini-2.5-flash")
    rate_limit = ai_cfg.get("rate_limit_seconds", 7.0)
    min_score = ai_cfg.get("min_score", 0)
    batch_size = ai_cfg.get("batch_size", 5)

    batches = [items[i : i + batch_size] for i in range(0, len(items), batch_size)]
    print(f"  [AI] {len(items)} items → {len(batches)} API calls")

    enriched = []
    for i, batch in enumerate(batches):
        print(f"  [AI] Batch {i + 1}/{len(batches)}...")
        prompt = _build_prompt(batch, context, preference_prompt, config)
        result = generate(prompt, model=model, rate_limit=rate_limit)
        analyses = result.get("analyses", [])

        analyses_by_name = _pair_batch(analyses, batch)
        for item in batch:
            ai = analyses_by_name.get(item.get("name"))
            if not isinstance(ai, dict):
                enriched.append(item)
                continue
            score = max(0, min(100, int(ai.get("score", 0))))
            if min_score and score < min_score:
                continue
            enriched.append({
                **item,
                "ai_score": score,
                "ai_summary": ai.get("summary", ""),
                "ai_notes": ai.get("notes", ""),
            })

    return enriched


def _pair_batch(analyses: list[dict], batch: list[dict]) -> dict:
    """Pair analyses to batch items by name; fall back to position.

    Prefer `a["match"] == item["name"]`. 兼容回退：所有 analysis 都无
    match 键且数量与 batch 相等时，退回按位置配对（旧行为）。
    """
    valid_analyses = [a for a in analyses if isinstance(a, dict)]
    if not valid_analyses:
        return {}
    if all("match" not in a for a in valid_analyses):
        return {
            item.get("name"): a
            for item, a in zip(batch, analyses)
            if isinstance(a, dict)
        }
    return {
        a["match"]: a
        for a in valid_analyses
        if a.get("match") is not None
    }



def _build_prompt(batch, context, preference_prompt, config):
    """Build the Gemini prompt for a batch of items."""
    priorities = config.get("priorities") or DEFAULT_AI_PRIORITIES
    items_text = "\n\n".join(
        f"Item {i+1}: {json.dumps({k: v for k, v in item.items() if not k.startswith('_')})}"
        for i, item in enumerate(batch)
    )

    scoring_rubric = config.get("scoring_rubric") or DEFAULT_SCORING_RUBRIC
    return f"""Analyse these {len(batch)} items and return a JSON object.
# Items
{items_text}
# User Context
{context[:800] if context else "Not provided"}
# User Priorities
{chr(10).join(f"- {p}" for p in priorities)}
{preference_prompt}
# Instructions
Return: {{"analyses": [{{"match": "<对应条目的 name 原样照抄>", "score": <0-100>, "summary": "<2 sentences>", "notes": ""}} for each item in order]}}
analyses 必须覆盖全部条目，match 原样照抄，不得改写。
所有 summary 与 notes 必须使用简体中文撰写（JSON 键名保持英文）。
{scoring_rubric}"""