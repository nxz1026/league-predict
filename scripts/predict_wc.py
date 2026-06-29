#!/usr/bin/env python3
"""
World Cup Predict v2 — 结构化预测引擎
P0: form, records, details(ML), spread line 全字段利用
P2: 隐含概率计算 + 加权评分 + 自动校准

用法: python3 /tmp/predict_wc.py [--dates YYYYMMDD-YYYYMMDD] [--no-fetch]
      --no-fetch: 使用本地 /tmp/espn_wc.json (调试用)
输出: JSON 写入 /root/football/predictions/prediction_YYYY-MM-DD_HH.json
      校准写入 /tmp/pred_calibration.json
"""
import json, urllib.request, gzip, os, sys, math
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── 配置 ──────────────────────────────────────
FOOTBALL_DIR = Path("/root/football")
PREDICTIONS_DIR = FOOTBALL_DIR / "predictions"
RESULTS_DIR = FOOTBALL_DIR / "results"
TRENDS_FILE = Path("/root/.hermes/skills/productivity/world-cup-predict/references/tournament-trends.md")
ESPN_URL_TEMPLATE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={dates}&limit=50"

# ── 权重 (P2 算法核心) ──────────────────────────
WEIGHTS = {
    "home_ml_implied": 0.30,
    "draw_ml_implied": 0.25,
    "home_form":       0.12,
    "away_form":       0.08,
    "home_record":     0.08,
    "away_record":     0.07,
    "spread_move":     0.10,
}

# ── Poisson 参数 ─────────────────────────────────
# λ = raw_strength × LAMBDA_MULTIPLIER
# 强队 λ ~3.0-3.5, 弱队 λ ~0.3-0.8
LAMBDA_MULTIPLIER = 4.5

def log(msg):
    print(f"[predict] {msg}", file=sys.stderr)

# ── ML 解析 ────────────────────────────────────
def parse_american_odds(odds_str):
    """解析美式赔率 → 隐含概率 (含 vig)
    -125 → 125/225 = 0.5556
    +265 → 100/365 = 0.2740
    +105 → 100/205 = 0.4878"""
    try:
        raw = str(odds_str).strip().lstrip('+')
        odds = int(raw)
        abs_odds = abs(odds)
        if odds < 0:  # favorite: -125
            return abs_odds / (abs_odds + 100)
        else:  # underdog: +265
            return 100 / (abs_odds + 100)
    except (ValueError, TypeError):
        return None

def parse_details(details_str):
    """解析 details 字段如 'CZE -125' → (team, odds_str, implied)"""
    if not details_str:
        return None, None, None
    parts = details_str.strip().split()
    if len(parts) >= 2:
        team = parts[0]
        odds_str = parts[-1]
        impl = parse_american_odds(odds_str)
        return team, odds_str, impl
    return None, None, None

# ── 球队状态评分 ──────────────────────────────
# 2026 世界杯 48 队中英文映射 (ESPN 英文名 → 中文)
COUNTRY_CN = {
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
}

def to_cn(name):
    """英文国家名 → 中文 (未知回退原文)"""
    if not name:
        return name
    return COUNTRY_CN.get(name, COUNTRY_CN.get(name.replace("'", ""), name))

def form_to_score(form_str):
    """'DWDDW' → 0-1, W=3, D=1, L=0"""
    if not form_str:
        return 0.5
    score = sum(3 if c == 'W' else 1 if c == 'D' else 0 for c in form_str)
    return score / (len(form_str) * 3)

def record_to_score(records):
    """records[0].summary '1-0-0' (W-D-L) → 0-1"""
    if not records:
        return 0.5
    summary = records[0].get("summary", "")
    parts = summary.split("-")
    if len(parts) >= 3:
        w, d, l = int(parts[0]), int(parts[1]), int(parts[2])
        total = w + d + l
        return (w * 3 + d) / (total * 3) if total > 0 else 0.5
    return 0.5

