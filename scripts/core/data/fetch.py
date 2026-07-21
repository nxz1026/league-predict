from __future__ import annotations

"""Data fetching layer: ESPN, football-data.org, API-Football, FIFA rankings."""

import json
import urllib.request
import gzip
import os
import time
from pathlib import Path

from core.config import (
    ESPN_URL_TEMPLATE, ESPN_MAX_RETRIES, ESPN_RETRY_DELAY_SECONDS,
    ESPN_TIMEOUT_SECONDS, LEAGUE_CONFIG, FOOTBALL_DIR,
    TIMEOUT_FOOTBALL_DATA, TIMEOUT_API_FOOTBALL,
)
from core.log import logger
from core.data.convert import convert_football_data_to_espn_format, convert_api_football_to_espn_format


def _retry_request(req: urllib.request.Request, max_retries: int = 3, timeout: int | None = None) -> dict:
    """通用重试机制：指数退避，适用于所有外部 API 调用"""
    _timeout = timeout or ESPN_TIMEOUT_SECONDS
    for attempt in range(1, max_retries + 1):
        try:
            resp = urllib.request.urlopen(req, timeout=_timeout)
            return json.loads(resp.read())
        except Exception as e:
            logger.info(f"Request attempt {attempt}/{max_retries} failed: {type(e).__name__}: {e}")
            if attempt < max_retries:
                delay = ESPN_RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                logger.info(f"Retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise

FIFA_RANKINGS_API_URL = "https://api.football-data.org/v4/teams"


def fetch_events(dates_str: str, league_key: str = "wc", data_source: str = "espn") -> list:
    """
    抽象数据源层：根据联赛配置获取比赛数据。

    Args:
        dates_str: 日期范围字符串 (YYYYMMDD-YYYYMMDD)
        league_key: 联赛键 (wc, epl, laliga, bundesliga, seriea, ligue1)
        data_source: 数据源 (espn, football-data, api-football)

    Returns:
        list: events 列表
    """
    config = LEAGUE_CONFIG.get(league_key, LEAGUE_CONFIG["epl"])

    if data_source == "espn" or config["data_source"] == "espn":
        return fetch_espn(dates_str, config.get("espn_slug", "epl"))
    elif data_source == "football-data" or config["data_source"] == "football-data":
        return fetch_football_data(dates_str, config)
    elif data_source == "api-football":
        return fetch_api_football(dates_str, config)
    else:
        # 默认 ESPN
        return fetch_espn(dates_str, config.get("espn_slug", "epl"))


def fetch_espn(dates_str: str, league_slug: str = "epl") -> list:
    """抓取 ESPN 数据（带重试机制）, 返回 parsed events"""
    url = ESPN_URL_TEMPLATE.format(dates=dates_str, league_slug=league_slug)

    for attempt in range(1, ESPN_MAX_RETRIES + 1):
        try:
            logger.info(f"Fetching ESPN (attempt {attempt}/{ESPN_MAX_RETRIES}): {url}")
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                'Accept-Encoding': 'gzip'
            })
            resp = urllib.request.urlopen(req, timeout=ESPN_TIMEOUT_SECONDS)
            data = json.loads(gzip.decompress(resp.read()))

            return data.get("events", [])

        except Exception as e:
            logger.info(f"Attempt {attempt} failed: {type(e).__name__}: {e}")
            if attempt < ESPN_MAX_RETRIES:
                logger.info(f"Retrying in {ESPN_RETRY_DELAY_SECONDS}s...")
                time.sleep(ESPN_RETRY_DELAY_SECONDS)
            else:
                logger.info(f"All {ESPN_MAX_RETRIES} attempts failed")
                raise


