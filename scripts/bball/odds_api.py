"""The Odds API 的篮球数据访问与盘口解析。"""

from datetime import datetime, timedelta, timezone
import json
import urllib.error
import urllib.request



class OddsApiError(RuntimeError):
    """赔率接口请求失败。"""

    def __init__(self, url: str, reason: BaseException | str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"odds api request failed for {url}: {reason}")


def _http_get(url: str, timeout: int = 15) -> dict:
    """发起 JSON GET 请求，统一转换为领域异常。"""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            ValueError) as error:
        raise OddsApiError(url, error) from error


def _unique_games(games: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for game in games:
        pair = tuple(sorted((game.get("home_team", ""), game.get("away_team", ""))))
        if pair not in seen:
            seen.add(pair)
            unique.append(game)
    return unique


def fetch_odds_games(api_key: str, sport_key: str, days_ahead: int) -> list[dict]:
    """获取未来盘口并按队伍组合去重。"""
    now = datetime.now(timezone.utc)
    start = now.isoformat().replace("+00:00", "Z")
    end = (now + timedelta(days=days_ahead)).isoformat().replace("+00:00", "Z")
    url = (
        f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
        f"?regions=us&markets=h2h,spreads,totals&commenceTimeFrom={start}"
        f"&commenceTimeTo={end}&apiKey={api_key}"
    )
    data = _http_get(url)
    return _unique_games(data) if isinstance(data, list) else []


def fetch_completed_games(api_key: str, sport_key: str, days_back: int) -> list[dict]:
    """获取指定回溯天数内的已完赛比赛。"""
    url = (
        f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores/"
        f"?daysFrom={days_back}&apiKey={api_key}"
    )
    data = _http_get(url)
    if not isinstance(data, list):
        return []
    return [game for game in data if game.get("completed") and game.get("scores")]


def filter_24h_games(games: list[dict]) -> tuple[list[dict], list[dict]]:
    """按当前 UTC 时间拆分过去比赛与未来 24 小时比赛。"""
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=24)
    past: list[dict] = []
    future: list[dict] = []
    for game in games:
        commence = game.get("commence_time", "")
        if not commence:
            continue
        try:
            moment = datetime.fromisoformat(commence.replace("Z", "+00:00"))
        except ValueError:
            continue
        if moment < now:
            past.append(game)
        elif moment <= window_end:
            future.append(game)
    return past, future


def parse_odds(game: dict, home: str) -> tuple[float | None, float | None, float | None, float | None]:
    """解析主客胜赔、主队让分和大小分。"""
    odds_home: float | None = None
    odds_away: float | None = None
    spread_line: float | None = None
    total_line: float | None = None
    for bookmaker in game.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            outcomes = market.get("outcomes", [])
            key = market.get("key", "")
            if key == "h2h" and len(outcomes) >= 2:
                if outcomes[0].get("name") == home:
                    odds_home, odds_away = outcomes[0].get("price"), outcomes[1].get("price")
                else:
                    odds_home, odds_away = outcomes[1].get("price"), outcomes[0].get("price")
            elif key == "spreads" and len(outcomes) >= 2:
                for outcome in outcomes:
                    if outcome.get("name") == home:
                        spread_line = outcome.get("point")
            elif key == "totals" and len(outcomes) >= 2:
                total_line = outcomes[0].get("point", 0)
    return odds_home, odds_away, spread_line, total_line
