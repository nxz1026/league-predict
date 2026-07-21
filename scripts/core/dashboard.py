from __future__ import annotations

"""Web Dashboard HTML Generator (P5-1).

生成静态 HTML Dashboard 文件，可视化预测结果：
- 实时预测表格（方向、信心、比分、λ 参数）
- Monte Carlo 冠军概率柱状图
- 校准偏移状态面板
- 历史准确率趋势
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import FOOTBALL_DIR, PREDICTIONS_DIR
from core.log import logger


def generate_dashboard(prediction_data: dict[str, Any], output_path: Path | None = None) -> str:
    """从预测 JSON 数据生成 HTML Dashboard。"""
    predictions = prediction_data.get("predictions", [])
    mc = prediction_data.get("monte_carlo", {})
    cal = prediction_data.get("calibration", {})
    cal_offset = prediction_data.get("calibration_offset")
    bt = prediction_data.get("backtest")

    now_str = prediction_data.get("generated_at", datetime.now(timezone.utc).isoformat())
    league = prediction_data.get("league", "unknown")

    rows_html = ""
    for p in predictions:
        direction = p.get("direction", "")
        stars = p.get("stars", "⭐")
        score = p.get("predicted_score", "-")
        lam_h = p.get("lambda_home", 0)
        lam_a = p.get("lambda_away", 0)
        conf = p.get("confidence_score", 0)
        ou = p.get("over_under", "-")
        btts = p.get("btts", "-")
        match_name = p.get("match", "")

        if "胜" in direction and ("主" in direction or direction.startswith(p.get("home", ""))):
            row_class = "row-home"
        elif "胜" in direction:
            row_class = "row-away"
        else:
            row_class = "row-draw"

        rows_html += f"""
        <tr class="{row_class}">
          <td>{match_name}</td>
          <td><strong>{direction}</strong> {stars}</td>
          <td>{score}</td>
          <td>{conf:.0%}</td>
          <td>{lam_h:.2f}</td>
          <td>{lam_a:.2f}</td>
          <td>{ou}</td>
          <td>{btts}</td>
        </tr>"""

    champion_probs = mc.get("champion_probs", {})
    mc_html = ""
    if champion_probs:
        top_teams = list(champion_probs.items())[:8]
        max_prob = max(p for _, p in top_teams) if top_teams else 1
        for team, prob in top_teams:
            bar_width = prob / max_prob * 100 if max_prob > 0 else 0
            mc_html += f"""
        <div class="mc-bar">
          <span class="team-name">{team}</span>
          <div class="bar-bg"><div class="bar-fill" style="width:{bar_width:.0f}%"></div></div>
          <span class="prob-val">{prob:.1%}</span>
        </div>"""
    else:
        mc_html = "<p>No Monte Carlo data</p>"

    total_matches = cal.get("total_matches", 0)
    hw_rate = cal.get("home_win_rate", 0)
    d_rate = cal.get("draw_rate", 0)
    aw_rate = cal.get("away_win_rate", 0)
    odds_acc = cal.get("odds_accuracy", 0)

    cal_info = ""
    if cal_offset:
        cal_info = f"""
        <div class="cal-offset">
          <h4>校准偏移 (n={cal_offset.get('sample_size', '?')})</h4>
          <p>Home x{cal_offset.get('home_correction', '-')} | Draw x{cal_offset.get('draw_correction', '-')} | Away x{cal_offset.get('away_correction', '-')}</p>
          <p>Onside Home x{cal_offset.get('onside_home_correction', '-')} | Onside Away x{cal_offset.get('onside_away_correction', '-')}</p>
        </div>"""

    bt_html = ""
    if bt:
        bt_html = f"""
        <div class="backtest-panel">
          <h4>回测结果</h4>
          <p>Status: {bt.get('status', 'N/A')}</p>
          <p>Matched: {bt.get('matched_matches', 0)} | Accuracy: {bt.get('accuracy', 0):.1%}</p>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>League Predict - {league.upper()} Dashboard</title>