# ── 亚盘 movement 分析 ───────────────────────
def spread_movement_factor(spread_open, spread_close):
    """
    spread 开盘→收盘水位变化
    正数 = 主队更被市场看好, 负数 = 客队被看好
    范围 -1 到 1, 0 = 无变化
    """
    def odds_to_int(d):
        if not d:
            return None
        try:
            return int(str(d.get("odds", "0")).lstrip('+'))
        except (ValueError, AttributeError, TypeError):
            return None
    
    o = odds_to_int(spread_open)
    c = odds_to_int(spread_close)
    if o is None or c is None:
        return 0.0
    
    # 水位越负 = 越被看好
    # -110 → -135: 增加信心, factor > 0
    # -110 → -105: 减少信心, factor < 0
    # 计算变化百分比
    if o < 0 and c < 0:
        # 都负: -110→-135 means more confidence
        change = (abs(c) - abs(o)) / abs(o)
        return min(change, 1.0)
    elif o < 0 and c > 0:
        # 从被看好变成不被看好: 大逆转
        return -0.8
    elif o > 0 and c < 0:
        # 从不被看好变成被看好: 大逆转
        return 0.8
    else:
        # 都正: +110→+135 means less confidence (odds went up)
        change = (abs(o) - abs(c)) / abs(o)
        return -min(abs(change), 1.0)

# ── vig 去除 ──────────────────────────────────
def remove_vig(home_p, draw_p, away_p=None, default_margin=1.07):
    """
    三向去水: 已知 home + draw 隐含概率, 推算 + 归一
    away_p 为 None 时从默认 margin 推算
    """
    if home_p is None or draw_p is None:
        return None, None, None
    if away_p is None:
        away_p = default_margin - home_p - draw_p
        if away_p < 0:
            away_p = 0.05
    
    total = home_p + draw_p + away_p
    if total <= 0:
        return home_p / default_margin, draw_p / default_margin, away_p / default_margin
    
    return home_p / total, draw_p / total, away_p / total

# ── Poisson 工具 ────────────────────────────────
def poisson_prob(k, lam):
    """P(X=k) for Poisson(lam), k up to 20 (safe factorial)"""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    log_p = k * math.log(lam) - lam - math.lgamma(k + 1)
    return math.exp(log_p)

def compute_score_distribution(λ_home, λ_away, max_goals=12):
    """
    遍历主客 0..max_goals, 计算 Poisson 联合概率
    返回: top_3_scores + 完整分布 dict + 比分区间概率
    """
    scores = []
    total_prob = 0.0
    # 遍历所有组合 (不截断低概率，保证 score_bands 归一化)
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            ph = poisson_prob(h, λ_home)
            pa = poisson_prob(a, λ_away)
            prob = ph * pa
            scores.append({"score": f"{h}-{a}", "prob": round(prob, 4)})
            total_prob += prob
    # 按概率降序
    scores.sort(key=lambda x: -x["prob"])
    top3 = scores[:3]

    # 比分区间概率 (总进球数)
    band_0_1 = sum(s["prob"] for s in scores
                   if int(s["score"].split("-")[0]) + int(s["score"].split("-")[1]) <= 1)
    band_2 = sum(s["prob"] for s in scores
                 if int(s["score"].split("-")[0]) + int(s["score"].split("-")[1]) == 2)
    band_3 = sum(s["prob"] for s in scores
                 if int(s["score"].split("-")[0]) + int(s["score"].split("-")[1]) == 3)
    band_4plus = sum(s["prob"] for s in scores
                     if int(s["score"].split("-")[0]) + int(s["score"].split("-")[1]) >= 4)

    return top3, {
        "0-1球": round(band_0_1, 4),
        "2球": round(band_2, 4),
        "3球": round(band_3, 4),
        "4球+": round(band_4plus, 4),
    }

# ── 主预测函数 ─────────────────────────────────
def fetch_espn(dates_str):
    """抓取 ESPN 数据, 返回 parsed events"""
    url = ESPN_URL_TEMPLATE.format(dates=dates_str)
    log(f"Fetching ESPN: {url}")
    
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
        'Accept-Encoding': 'gzip'
    })
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(gzip.decompress(resp.read()))
    
    # 存一份到 /tmp 供调试
    with open("/tmp/espn_wc.json", "w") as f:
        json.dump(data, f, indent=2)
    
    return data.get("events", [])

