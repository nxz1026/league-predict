from __future__ import annotations

"""Configuration constants for the league-predict engine."""

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

# ── 配置 ──────────────────────────────────────
_SKILL_DIR: Path = Path(__file__).parent.parent
FOOTBALL_DIR: Path = Path(os.environ.get("WC_OUTPUT_DIR", str(_SKILL_DIR)))
PREDICTIONS_DIR: Path = FOOTBALL_DIR / "predictions"
RESULTS_DIR: Path = FOOTBALL_DIR / "results"
TRENDS_FILE: Path = _SKILL_DIR / "references" / "tournament-trends.md"
ESPN_URL_TEMPLATE: str = "https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/scoreboard?dates={dates}&limit=50"

# ─── 重试配置 ───────────────────────────────────
ESPN_MAX_RETRIES: int = 3
ESPN_RETRY_DELAY_SECONDS: int = 30
ESPN_TIMEOUT_SECONDS: int = 15

# ── Dixon-Coles 参数 ────────────────────────────
DC_RHO: float = 0.2

# ── 蒙特卡洛参数 ────────────────────────────────
DEFAULT_N_SIMULATIONS: int = 10000

# ── Onside 4 信号权重 ──────────────────────────
ONSIDE_WEIGHTS: dict[str, float] = {
    "market_odds":      0.20,
    "fifa_ranking":     0.25,
    "league_footprint": 0.20,
    "host_advantage":   0.15,
    "confederation":    0.20,
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
}

# ── 联赛配置 ────────────────────────────────────
LEAGUE_CONFIG: dict[str, dict[str, object]] = {
    "epl": {
        "name": "English Premier League",
        "data_source": "football-data",
        "league_id": "PL",
        "espn_slug": "eng.1",
        "host_country": "England",
        "groups": False,
        "knockout": False,
    },
    "laliga": {
        "name": "La Liga",
        "tournament_type": "league",
        "data_source": "football-data",
        "league_id": "PD",
        "host_country": "Spain",
        "groups": False,
        "knockout": False,
    },
    "bundesliga": {
        "name": "Bundesliga",
        "tournament_type": "league",
        "data_source": "football-data",
        "league_id": "BL1",
        "host_country": "Germany",
        "groups": False,
        "knockout": False,
    },
    "seriea": {
        "name": "Serie A",
        "tournament_type": "league",
        "data_source": "football-data",
        "league_id": "SA",
        "host_country": "Italy",
        "groups": False,
        "knockout": False,
    },
    "ligue1": {
        "name": "Ligue 1",
        "tournament_type": "league",
        "data_source": "football-data",
        "league_id": "FL1",
        "host_country": "France",
        "groups": False,
        "knockout": False,
    },
}

# ── 东道主加成 ──────────────────────────────────
HOST_ADVANTAGE_BOOST: float = 0.05