<style>
  :root {{ --primary:#1a73e8; --bg:#0d1117; --card:#161b22; --text:#c9d1d9; --border:#30363d; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,'Segoe UI',Roboto,sans-serif; background:var(--bg); color:var(--text); padding:20px; }}
  .header {{ text-align:center; margin-bottom:24px; }}
  .header h1 {{ font-size:28px; color:#fff; }} .header .meta {{ color:#8b949e; font-size:13px; margin-top:6px; }}
  .grid {{ display:grid; grid-template-columns:1fr 360px; gap:20px; }}
  @media(max-width:900px){{ .grid{{grid-template-columns:1fr}} }}
  .card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:20px; }}
  .card h3 {{ color:#fff; margin-bottom:14px; font-size:16px; border-bottom:1px solid var(--border); padding-bottom:8px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ text-align:left; padding:8px 6px; border-bottom:2px solid var(--border); color:#8b949e; font-weight:500; }}
  td {{ padding:7px 6px; border-bottom:1px solid var(--border); }}
  tr:hover {{ background:#1c2128; }}
  .row-home td:first-child{{ color:#58a6ff; }} .row-away td:first-child{{ color:#f78166; }} .row-draw td:first-child{{ color:#a5d6ff; }}
  .mc-bar {{ display:flex; align-items:center; gap:8px; margin-bottom:8px; font-size:13px; }}
  .team-name {{ width:130px; overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }}
  .bar-bg {{ flex:1; height:18px; background:#21262d; border-radius:4px; overflow:hidden; }}
  .bar-fill {{ height:100%; background:linear-gradient(90deg,#1a73e8,#58a6ff); border-radius:4px; transition:width .3s; }}
  .prob-val {{ width:45px; text-align:right; font-weight:600; color:#58a6ff; }}
  .stats-row {{ display:flex; justify-content:space-between; margin-bottom:8px; font-size:13px; }}
  .stats-row span {{ color:#8b949e; }} .stats-row strong {{ color:#fff; }}
  .cal-offset {{ background:#1c2128; border-radius:8px; padding:12px; margin-top:12px; font-size:13px; }}
  .backtest-panel {{ background:#1c2128; border-radius:8px; padding:12px; margin-top:12px; font-size:13px; }}
  .tag {{ display:inline-block; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600; }}
  .tag-blue {{ background:#1f6feb22; color:#58a6ff; }}
</style>
</head>
<body>
<div class="header">
  <h1>⚽ League Predict Dashboard</h1>
  <div class="meta">{league.upper()} | Generated: {now_str} | <span class="tag tag-blue">v4.0</span></div>
</div>

<div class="grid">
  <div class="card">
    <h3>Predictions ({len(predictions)})</h3>
    <table>
      <thead><tr><th>Match</th><th>Direction</th><th>Score</th><th>Conf</th><th>LH</th><th>LA</th><th>O/U</th><th>BTTS</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
  <div>
    <div class="card" style="margin-bottom:20px;">
      <h3>Monte Carlo Champion</h3>
      {mc_html}
    </div>
    <div class="card">
      <h3>Calibration Status</h3>
      <div class="stats-row"><span>Total Matches:</span><strong>{total_matches}</strong></div>
      <div class="stats-row"><span>Home Win:</span><strong style="color:#58a6ff">{hw_rate:.1%}</strong></div>
      <div class="stats-row"><span>Draw:</span><strong style="color:#a5d6ff">{d_rate:.1%}</strong></div>
      <div class="stats-row"><span>Away Win:</span><strong style="color:#f78166">{aw_rate:.1%}</strong></div>
      <div class="stats-row"><span>Odds Accuracy:</span><strong style="color:#3fb950">{odds_acc:.1%}</strong></div>
      {cal_info}
      {bt_html}
    </div>
  </div>
</div>

<div style="text-align:center;margin-top:24px;color:#484f58;font-size:12px;">
  League Predict v4.0 - Onside 4+1 + Dixon-Coles + Monte Carlo
</div>
</body>
</html>"""

    if output_path is None:
        output_path = PREDICTIONS_DIR / "dashboard.html"

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        logger.info(f"Dashboard saved: {output_path}")
    except OSError as e:
        logger.warning(f"Failed to save dashboard: {e}")

    return html
