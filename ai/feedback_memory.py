"""
Learn from user decisions to improve future AI scoring.
Adapted from ECC community data-scraper-agent skill.
"""
import json
from pathlib import Path


def load_feedback(path: str = "data/feedback.json") -> dict:
    """Load feedback history from JSON file."""
    fb_path = Path(path)
    if fb_path.exists():
        try:
            return json.loads(fb_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"positive": [], "negative": []}


def save_feedback(fb: dict, path: str = "data/feedback.json"):
    """Save feedback history to JSON file."""
    fb_path = Path(path)
    fb_path.parent.mkdir(parents=True, exist_ok=True)
    fb_path.write_text(json.dumps(fb, indent=2))


def build_preference_prompt(feedback: dict, max_examples: int = 15) -> str:
    """Convert feedback history into a prompt bias section.

    'positive' items boost future scoring for similar patterns.
    'negative' items suppress future scoring.
    """
    lines = []
    if feedback.get("positive"):
        lines.append("# Items the user LIKED (positive signal):")
        for e in feedback["positive"][-max_examples:]:
            lines.append(f"- {e}")
    if feedback.get("negative"):
        lines.append("\n# Items the user SKIPPED/REJECTED (negative signal):")
        for e in feedback["negative"][-max_examples:]:
            lines.append(f"- {e}")
    if lines:
        lines.append("\nUse these patterns to bias scoring on new items.")
    return "\n".join(lines)