def fetch_fifa_rankings():
    """FIFA 世界排名 (从 web_search 获取, 已缓存则跳过)"""
    rank_file = FOOTBALL_DIR / "references" / "fifa_rankings.json"
    if rank_file.exists():
        with open(rank_file) as f:
            return json.load(f)
    return {}  # 无缓存, 留给 LLM 后续 web_search

def parse_events(events, now_utc=None):
    """解析 ESPN events → 结束比赛列表 + 待预测比赛列表"""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    
    past = []
    future = []
    in_progress = []
    
    for ev in events:
        # ESPN name 格式: "Away at Home" → 中文 "客队 vs 主队"
        en_name = ev.get("name", "")
        if " at " in en_name:
            away_en, home_en = en_name.split(" at ", 1)
            name = f"{to_cn(away_en)} vs {to_cn(home_en)}"
        else:
            name = to_cn(en_name)
        comps = ev.get("competitions", [{}])[0]
        status = comps.get("status", {}).get("type", {}).get("name", "")
        completed = comps.get("status", {}).get("type", {}).get("completed", False)
        
        # 开球时间
        date_str = ev.get("date", "")
        try:
            kickoff = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except:
            kickoff = now_utc
        time_to = (kickoff - now_utc).total_seconds() / 3600
        
        # 球队
        competitors = comps.get("competitors", [])
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        
        home_name = to_cn(home["team"]["displayName"]) if home else "?"
        away_name = to_cn(away["team"]["displayName"]) if away else "?"
        home_abbr = home["team"]["abbreviation"] if home else ""
        away_abbr = away["team"]["abbreviation"] if away else ""
        home_score = home.get("score", "0") if home else "0"
        away_score = away.get("score", "0") if away else "0"
        
        # P0 字段: form + records
        home_form = home.get("form", "") if home else ""
        away_form = away.get("form", "") if home else ""
        home_records = home.get("records", []) if home else []
        away_records = away.get("records", []) if away else []
        
        # 赔率
        odds_raw = comps.get("odds") or []
        odds = next((o for o in odds_raw if o), {}) if odds_raw else {}
        
        details = odds.get("details", "")
        draw_ml = (odds.get("drawOdds") or {}).get("moneyLine", None)
        
        # P0: spread 全字段 (含 line + odds)
        ps = odds.get("pointSpread") or {}
        spread_h = ps.get("home") or {}
        spread_a = ps.get("away") or {}
        spread_h_open = spread_h.get("open") or {}
        spread_h_close = spread_h.get("close") or {}
        spread_a_open = spread_a.get("open") or {}
        spread_a_close = spread_a.get("close") or {}
        
        # Total
        tot = odds.get("total") or {}
        tot_o = tot.get("over") or {}
        tot_u = tot.get("under") or {}
        tot_o_close = tot_o.get("close") or {}
        tot_u_close = tot_u.get("close") or {}
        
        # Spread line (区分 -0.5 碾压 vs +0.5 受让)
        spread_h_line = spread_h_close.get("line", "")
        spread_h_odds = spread_h_close.get("odds", "")
        
        # ML 解析
        ml_team, ml_odds_str, home_ml_implied = parse_details(details)
        draw_implied = parse_american_odds(draw_ml)
        
        # 去水
        home_true, draw_true, away_true = remove_vig(home_ml_implied, draw_implied)
        
        # 亚盘 movement
        spread_move = spread_movement_factor(spread_h_open, spread_h_close)
        
        # 评分
        h_fs = form_to_score(home_form)
        a_fs = form_to_score(away_form)
        h_rs = record_to_score(home_records)
        a_rs = record_to_score(away_records)
        
        rec = {
            "name": name,
            "status": status,
            "completed": completed,
            "kickoff_utc": date_str,
            "time_to_kickoff_h": round(time_to, 1),
            "home": home_name,
            "away": away_name,
            "home_abbr": home_abbr,
            "away_abbr": away_abbr,
            "score": f"{home_score}-{away_score}" if status == "STATUS_FULL_TIME" else "",
            # P0: 新字段
            "home_form": home_form,
            "away_form": away_form,
            "home_form_score": round(h_fs, 3),
            "away_form_score": round(a_fs, 3),
            "home_record": home_records[0].get("summary","") if home_records else "",
            "away_record": away_records[0].get("summary","") if away_records else "",
            "home_record_score": round(h_rs, 3),
            "away_record_score": round(a_rs, 3),
            # P0: 赔率新字段
            "ml_home_close": ml_odds_str,
            "draw_ml": draw_ml,
            "home_ml_implied": round(home_ml_implied, 4) if home_ml_implied else None,
            "draw_implied": round(draw_implied, 4) if draw_implied else None,
            "home_true_prob": round(home_true, 4) if home_true else None,
            "draw_true_prob": round(draw_true, 4) if draw_true else None,
            "away_true_prob": round(away_true, 4) if away_true else None,
            "spread_home_line": spread_h_line,
            "spread_home_close_odds": spread_h_odds,
            "spread_movement_score": round(spread_move, 3),
            "total_over_close": tot_o_close.get("odds",""),
            "total_under_close": tot_u_close.get("odds",""),
        }
        
        # 分类
        if status == "STATUS_FULL_TIME":
            past.append(rec)
        elif status == "STATUS_SCHEDULED":
            future.append(rec)
        else:
            in_progress.append(rec)
    
    return past, future, in_progress