# ── 球队中文名映射 ────────────────────────────
COUNTRY_CN: dict[str, str] = {
    "Afghanistan": "阿富汗", "Albania": "阿尔巴尼亚", "Algeria": "阿尔及利亚",
    "Angola": "安哥拉", "Argentina": "阿根廷", "Armenia": "亚美尼亚",
    "Australia": "澳大利亚", "Austria": "奥地利", "Azerbaijan": "阿塞拜疆",
    "Bahrain": "巴林", "Bangladesh": "孟加拉国", "Belarus": "白俄罗斯",
    "Belgium": "比利时", "Benin": "贝宁", "Bolivia": "玻利维亚",
    "Bosnia and Herzegovina": "波黑", "Bosnia-Herzegovina": "波黑",
    "Botswana": "博茨瓦纳", "Brazil": "巴西", "Bulgaria": "保加利亚",
    "Burkina Faso": "布基纳法索", "Burundi": "布隆迪", "Cameroon": "喀麦隆",
    "Canada": "加拿大", "Cape Verde": "佛得角", "Chad": "乍得",
    "Chile": "智利", "China PR": "中国", "China": "中国",
    "Colombia": "哥伦比亚", "Comoros": "科摩罗", "Congo": "刚果",
    "Congo DR": "刚果(金)", "DR Congo": "刚果(金)", "Costa Rica": "哥斯达黎加",
    "Croatia": "克罗地亚", "Cuba": "古巴", "Curacao": "库拉索",
    "Curaçao": "库拉索", "Cyprus": "塞浦路斯", "Czechia": "捷克",
    "Czech Republic": "捷克", "Denmark": "丹麦", "Djibouti": "吉布提",
    "Dominican Republic": "多米尼加", "Ecuador": "厄瓜多尔", "Egypt": "埃及",
    "El Salvador": "萨尔瓦多", "England": "英格兰", "Estonia": "爱沙尼亚",
    "Eswatini": "斯威士兰", "Ethiopia": "埃塞俄比亚", "Faroe Islands": "法罗群岛",
    "Fiji": "斐济", "Finland": "芬兰", "France": "法国",
    "Gabon": "加蓬", "Gambia": "冈比亚", "Georgia": "格鲁吉亚",
    "Germany": "德国", "Ghana": "加纳", "Gibraltar": "直布罗陀",
    "Greece": "希腊", "Grenada": "格林纳达", "Guadeloupe": "瓜德罗普",
    "Guatemala": "危地马拉", "Guinea": "几内亚", "Guinea-Bissau": "几内亚比绍",
    "Guyana": "圭亚那", "Haiti": "海地", "Honduras": "洪都拉斯",
    "Hong Kong": "中国香港", "Hungary": "匈牙利", "Iceland": "冰岛",
    "India": "印度", "Indonesia": "印度尼西亚", "Iran": "伊朗",
    "Iraq": "伊拉克", "Ireland": "爱尔兰", "Israel": "以色列",
    "Italy": "意大利", "Ivory Coast": "科特迪瓦", "Cote d'Ivoire": "科特迪瓦",
    "Jamaica": "牙买加", "Japan": "日本", "Jordan": "约旦",
    "Kazakhstan": "哈萨克斯坦", "Kenya": "肯尼亚", "Korea Republic": "韩国",
    "South Korea": "韩国", "Korea DPR": "朝鲜", "North Korea": "朝鲜",
    "Kosovo": "科索沃", "Kuwait": "科威特", "Kyrgyzstan": "吉尔吉斯斯坦",
    "Laos": "老挝", "Latvia": "拉脱维亚", "Lebanon": "黎巴嫩",
    "Lesotho": "莱索托", "Liberia": "利比里亚", "Libya": "利比亚",
    "Liechtenstein": "列支敦士登", "Lithuania": "立陶宛", "Luxembourg": "卢森堡",
    "Macao": "中国澳门", "Macedonia": "北马其顿", "North Macedonia": "北马其顿",
    "Madagascar": "马达加斯加", "Malawi": "马拉维", "Malaysia": "马来西亚",
    "Maldives": "马尔代夫", "Mali": "马里", "Malta": "马耳他",
    "Martinique": "马提尼克", "Mauritania": "毛里塔尼亚", "Mauritius": "毛里求斯",
    "Mexico": "墨西哥", "Moldova": "摩尔多瓦", "Monaco": "摩纳哥",
    "Mongolia": "蒙古", "Montenegro": "黑山", "Morocco": "摩洛哥",
    "Mozambique": "莫桑比克", "Myanmar": "缅甸", "Namibia": "纳米比亚",
    "Nepal": "尼泊尔", "Netherlands": "荷兰", "New Caledonia": "新喀里多尼亚",
    "New Zealand": "新西兰", "Nicaragua": "尼加拉瓜", "Niger": "尼日尔",
    "Nigeria": "尼日利亚", "Norway": "挪威", "Oman": "阿曼",
    "Pakistan": "巴基斯坦", "Palestine": "巴勒斯坦", "Panama": "巴拿马",
    "Paraguay": "巴拉圭", "Peru": "秘鲁", "Philippines": "菲律宾",
    "Poland": "波兰", "Portugal": "葡萄牙", "Qatar": "卡塔尔",
    "Romania": "罗马尼亚", "Russia": "俄罗斯", "Rwanda": "卢旺达",
    "Saudi Arabia": "沙特", "Scotland": "苏格兰", "Senegal": "塞内加尔",
    "Serbia": "塞尔维亚", "Sierra Leone": "塞拉利昂", "Singapore": "新加坡",
    "Slovakia": "斯洛伐克", "Slovenia": "斯洛文尼亚", "Solomon Islands": "所罗门群岛",
    "Somalia": "索马里", "South Africa": "南非", "South Sudan": "南苏丹",
    "Spain": "西班牙", "Sri Lanka": "斯里兰卡", "Sudan": "苏丹",
    "Suriname": "苏里南", "Sweden": "瑞典", "Switzerland": "瑞士",
    "Syria": "叙利亚", "Tahiti": "塔希提", "Taiwan": "中国台北",
    "Tajikistan": "塔吉克斯坦", "Tanzania": "坦桑尼亚", "Thailand": "泰国",
    "Togo": "多哥", "Trinidad and Tobago": "特立尼达和多巴哥",
    "Tunisia": "突尼斯", "Turkey": "土耳其", "Türkiye": "土耳其",
    "Turkmenistan": "土库曼斯坦", "Uganda": "乌干达", "Ukraine": "乌克兰",
    "United Arab Emirates": "阿联酋", "Uruguay": "乌拉圭",
    "United States": "美国", "USA": "美国", "Uzbekistan": "乌兹别克斯坦",
    "Venezuela": "委内瑞拉", "Vietnam": "越南", "Wales": "威尔士",
    "Yemen": "也门", "Zambia": "赞比亚", "Zimbabwe": "津巴布韦",
    "Manchester City": "曼城", "Manchester United": "曼联", "Liverpool": "利物浦",
    "Chelsea": "切尔西", "Arsenal": "阿森纳", "Tottenham": "热刺",
    "Newcastle": "纽卡斯尔", "Aston Villa": "阿斯顿维拉", "Brighton": "布莱顿",
    "West Ham": "西汉姆", "Crystal Palace": "水晶宫", "Wolverhampton": "狼队",
    "Fulham": "富勒姆", "Bournemouth": "伯恩茅斯", "Nottingham Forest": "诺丁汉森林",
    "Brentford": "布伦特福德", "Everton": "埃弗顿", "Leicester": "莱斯特城",
    "Ipswich": "伊普斯维奇", "Southampton": "南安普顿",
    "Real Madrid": "皇家马德里", "Barcelona": "巴塞罗那", "Atletico Madrid": "马竞",
    "Sevilla": "塞维利亚", "Real Sociedad": "皇家社会", "Villarreal": "比利亚雷亚尔",
    "Athletic Club": "毕尔巴鄂", "Real Betis": "贝蒂斯",
    "Bayern Munich": "拜仁慕尼黑", "Borussia Dortmund": "多特蒙德",
    "RB Leipzig": "RB莱比锡", "Bayer Leverkusen": "勒沃库森",
    "Wolfsburg": "沃尔夫斯堡", "Frankfurt": "法兰克福",
    "Juventus": "尤文图斯", "AC Milan": "AC米兰", "Inter Milan": "国际米兰",
    "Napoli": "那不勒斯", "Roma": "罗马", "Lazio": "拉齐奥",
    "Atalanta": "亚特兰大", "Fiorentina": "佛罗伦萨",
    "Paris Saint-Germain": "巴黎圣日耳曼", "PSG": "巴黎圣日耳曼",
    "Marseille": "马赛", "Lyon": "里昂", "Monaco": "摩纳哥",
    "Lille": "里尔", "Nice": "尼斯",
}