def fetch_football_data(dates_str: str, config: dict) -> list:
    """
    从 football-data.org 获取数据。
    注意：需要 API key（环境变量 FOOTBALL_DATA_API_KEY）
    """
    api_key = os.environ.get("FOOTBALL_DATA_API_KEY", "")
    league_id = config["league_id"]

    # 解析日期范围并转为 API 所需格式 YYYY-MM-DD
    if "-" in dates_str:
        start_raw, end_raw = dates_str.split("-", 1)
    else:
        start_raw = end_raw = dates_str

    def fmt_date(s):
        s = s.strip()
        if len(s) == 8 and s.isdigit():
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return s

    start_date = fmt_date(start_raw)
    end_date = fmt_date(end_raw)

    url = f"https://api.football-data.org/v4/competitions/{league_id}/matches?dateFrom={start_date}&dateTo={end_date}"

    headers = {
        'User-Agent': 'WorldCupPredict/3.0',
    }
    if api_key:
        headers['X-Auth-Token'] = api_key

    try:
        logger.info(f"Fetching football-data.org: {url}")
        req = urllib.request.Request(url, headers=headers)
        data = _retry_request(req, max_retries=3, timeout=TIMEOUT_FOOTBALL_DATA)

        # 转换为 ESPN 格式
        return convert_football_data_to_espn_format(data, config)
    except Exception as e:
        logger.info(f"football-data.org fetch failed: {e}")
        raise


def fetch_api_football(dates_str: str, config: dict) -> list:
    """
    从 API-Football 获取数据。
    注意：需要 API key（环境变量 API_FOOTBALL_KEY）
    """
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    league_id = config["league_id"]

    if "-" in dates_str:
        date = dates_str.split("-")[0]
    else:
        date = dates_str

    # 转换日期格式 YYYYMMDD → YYYY-MM-DD
    formatted_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"

    url = f"https://v3.football.api-sports.io/fixtures?league={league_id}&season=2024&date={formatted_date}"

    headers = {
        'User-Agent': 'WorldCupPredict/3.0',
        'x-apisports-key': api_key,
    }

    try:
        logger.info(f"Fetching API-Football: {url}")
        req = urllib.request.Request(url, headers=headers)
        data = _retry_request(req, max_retries=3, timeout=TIMEOUT_API_FOOTBALL)

        return convert_api_football_to_espn_format(data, config)
    except Exception as e:
        logger.info(f"API-Football fetch failed: {e}")
        raise


def update_fifa_rankings() -> dict:
    """从 API 获取 FIFA 排名并保存到本地文件"""
    rank_file = FOOTBALL_DIR / "references" / "fifa_rankings.json"
    api_key = os.environ.get("FOOTBALL_DATA_API_KEY", "")

    headers = {'User-Agent': 'WorldCupPredict/3.0'}
    if api_key:
        headers['X-Auth-Token'] = api_key

    try:
        logger.info(f"Fetching FIFA rankings from API: {FIFA_RANKINGS_API_URL}")
        req = urllib.request.Request(FIFA_RANKINGS_API_URL, headers=headers)
        resp = urllib.request.urlopen(req, timeout=ESPN_TIMEOUT_SECONDS)
        data = json.loads(resp.read())

        rankings = {}
        for team in data.get("teams", []):
            name = team.get("name", "")
            if name:
                rankings[name] = team.get("fifa_rank", team.get("id", 200))

        if rankings:
            rank_file.parent.mkdir(parents=True, exist_ok=True)
            with open(rank_file, "w") as f:
                json.dump(rankings, f, indent=2)
            logger.info(f"FIFA rankings updated from API: {len(rankings)} teams")
            return rankings

        logger.info("No team data in API response, falling back to local file")
    except Exception as e:
        logger.info(f"FIFA rankings API fetch failed: {e}")

    return {}


def fetch_fifa_rankings(force_refresh: bool = False) -> dict:
    """获取 FIFA 世界排名，返回 {country_name: rank} 字典"""
    rank_file = FOOTBALL_DIR / "references" / "fifa_rankings.json"

    if force_refresh:
        api_data = update_fifa_rankings()
        if api_data:
            return api_data

    if rank_file.exists():
        with open(rank_file) as f:
            data = json.load(f)
        # 支持两种格式: 列表 [{country, rank}] 或 字典 {country: rank}
        if isinstance(data, list):
            return {item.get("country", item.get("name", "")): item.get("rank", item.get("fifa_rank", 200)) for item in data}
        elif isinstance(data, dict):
            # 检查是否是 {country: rank} 格式
            first_val = next(iter(data.values())) if data else None
            if isinstance(first_val, (int, float)):
                return data
            # 可能是 {country: {rank: X, points: Y}} 格式
            result = {}
            for k, v in data.items():
                if isinstance(v, dict):
                    result[k] = v.get("rank", 200)
                else:
                    result[k] = v
            return result
    return {}