def calculate_prediction(match, weights=None):
    """P2 加权评分 → 方向 + 信心 + 比分预测"""
    if weights is None:
        weights = WEIGHTS
    
    # 确保概率值有效
    hp = match.get("home_true_prob") or 0.5
    dp = match.get("draw_true_prob") or 0.25
    ap = match.get("away_true_prob") or 0.25
    hfs = match.get("home_form_score", 0.5)
    afs = match.get("away_form_score", 0.5)
    hrs = match.get("home_record_score", 0.5)
    ars = match.get("away_record_score", 0.5)
    sm = match.get("spread_movement_score", 0)
    
    # 计算三向强度 (clamp 到非负)
    # ML 隐含概率直接作为基础 (去水后)
    home_strength = max(0,
        hp * 0.40
        + hfs * 0.20
        + hrs * 0.15
        + sm * 0.25  # 正 spread movement = 市场看好主队
    )
    away_strength = max(0,
        ap * 0.40
        + afs * 0.20
        + ars * 0.15
        + (-sm) * 0.25  # 负 spread movement = 客队被看好
    )
    draw_strength = max(0, dp * 0.50)  # 平局主要靠 ML 决定
    
    # 归一化 (三向和至少 0.05 防除零)
    total = max(home_strength + draw_strength + away_strength, 0.05)
    home_prob = home_strength / total
    draw_prob_calc = draw_strength / total
    away_prob = away_strength / total
    
    # 方向判定
    if home_prob > 0.45 and home_prob > away_prob * 1.3:
        direction = f"{match['home']} 胜"
        confidence_raw = (home_prob - 0.25) * 2  # 0.25→0, 0.75→1
    elif away_prob > 0.45 and away_prob > home_prob * 1.3:
        direction = f"{match['away']} 胜"
        confidence_raw = (away_prob - 0.25) * 2
    elif draw_prob_calc > 0.40:
        direction = "平局"
        confidence_raw = (draw_prob_calc - 0.25) * 2
    else:
        # 接近的比赛 — 取概率最高方向
        if home_prob >= away_prob and home_prob >= draw_prob_calc:
            direction = f"{match['home']} 胜 (接近)"
            confidence_raw = (home_prob - 0.33) * 3
        elif away_prob >= home_prob and away_prob >= draw_prob_calc:
            direction = f"{match['away']} 胜 (接近)"
            confidence_raw = (away_prob - 0.33) * 3
        else:
            direction = "平局 (接近)"
            confidence_raw = (draw_prob_calc - 0.33) * 3
    
    # 信心星级
    confidence_raw = min(max(confidence_raw, 0.1), 1.0)
    if confidence_raw > 0.8:
        stars = "⭐⭐⭐⭐⭐"
    elif confidence_raw > 0.65:
        stars = "⭐⭐⭐⭐"
    elif confidence_raw > 0.5:
        stars = "⭐⭐⭐"
    elif confidence_raw > 0.35:
        stars = "⭐⭐"
    else:
        stars = "⭐"
    
    # ── Poisson 比分预测 (取代启发式 if-elif) ──────
    # λ = raw_strength × LAMBDA_MULTIPLIER
    # raw_strength 来自三向归一化前的原始强度
    raw_home = max(0, hp * 0.40 + hfs * 0.20 + hrs * 0.15 + sm * 0.25)
    raw_away = max(0, ap * 0.40 + afs * 0.20 + ars * 0.15 + (-sm) * 0.25)
    raw_draw = max(0, dp * 0.50)

    # 把三向强度映射到进球数 λ
    # 主队场均进球倾向: home_strength + 0.5 * draw_strength
    # 客队场均进球倾向: away_strength + 0.5 * draw_strength
    λ_home = (raw_home + 0.5 * raw_draw) * LAMBDA_MULTIPLIER
    λ_away = (raw_away + 0.5 * raw_draw) * LAMBDA_MULTIPLIER

    # 封底: 即使弱队也至少有一点进攻期望
    λ_home = max(λ_home, 0.3)
    λ_away = max(λ_away, 0.3)

    top3_scores, score_bands = compute_score_distribution(λ_home, λ_away)

    # 格式化 top-3
    score_display = " / ".join(
        f"{s['score']} ({s['prob']*100:.0f}%)" for s in top3_scores
    )

    # O/U 判断 (用 Poisson 期望总进球)
    expected_total = round(λ_home + λ_away, 1)
    ou_total = match.get("total_over_close", "2.5")
    if expected_total > 2.5:
        ou = f"Over {ou_total}"
        ou_note = f"高总分 ({expected_total})"
    elif expected_total > 1.8:
        ou = f"Over {ou_total}"
        ou_note = f"中高总分 ({expected_total})"
    else:
        ou = f"Under {ou_total}"
        ou_note = f"低总分 ({expected_total})"

    btts = "Yes" if λ_home > 0.8 and λ_away > 0.5 and raw_draw < 0.4 else "No"
    
    return {
        "direction": direction,
        "stars": stars,
        "confidence_score": round(confidence_raw, 3),
        "predicted_score": score_display,  # "2-0 (15%) / 3-0 (13%) / 1-0 (12%)"
        "expected_goals_home": round(λ_home, 2),
        "expected_goals_away": round(λ_away, 2),
        "expected_goals_total": expected_total,
        "top3_scores": top3_scores,  # [{score, prob}, ...]
        "score_bands": score_bands,
        "over_under": f"{ou} @ {match.get('total_over_close','')}" if match.get('total_over_close','') else f"{ou}",
        "btts": btts,
        "reasoning_factors": {
            "home_ml_true_prob": round(hp, 3),
            "draw_true_prob": round(dp, 3),
            "away_ml_true_prob": round(ap, 3),
            "home_form_score": round(hfs, 3),
            "away_form_score": round(afs, 3),
            "home_record_score": round(hrs, 3),
            "away_record_score": round(ars, 3),
            "spread_movement": round(sm, 3),
            "home_prob_weighted": round(home_prob, 3),
            "draw_prob_weighted": round(draw_prob_calc, 3),
            "away_prob_weighted": round(away_prob, 3),
        }
    }