# ── 期望进球强度映射参数 ─────────────────────
LAMBDA_MULTIPLIER: float = 2.8

# ── 各数据源独立超时（秒） ──────────────────────\
TIMEOUT_FOOTBALL_DATA: int = 30       # football-data.org 响应较慢
TIMEOUT_API_FOOTBALL: int = 20        # API-Football 中等响应

# ── 去水/赔率常量 ──────────────────────────────\
BOOKMAKER_MARGIN: float = 1.07        # 默认庄家抽水 ~6.5%
MIN_IMPLIED_PROB: float = 0.05        # 最小隐含概率下限

# ── 方向判定阈值（P2-2 集中管理） ───────────────\
THRESHOLDS: dict[str, float] = {
    # 方向判定
    "direction_min_prob": 0.45,           # 主/客胜最低概率
    "direction_odds_ratio": 1.3,          # 主客胜优势比
    "draw_threshold": 0.40,              # 平局判定阈值
    "near_mode_base": 0.33,             # 接近态基准线
    # 信心度星级边界
    "star_5": 0.90,
    "star_4": 0.72,
    "star_3": 0.55,
    "star_2": 0.35,
    # 无盘口惩罚
    "no_odds_penalty": 0.25,
    # 平局基础分
    "draw_base_score": 0.15,
    # 盘口移动裁剪
    "spread_movement_cap": 0.15,
    # λ 参数
    "lambda_lower_bound": 0.3,
    "lambda_multiplier": 2.8,            # 与 LAMBDA_MULTIPLIER 同步
}

# ── 校准基线分布（P0-4 修复） ───────────────────\
CALIBRATION_BASELINE: dict[str, float] = {
    "home": 0.45,
    "draw": 0.25,
    "away": 0.30,
}
