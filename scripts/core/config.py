from __future__ import annotations

"""Configuration constants for the league-predict engine.

P0-3 修复: 新增 LEAGUE_DC_RHO 字典，按联赛差异化 Dixon-Coles ρ 参数。
"""

import json
import urllib.request
import gzip
import os
import sys
import time
import math
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── 加载 .env（零依赖） ─────────────────────────
_env_loaded = False
def _load_dotenv() -> None:
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    _skill_dir = Path(__file__).parent.parent
    _base = Path(os.environ.get("LP_OUTPUT_DIR", str(_skill_dir.parent)))
    _env_file = _base / ".env"
    if _env_file.exists():
        try:
            with open(_env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    if key and not os.environ.get(key):
                        os.environ[key] = val
        except OSError:
            pass

_load_dotenv()

# ── 配置 ──────────────────────────────────────
_SKILL_DIR: Path = Path(__file__).parent.parent
FOOTBALL_DIR: Path = Path(os.environ.get("LP_OUTPUT_DIR", str(_SKILL_DIR)))
PREDICTIONS_DIR: Path = FOOTBALL_DIR / "predictions"
RESULTS_DIR: Path = FOOTBALL_DIR / "results"
TRENDS_FILE: Path = _SKILL_DIR / "references" / "tournament-trends.md"
ESPN_URL_TEMPLATE: str = "https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/scoreboard?dates={dates}&limit=50"

# ─── 重试配置 ───────────────────────────────────
ESPN_MAX_RETRIES: int = 3
ESPN_RETRY_DELAY_SECONDS: int = 30
ESPN_TIMEOUT_SECONDS: int = 15

# ── Dixon-Coles 参数 ────────────────────────────
DC_RHO: float = 0.2  # 全局默认值（向后兼容）

# ════════════════════════════════════════════════
# P0-3 新增: 联赛差异化 Dixon-Coles ρ 参数
# 不同联赛的平局倾向差异显著：
#   Serie A 平局率 ~28% → ρ=0.28 (低分平局校正更强)
#   Bundesliga 平局率 ~24% → ρ=0.19
#   EPL 平局率 ~23% → ρ=0.17 (进攻型联赛，低分平局少)
# ════════════════════════════════════════════════
LEAGUE_DC_RHO: dict[str, float] = {
    "epl":       0.17,   # 英超：进攻性强，平局偏少
    "laliga":    0.22,   # 西甲：技术流，中等平局
    "bundesliga": 0.19,  # 德甲：进球多，平局略少
    "seriea":    0.28,   # 意甲：防守型，平局最多
    "ligue1":    0.21,   # 法甲：接近平均
    "mls":       0.23,   # 美职：中等水平
    "jleague":   0.20,   # J联：接近平均
    "csl":       0.22,   # 中超：略高于平均
}

# ════════════════════════════════════════════════
# P1-C 新增: 联赛差异化 λ 映射系数
# 不同联赛场均进球差异显著，统一 2.8 导致系统性偏差
# 数据来源: 各联赛近 5 赛季场均进球统计
# ════════════════════════════════════════════════
LEAGUE_LAMBDA_MULTIPLIER: dict[str, float] = {
    "epl":       2.8,    # 英超: ~2.8 球/场
    "laliga":    2.7,    # 西甲: ~2.65 球/场
    "bundesliga": 3.2,   # 德甲: ~3.2+ 球/场（进攻型）
    "seriea":    2.5,    # 意甲: ~2.5 球/场（防守型）
    "ligue1":    2.7,    # 法甲: ~2.7 球/场
    "mls":       2.9,    # 美职: ~2.9 球/场
    "jleague":   2.8,    # J联: ~2.75 球/场
    "csl":       2.9,    # 中超: ~2.9 球/场
}

# ── 蒙特卡洛参数 ────────────────────────────────
DEFAULT_N_SIMULATIONS: int = 10000

# ── 庄家水线常量（去水用）────────────────────────
BOOKMAKER_MARGIN: float = 1.07  # 典型庄家总隐含概率

# ── Monte Carlo 统一进球范围 ─────────────────────
MAX_GOALS_MC: int = 8        # MC 模拟 range(MAX_GOALS_MC) → 0~7
MAX_GOALS_PREDICT: int = 9   # 独立泊松预测 → 0~8

# ── 市场赔率权重（predictor.py 中独立使用，不混入 Onside 内部权重）─
MARKET_ODDS_WEIGHT: float = 0.20

# ── Onside 4 信号权重（内部信号，不含 market_odds）────
# P0-B 修复：market_odds 在 predictor.py 中独立使用，不应混入 Onside 内部权重
# 内部 4 信号归一化基数 = 0.25+0.20+0.15+0.20 = 0.80
ONSIDE_WEIGHTS: dict[str, float] = {
    "fifa_ranking":     0.25,
    "league_footprint": 0.20,
    "host_advantage":   0.15,
    "confederation":    0.20,
}

# ── 预测阈值字典（集中管理魔术数字）────────────────
THRESHOLDS: dict = {
    # 方向判定
    "direction_min_prob":    0.45,
    "direction_odds_ratio":  1.3,
    "draw_threshold":        0.40,
    "near_mode_base":        0.33,
    # 信心度星级边界
    "star_5":                0.90,
    "star_4":                0.72,
    "star_3":                0.55,
    "star_2":                0.35,
    # λ 参数
    "lambda_multiplier":     2.8,
    "lambda_lower_bound":    0.3,
    # 校准和默认值
    "draw_base_score":       0.15,
    "confidence_baseline":   0.25,
    "no_spread_penalty":     0.5,
    "no_odds_penalty":       0.25,
    "fifa_rank_default":     200,
    "host_advantage_score":  1.0,
    "total_min_divisor":     0.05,
    "rho_fit_min_sample":    20,
    # 盘口移动
    "spread_movement_cap":   0.15,
}

# ── 足联实力系数 ──────────────────────────────
CONFEDERATION_STRENGTH: dict[str, float] = {
    "UEFA":     1.00,
    "CONMEBOL": 0.95,
    "CONCACAF": 0.70,
    "AFC":      0.65,
    "CAF":      0.60,
    "OFC":      0.40,
}

# ── 国家→足联映射（常用） ──────────────────────
COUNTRY_CONFEDERATION: dict[str, str] = {
    "Argentina": "CONMEBOL", "Brazil": "CONMEBOL", "Uruguay": "CONMEBOL",
    "Colombia": "CONMEBOL", "Chile": "CONMEBOL", "Paraguay": "CONMEBOL",
    "Ecuador": "CONMEBOL", "Peru": "CONMEBOL", "Venezuela": "CONMEBOL",
    "Bolivia": "CONMEBOL",
    "England": "UEFA", "France": "UEFA", "Germany": "UEFA", "Spain": "UEFA",
    "Italy": "UEFA", "Netherlands": "UEFA", "Portugal": "UEFA", "Belgium": "UEFA",
    "Croatia": "UEFA", "Switzerland": "UEFA", "Denmark": "UEFA", "Poland": "UEFA",
    "Austria": "UEFA", "Scotland": "UEFA", "Serbia": "UEFA", "Wales": "UEFA",
    "Turkey": "UEFA", "Norway": "UEFA", "Sweden": "UEFA", "Ukraine": "UEFA",
    "Czech Republic": "UEFA", "Czechia": "UEFA", "Hungary": "UEFA", "Greece": "UEFA",
    "Romania": "UEFA", "Slovakia": "UEFA", "Slovenia": "UEFA", "Finland": "UEFA",
    "Ireland": "UEFA", "Iceland": "UEFA", "Northern Ireland": "UEFA",
    "USA": "CONCACAF", "United States": "CONCACAF", "Mexico": "CONCACAF",
    "Canada": "CONCACAF", "Costa Rica": "CONCACAF", "Panama": "CONCACAF",
    "Jamaica": "CONCACAF", "Honduras": "CONCACAF",
    "Japan": "AFC", "South Korea": "AFC", "Korea Republic": "AFC",
    "Australia": "AFC", "Iran": "AFC", "Saudi Arabia": "AFC",
    "Qatar": "AFC", "China PR": "AFC", "China": "AFC",
    "Iraq": "AFC", "United Arab Emirates": "AFC", "Uzbekistan": "AFC",
    "Nigeria": "CAF", "Egypt": "CAF", "Senegal": "CAF", "Morocco": "CAF",
    "Cameroon": "CAF", "Ghana": "CAF", "Ivory Coast": "CAF", "Cote d'Ivoire": "CAF",
    "Algeria": "CAF", "Tunisia": "CAF", "Mali": "CAF", "South Africa": "CAF",
    "DR Congo": "CAF", "Congo DR": "CAF",
    "New Zealand": "OFC",
    # P3-B 补充: 常见非洲/亚洲/欧洲国家队
    "Morocco": "CAF", "Tunisia": "CAF", "Algeria": "CAF",
    "Ghana": "CAF", "Ivory Coast": "CAF", "Cote d'Ivoire": "CAF",
    "Mali": "CAF", "Burkina Faso": "CAF", "Egypt": "CAF",
    "Cameroon": "CAF", "Guinea": "CAF", "Benin": "CAF",
    "Syria": "AFC", "Thailand": "AFC", "Vietnam": "AFC",
    "Oman": "AFC", "Bahrain": "AFC", "Jordan": "AFC",
    "Palestine": "AFC", "UAE": "AFC", "United Arab Emirates": "AFC",
    "North Macedonia": "UEFA", "Georgia": "UEFA", "Armenia": "UEFA",
    "Israel": "UEFA", "Belarus": "UEFA", "Kosovo": "UEFA",
}

# ── 联赛配置 ────────────────────────────────────
LEAGUE_CONFIG: dict[str, dict[str, object]] = {
    "epl": {
        "name": "English Premier League",
        "data_source": "api-football",
        "league_id": "PL",
        "api_football_id": 39,
        "espn_slug": "eng.1",
        "host_country": "England",
        "groups": False,
        "knockout": False,
    },
    "laliga": {
        "name": "La Liga",
        "tournament_type": "league",
        "data_source": "api-football",
        "league_id": "PD",
        "api_football_id": 140,
        "espn_slug": "spa.1",
        "host_country": "Spain",
        "groups": False,
        "knockout": False,
    },
    "bundesliga": {
        "name": "Bundesliga",
        "tournament_type": "league",
        "data_source": "api-football",
        "league_id": "BL1",
        "api_football_id": 78,
        "espn_slug": "ger.1",
        "host_country": "Germany",
        "groups": False,
        "knockout": False,
    },
    "seriea": {
        "name": "Serie A",
        "tournament_type": "league",
        "data_source": "api-football",
        "league_id": "SA",
        "api_football_id": 135,
        "espn_slug": "ita.1",
        "host_country": "Italy",
        "groups": False,
        "knockout": False,
    },
    "ligue1": {
        "name": "Ligue 1",
        "tournament_type": "league",
        "data_source": "api-football",
        "league_id": "FL1",
        "api_football_id": 61,
        "espn_slug": "fra.1",
        "host_country": "France",
        "groups": False,
        "knockout": False,
    },
    # ── 扩展联赛（P4-2）─────────────────────────────
    "mls": {
        "name": "Major League Soccer",
        "tournament_type": "league",
        "data_source": "espn",
        "league_id": "MLS",
        "api_football_id": 253,
        "espn_slug": "usa.1",
        "host_country": "USA",
        "groups": False,
        "knockout": False,
    },
    "jleague": {
        "name": "J-League",
        "tournament_type": "league",
        "data_source": "football-data",
        "league_id": "JL1",
        "api_football_id": 98,
        "espn_slug": "japan.1",
        "host_country": "Japan",
        "groups": False,
        "knockout": False,
    },
    "csl": {
        "name": "Chinese Super League",
        "tournament_type": "league",
        "data_source": "api-football",
        "league_id": "CSL",
        "api_football_id": 169,
        "espn_slug": "chn.1",
        "host_country": "China",
        "groups": False,
        "knockout": False,
    },
}

# ── 中文队名映射 ────────────────────────────────
COUNTRY_CN: dict[str, str] = {
    # 欧洲
    "England": "英格兰", "France": "法国", "Germany": "德国", "Spain": "西班牙",
    "Italy": "意大利", "Netherlands": "荷兰", "Portugal": "葡萄牙", "Belgium": "比利时",
    "Croatia": "克罗地亚", "Switzerland": "瑞士", "Denmark": "丹麦", "Poland": "波兰",
    "Sweden": "瑞典", "Norway": "挪威", "Serbia": "塞尔维亚", "Ukraine": "乌克兰",
    "Turkey": "土耳其", "Austria": "奥地利", "Scotland": "苏格兰", "Hungary": "匈牙利",
    "Romania": "罗马尼亚", "Slovakia": "斯洛伐克", "Slovenia": "斯洛文尼亚", "Czech Republic": "捷克",
    "Czechia": "捷克", "Greece": "希腊", "Finland": "芬兰", "Wales": "威尔士",
    "Ireland": "爱尔兰", "Iceland": "冰岛", "Russia": "俄罗斯",
    # 南美
    "Brazil": "巴西", "Argentina": "阿根廷", "Uruguay": "乌拉圭", "Colombia": "哥伦比亚",
    "Chile": "智利", "Peru": "秘鲁", "Ecuador": "厄瓜多尔", "Paraguay": "巴拉圭",
    "Venezuela": "委内瑞拉", "Bolivia": "玻利维亚",
    # 中北美
    "USA": "美国", "United States": "美国", "Mexico": "墨西哥", "Canada": "加拿大",
    "Costa Rica": "哥斯达黎加", "Panama": "巴拿马", "Jamaica": "牙买加", "Honduras": "洪都拉斯",
    # 亚非
    "Japan": "日本", "South Korea": "韩国", "Korea Republic": "韩国",
    "Australia": "澳大利亚", "Iran": "伊朗", "Saudi Arabia": "沙特阿拉伯",
    "Qatar": "卡塔尔", "China PR": "中国", "China": "中国",
    "Iraq": "伊拉克", "UAE": "阿联酋", "United Arab Emirates": "阿联酋",
    "Uzbekistan": "乌兹别克斯坦", "Nigeria": "尼日利亚", "Egypt": "埃及",
    "Senegal": "塞内加尔", "Morocco": "摩洛哥", "Cameroon": "喀麦隆",
    "Ghana": "加纳", "Tunisia": "突尼斯", "Algeria": "阿尔及利亚",
    "Ivory Coast": "科特迪瓦", "Cote d'Ivoire": "科特迪瓦", "Mali": "马里",
    "South Africa": "南非", "DR Congo": "民主刚果", "Congo DR": "民主刚果",
    "New Zealand": "新西兰",
    # 俱乐部（常见）
    "Arsenal": "阿森纳", "Manchester City": "曼城", "Liverpool": "利物浦",
    "Chelsea": "切尔西", "Manchester United": "曼联", "Tottenham": "热刺",
    "Real Madrid": "皇家马德里", "Barcelona": "巴塞罗那", "Atlético Madrid": "马德里竞技",
    "Bayern Munich": "拜仁慕尼黑", "Borussia Dortmund": "多特蒙德",
    "Paris Saint-Germain": "巴黎圣日耳曼", "Juventus": "尤文图斯",
    "AC Milan": "AC米兰", "Inter Milan": "国际米兰", "Napoli": "那不勒斯",
}

# ── API 超时配置 ────────────────────────────────
TIMEOUT_FOOTBALL_DATA: int = 15
TIMEOUT_API_FOOTBALL: int = 20

# ── 去水相关常量 ────────────────────────────────
MIN_IMPLIED_PROB: float = 0.01  # 最小隐含概率下限