def build_calibration(past_matches, future_matches):
    """从结束比赛计算校准参数"""
    if not past_matches:
        return {"note": "no past matches to calibrate from"}
    
    home_wins = sum(1 for m in past_matches if m["score"] and m["score"].split("-")[0].isdigit() and m["score"].split("-")[1].isdigit() and int(m["score"].split("-")[0]) > int(m["score"].split("-")[1]))
    draws = sum(1 for m in past_matches if m["score"] and m["score"].split("-")[0] == m["score"].split("-")[1])
    away_wins = sum(1 for m in past_matches if m["score"] and m["score"].split("-")[0].isdigit() and m["score"].split("-")[1].isdigit() and int(m["score"].split("-")[0]) < int(m["score"].split("-")[1]))
    total = home_wins + draws + away_wins
    
    # 实际 vs 理论 (如果 ML 正确, 热门应该赢多少)
    favorite_wins = 0
    total_odds_based = 0
    for m in past_matches:
        hp = m.get("home_true_prob")
        if hp and hp > 0.5:
            total_odds_based += 1
            if m["score"]:
                try:
                    hs, aws = m["score"].split("-")
                    if int(hs) > int(aws):
                        favorite_wins += 1
                except: pass
    
    return {
        "total_matches": total,
        "home_wins": home_wins,
        "draws": draws,
        "away_wins": away_wins,
        "home_win_rate": round(home_wins/total, 3) if total else 0,
        "draw_rate": round(draws/total, 3) if total else 0,
        "away_win_rate": round(away_wins/total, 3) if total else 0,
        "favored_by_odds": total_odds_based,
        "favored_won": favorite_wins,
        "odds_accuracy": round(favorite_wins/total_odds_based, 3) if total_odds_based else 0,
    }

