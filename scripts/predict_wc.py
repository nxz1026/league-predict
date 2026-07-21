#!/usr/bin/env python3
"""
League Predict v4.0 — Onside 4+1 Signal Model + Dixon-Coles + Monte Carlo
CLI entry point.

Usage: python3 predict_wc.py [--league epl] [--data-source football-data] [--monte-carlo]
       [--n-simulations 10000] [--backtest] [--cleanup] [--dates YYYYMMDD-YYYYMMDD]
       [--no-fetch] [--no-dc]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

from core.config import (
    LEAGUE_CONFIG, PREDICTIONS_DIR, FOOTBALL_DIR, DC_RHO, DEFAULT_N_SIMULATIONS
)
from core.log import logger
from core.data.fetch import fetch_events, fetch_fifa_rankings
from core.data.parse import parse_events
from core.model.poisson import fit_dc_rho
from core.model.monte_carlo import monte_carlo_champion
from core.calibration import build_calibration, compute_calibration_offset, load_historical_past_matches
from core.backtest import reconcile_predictions, backtest_with_live_results
from core.output import cleanup_old_files, save_results
from core.predictor import calculate_prediction


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="League Predict v4.0 — Onside 4+1 Signal Model + Dixon-Coles + Monte Carlo"
    )
    parser.add_argument("--league", default="epl",
                        choices=["epl", "laliga", "bundesliga", "seriea", "ligue1"],
                        help="League to predict")
    parser.add_argument("--data-source", default="football-data",
                        choices=["football-data", "espn", "api-football"],
                        help="Data source")
    parser.add_argument("--monte-carlo", action="store_true", help="Run Monte Carlo simulation")
    parser.add_argument("--n-simulations", type=int, default=DEFAULT_N_SIMULATIONS,
                        help="Monte Carlo iterations")
    parser.add_argument("--backtest", action="store_true", help="Run backtest after prediction")
    parser.add_argument("--cleanup", action="store_true", help="Clean old prediction/result files")
    parser.add_argument("--dates", help="Date range YYYYMMDD-YYYYMMDD")
    parser.add_argument("--no-fetch", action="store_true", help="Use local cached data")
    parser.add_argument("--no-dc", action="store_true", help="Disable Dixon-Coles model")
    parser.add_argument("--update-rankings", action="store_true", help="Force refresh FIFA rankings from API")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.cleanup:
        cleanup_old_files(days=7)
        return

    now_utc = datetime.now(timezone.utc)
    league_key = args.league
    data_source = args.data_source
    run_monte_carlo = args.monte_carlo
    n_simulations = args.n_simulations
    run_backtest = args.backtest
    use_dc = not args.no_dc
    skip_fetch = args.no_fetch

    if args.dates:
        dates_str = args.dates
    else:
        d1 = (now_utc - timedelta(days=1)).strftime("%Y%m%d")
        d2 = (now_utc + timedelta(days=1)).strftime("%Y%m%d")
        dates_str = f"{d1}-{d2}"

    league_config = LEAGUE_CONFIG.get(league_key, LEAGUE_CONFIG["epl"])
    host_country = league_config.get("host_country")
    tournament_type = league_config.get("tournament_type", "league")

    logger.info(f"League: {league_key} ({league_config['name']}), source: {data_source}, type: {tournament_type}")

    if skip_fetch:
        fallback = str(FOOTBALL_DIR / "references" / "espn_league_fallback.json")
        if not os.path.exists(fallback):
            fallback = str(FOOTBALL_DIR / "references" / "espn_wc_fallback.json")
        with open(fallback) as f:
            data = json.load(f)
        events = data.get("events", [])
    else:
        events = fetch_events(dates_str, league_key, data_source)

    logger.info(f"Got {len(events)} events")
    past, future, in_prog = parse_events(events, now_utc)
    logger.info(f"Past: {len(past)}, Future: {len(future)}, In progress: {len(in_prog)}")
    save_results(past)

    if args.update_rankings:
        logger.info("Force-refreshing FIFA rankings from API")
    fifa_rankings = fetch_fifa_rankings(force_refresh=args.update_rankings)
    logger.info(f"FIFA rankings loaded: {len(fifa_rankings)} teams")

    if not future and not past:
        logger.info("No matches found in window")
        output = {
            "generated_at": now_utc.isoformat(),
            "data_window": dates_str,
            "status": "no_matches",
            "league": league_key,
            "tournament_type": tournament_type,
            "message": f"No matches in window ({dates_str})",
            "calibration": {"note": "no data"},
            "past_matches": [],
            "predictions": [],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return

    if not future and not run_backtest:
        logger.info("No future matches to predict")
        calibration = build_calibration(past, future)
        output = {
            "generated_at": now_utc.isoformat(),
            "data_window": dates_str,
            "status": "no_future_matches",
            "league": league_key,
            "tournament_type": tournament_type,
            "message": f"No matches to predict in window ({dates_str})",
            "calibration": calibration,
            "past_matches": past,
            "predictions": [],
        }
        reconciliation = reconcile_predictions(past)
        if reconciliation:
            output["reconciliation"] = reconciliation
        print(json.dumps(output, indent=2, ensure_ascii=False))
        ts = now_utc.strftime("%Y-%m-%d_%H")
        pred_file = PREDICTIONS_DIR / f"prediction_{ts}.json"
        PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
        with open(pred_file, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved (no predictions): {pred_file}")
        return

    calibration = build_calibration(past, future)
    logger.info(f"Calibration: {json.dumps(calibration)}")

    historical_past = load_historical_past_matches(days=30)
    calibration_offset = compute_calibration_offset(historical_past)
    if calibration_offset:
        logger.info(f"Calibration offset: {json.dumps(calibration_offset)}")
    else:
        logger.info("Calibration offset: insufficient historical data (<5 matches)")

    # Auto-load calibration_offset from previous run
    cal_file = PREDICTIONS_DIR / "pred_calibration.json"
    if not calibration_offset and cal_file.exists():
        try:
            with open(cal_file) as f:
                calibration_offset = json.load(f)
            logger.info(f"Loaded calibration offset from {cal_file}")
        except Exception as e:
            logger.info(f"Failed to load calibration offset: {e}")

    fitted_rho = DC_RHO
    if use_dc:
        try:
            fitted_rho = fit_dc_rho(past)
        except Exception as e:
            logger.info(f"DC rho fit failed: {e}, using default")

    predictions = []
    for match in future:
        try:
            pred = calculate_prediction(
                match,
                calibration_offset=calibration_offset,
                fifa_rankings=fifa_rankings,
                host_country=host_country,
                use_dixon_coles=use_dc,
                dc_rho=fitted_rho,
            )
            pred["match"] = match["name"]
            pred["home"] = match.get("home", "")
            pred["away"] = match.get("away", "")
            predictions.append(pred)
        except Exception as e:
            logger.error(f"Prediction failed for {match.get('name', '?')}: {e}")

    logger.info(f"Predicted {len(predictions)} matches")

    monte_carlo_result = None
    if run_monte_carlo and predictions:
        team_strengths = {}
        for p in predictions:
            home = p.get("home", "")
            away = p.get("away", "")
            if home:
                team_strengths[home] = {"lambda_home": p.get("lambda_home", 1.5), "lambda_away": p.get("lambda_away", 1.2)}
            if away:
                team_strengths[away] = {"lambda_home": p.get("lambda_home", 1.5), "lambda_away": p.get("lambda_away", 1.2)}
        fixtures = [{"home": p["home"], "away": p["away"]} for p in predictions if p.get("home") and p.get("away")]
        monte_carlo_result = monte_carlo_champion(
            fixtures, team_strengths, n_simulations=n_simulations,
            rho=fitted_rho, tournament_type=tournament_type,
        )
        logger.info(f"Monte Carlo complete. Top champion: {list(monte_carlo_result['champion_probs'].items())[:3]}")

    output = {
        "generated_at": now_utc.isoformat(),
        "data_window": dates_str,
        "status": "ok",
        "league": league_key,
        "tournament_type": tournament_type,
        "data_source": data_source,
        "dixon_coles_enabled": use_dc,
        "dixon_coles_rho": fitted_rho if use_dc else None,
        "calibration": calibration,
        "calibration_offset": calibration_offset,
        "past_matches": past,
        "predictions": predictions,
    }

    reconciliation = reconcile_predictions(past)
    if reconciliation:
        output["reconciliation"] = reconciliation

    if monte_carlo_result:
        output["monte_carlo"] = monte_carlo_result

    if run_backtest:
        ts = now_utc.strftime("%Y-%m-%d_%H")
        pred_file = PREDICTIONS_DIR / f"prediction_{ts}.json"
        PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
        with open(pred_file, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved: {pred_file}")
        bt = backtest_with_live_results(str(pred_file))
        output["backtest"] = bt
        logger.info(f"Backtest: {bt.get('status')} matched={bt.get('matched_matches')} acc={bt.get('accuracy')}")

    print(json.dumps(output, indent=2, ensure_ascii=False))

    ts = now_utc.strftime("%Y-%m-%d_%H")
    pred_file = PREDICTIONS_DIR / f"prediction_{ts}.json"
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    with open(pred_file, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved: {pred_file}")

    if calibration_offset:
        cal_file = PREDICTIONS_DIR / "pred_calibration.json"
        with open(cal_file, "w") as f:
            json.dump(calibration_offset, f, indent=2)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Window calibration: {calibration.get('total_matches',0)} finished | home win {calibration.get('home_win_rate',0)*100:.0f}% draw {calibration.get('draw_rate',0)*100:.0f}% away win {calibration.get('away_win_rate',0)*100:.0f}%", file=sys.stderr)
    print(f"    Odds favorite accuracy: {calibration.get('odds_accuracy',0)*100:.0f}% ({calibration.get('favored_won',0)}/{calibration.get('favored_by_odds',0)})", file=sys.stderr)
    if calibration_offset:
        print(f"Calibration offset(n={calibration_offset['sample_size']}): home x{calibration_offset['home_correction']} draw x{calibration_offset['draw_correction']} away x{calibration_offset['away_correction']}", file=sys.stderr)
        print(f"   Actual distribution: home {calibration_offset['actual_home_rate']} | draw {calibration_offset['actual_draw_rate']} | away {calibration_offset['actual_away_rate']}", file=sys.stderr)
    else:
        print(f"Calibration offset: insufficient data (<5 matches), skipping", file=sys.stderr)
    print(f"To predict: {len(predictions)} matches", file=sys.stderr)
    for p in predictions:
        poisson_str = " / ".join(f"{t['score']}({t['prob']:.0%})" for t in p.get('poisson_top3', [])[:3])
        ci_home = p.get('lambda_home_ci95', (0,0))
        ci_away = p.get('lambda_away_ci95', (0,0))
        cal = ' [cal]' if calibration_offset else ''
        dc = ' [DC]' if p.get('dixon_coles_used') else ''
        print(f"  {p['match']} | {p['direction']} {p['stars']}{cal}{dc} | {p['predicted_score']} | l={p.get('lambda_home',0)}[{ci_home[0]}-{ci_home[1]}]/{p.get('lambda_away',0)}[{ci_away[0]}-{ci_away[1]}] | {poisson_str}", file=sys.stderr)

    if monte_carlo_result:
        print(f"\nMonte Carlo champion prediction (n={n_simulations}):", file=sys.stderr)
        for team, prob in list(monte_carlo_result["champion_probs"].items())[:5]:
            print(f"  {team}: {prob:.1%}", file=sys.stderr)

    print(f"{'='*60}", file=sys.stderr)


if __name__ == "__main__":
    main()
