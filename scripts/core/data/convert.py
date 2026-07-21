from __future__ import annotations

"""Data format converters: football-data.org and API-Football to ESPN format."""

from core.log import logger


def convert_football_data_to_espn_format(data: dict, config: dict) -> list[dict]:
    """将 football-data.org 格式转换为 ESPN 兼容格式"""
    events = []
    matches = data.get("matches", [])

    for match in matches:
        home_team = match.get("homeTeam", {}).get("name", "Unknown")
        away_team = match.get("awayTeam", {}).get("name", "Unknown")

        status_map = {
            "SCHEDULED": "STATUS_SCHEDULED",
            "LIVE": "STATUS_IN_PROGRESS",
            "IN_PLAY": "STATUS_IN_PROGRESS",
            "PAUSED": "STATUS_IN_PROGRESS",
            "FINISHED": "STATUS_FULL_TIME",
            "POSTPONED": "STATUS_SCHEDULED",
            "SUSPENDED": "STATUS_SCHEDULED",
            "CANCELLED": "STATUS_SCHEDULED",
        }

        status = status_map.get(match.get("status", ""), "STATUS_SCHEDULED")
        completed = match.get("status") == "FINISHED"

        score_data = match.get("score", {}).get("fullTime", {})
        home_score = str(score_data.get("home", 0) or 0)
        away_score = str(score_data.get("away", 0) or 0)

        event = {
            "name": f"{away_team} at {home_team}",
            "date": match.get("utcDate", ""),
            "competitions": [{
                "status": {
                    "type": {
                        "name": status,
                        "completed": completed,
                    }
                },
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"displayName": home_team, "abbreviation": match.get("homeTeam", {}).get("t3", "UNK")},
                        "score": home_score,
                        "form": "",
                        "records": [],
                    },
                    {
                        "homeAway": "away",
                        "team": {"displayName": away_team, "abbreviation": match.get("awayTeam", {}).get("t3", "UNK")},
                        "score": away_score,
                        "form": "",
                        "records": [],
                    },
                ],
                "odds": [],
            }]
        }
        events.append(event)

    return events


def convert_api_football_to_espn_format(data: dict, config: dict) -> list[dict]:
    """将 API-Football 格式转换为 ESPN 兼容格式"""
    events = []
    fixtures = data.get("response", [])

    for fixture in fixtures:
        home_team = fixture.get("teams", {}).get("home", {}).get("name", "Unknown")
        away_team = fixture.get("teams", {}).get("away", {}).get("name", "Unknown")

        status_short = fixture.get("fixture", {}).get("status", {}).get("short", "NS")
        status_map = {
            "NS": "STATUS_SCHEDULED",
            "1H": "STATUS_IN_PROGRESS",
            "HT": "STATUS_IN_PROGRESS",
            "2H": "STATUS_IN_PROGRESS",
            "ET": "STATUS_IN_PROGRESS",
            "P": "STATUS_IN_PROGRESS",
            "FT": "STATUS_FULL_TIME",
            "AET": "STATUS_FINAL_ET",
            "PEN": "STATUS_FINAL_PEN",
            "SUSP": "STATUS_SCHEDULED",
            "INT": "STATUS_SCHEDULED",
            "PST": "STATUS_SCHEDULED",
            "CANC": "STATUS_SCHEDULED",
            "ABD": "STATUS_SCHEDULED",
            "AWD": "STATUS_FULL_TIME",
            "WO": "STATUS_FULL_TIME",
        }

        status = status_map.get(status_short, "STATUS_SCHEDULED")
        completed = status in ("STATUS_FULL_TIME", "STATUS_FINAL_ET", "STATUS_FINAL_PEN")

        goals = fixture.get("goals", {})
        home_score = str(goals.get("home", 0) or 0)
        away_score = str(goals.get("away", 0) or 0)

        event = {
            "name": f"{away_team} at {home_team}",
            "date": fixture.get("fixture", {}).get("date", ""),
            "competitions": [{
                "status": {
                    "type": {
                        "name": status,
                        "completed": completed,
                    }
                },
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"displayName": home_team, "abbreviation": home_team[:3].upper()},
                        "score": home_score,
                        "form": "",
                        "records": [],
                    },
                    {
                        "homeAway": "away",
                        "team": {"displayName": away_team, "abbreviation": away_team[:3].upper()},
                        "score": away_score,
                        "form": "",
                        "records": [],
                    },
                ],
                "odds": [],
            }]
        }
        events.append(event)

    return events