def main():
    # 时间
    now_utc = datetime.now(timezone.utc)
    
    # 日期窗口 (3 天)
    d1 = (now_utc - timedelta(days=1)).strftime("%Y%m%d")
    d2 = (now_utc + timedelta(days=1)).strftime("%Y%m%d")
    dates_str = f"{d1}-{d2}"
    
    # 获取数据
    skip_fetch = "--no-fetch" in sys.argv
    if skip_fetch:
        with open("/tmp/espn_wc.json") as f:
            data = json.load(f)
        events = data.get("events", [])
    else:
        events = fetch_espn(dates_str)
    
    log(f"Got {len(events)} events from ESPN")
    
    # 解析
    past, future, in_prog = parse_events(events, now_utc)
    log(f"Past: {len(past)}, Future: {len(future)}, In progress: {len(in_prog)}")
    
    # 校准
    calibration = build_calibration(past, future)
    log(f"Calibration: {json.dumps(calibration)}")
    
    # 预测
    predictions = []
    for m in sorted(future, key=lambda x: x.get("time_to_kickoff_h", 0)):
        if -6 <= m.get("time_to_kickoff_h", 24) <= 30:  # 只预测未来 30h
            pred = calculate_prediction(m)
            # display 字段：LLM 直接原样输出，不再自行格式化
            # match_display = "主队 vs 客队"，score_display = "主队进球-客队进球"
            # direction 中的队名与 match_display 一致
            home_name = m["home"]
            away_name = m["away"]
            predictions.append({
                "match": m["name"],
                "home": home_name,
                "away": away_name,
                "kickoff_utc": m["kickoff_utc"],
                "time_to_kickoff_h": m["time_to_kickoff_h"],
                "match_display": f"{home_name} vs {away_name}",
                "score_display": pred["predicted_score"],
                "direction_display": pred["direction"],
                **pred
            })
    
    # 输出
    output = {
        "generated_at": now_utc.isoformat(),
        "data_window": dates_str,
        "calibration": calibration,
        "past_matches": past,
        "predictions": predictions,
    }
    
    print(json.dumps(output, indent=2, ensure_ascii=False))
    
    # 写文件
    ts = now_utc.strftime("%Y-%m-%d_%H")
    pred_file = PREDICTIONS_DIR / f"prediction_{ts}.json"
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    with open(pred_file, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    log(f"Saved: {pred_file}")
    
    # 写校准到 /tmp
    with open("/tmp/pred_calibration.json", "w") as f:
        json.dump(calibration, f, indent=2)
    
    # 输出摘要到 stderr + stdout
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"📊 校准: {calibration.get('total_matches',0)}场已结束 | 主胜 {calibration.get('home_win_rate',0)*100:.0f}% 平 {calibration.get('draw_rate',0)*100:.0f}% 客胜 {calibration.get('away_win_rate',0)*100:.0f}%", file=sys.stderr)
    print(f"   投注热门正确率: {calibration.get('odds_accuracy',0)*100:.0f}% ({calibration.get('favored_won',0)}/{calibration.get('favored_by_odds',0)})", file=sys.stderr)
    print(f"🔥 待预测: {len(predictions)} 场", file=sys.stderr)
    for p in predictions:
        eg = p.get('expected_goals_total', '?')
        print(f"  {p.get('match_display', p['match'])} | {p['direction']} {p['stars']} | λ={eg} | {p['predicted_score']}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

if __name__ == "__main__":
    main()
