#!/usr/bin/env python3
"""
NBA Model Calibration - Grid search weight optimizer.
Runs the analyzer with different parameter combinations on cached backtest data
and finds the set that maximizes spread ATS%.

Usage: python3 nba/nba_calibrate.py 2026-01-15 2026-02-06
"""

import sys
import json
import itertools
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nba.nba_analyzer import NBAAnalyzer
from nba.nba_backtest import fetch_actual_results
from nba.nba_team_mappings import normalize_team_name

PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data"

# Parameter grid to search
PARAM_GRID = {
    "EFFICIENCY_DEFLATOR": [0.75, 0.78, 0.80, 0.82, 0.85],
    "HOME_COURT_ADVANTAGE": [1.5, 2.0, 2.5],
    "SEASON_WEIGHT": [0.35, 0.40, 0.45, 0.50],
    "LOCATION_BLEND_WEIGHT": [0.30, 0.35, 0.40],
    "ff_weight": [0.10, 0.15, 0.20],
}


def evaluate_params(params: dict, date_range: list) -> dict:
    """Run analyzer with given params on all cached data and score results."""
    spread_wins = 0
    spread_losses = 0
    spread_pushes = 0
    ml_wins = 0
    ml_losses = 0
    total_games = 0

    for date_str in date_range:
        compact = date_str.replace("-", "")
        data_file = DATA_DIR / f"nba_data_{compact}.json"

        if not data_file.exists():
            continue

        with open(data_file) as f:
            data = json.load(f)

        # Create analyzer and override params
        analyzer = NBAAnalyzer(data)
        analyzer.EFFICIENCY_DEFLATOR = params["EFFICIENCY_DEFLATOR"]

        # Override blending weights via monkey-patching the module-level values
        import nba.nba_config as cfg
        old_hca = cfg.HOME_COURT_ADVANTAGE
        old_sw = cfg.SEASON_WEIGHT
        old_r10w = cfg.ROLLING_10_WEIGHT
        old_r20w = cfg.ROLLING_20_WEIGHT
        old_lbw = cfg.LOCATION_BLEND_WEIGHT

        cfg.HOME_COURT_ADVANTAGE = params["HOME_COURT_ADVANTAGE"]
        cfg.SEASON_WEIGHT = params["SEASON_WEIGHT"]
        remaining = 1.0 - params["SEASON_WEIGHT"]
        cfg.ROLLING_10_WEIGHT = remaining * 0.583  # ~0.35/0.60 ratio
        cfg.ROLLING_20_WEIGHT = remaining * 0.417  # ~0.25/0.60 ratio
        cfg.LOCATION_BLEND_WEIGHT = params["LOCATION_BLEND_WEIGHT"]

        ff_weight = params["ff_weight"]

        # Run analysis
        analyses = analyzer.analyze_all_games()

        # Fetch actual results
        try:
            actual_results = fetch_actual_results(date_str)
        except Exception:
            # Restore and skip
            cfg.HOME_COURT_ADVANTAGE = old_hca
            cfg.SEASON_WEIGHT = old_sw
            cfg.ROLLING_10_WEIGHT = old_r10w
            cfg.ROLLING_20_WEIGHT = old_r20w
            cfg.LOCATION_BLEND_WEIGHT = old_lbw
            continue

        for analysis in analyses:
            if analysis.get("error"):
                continue

            away = analysis["away_name"]
            home = analysis["home_name"]
            key = f"{away} @ {home}"
            actual = actual_results.get(key)
            if not actual:
                continue

            actual_margin = actual["actual_margin"]
            closing_spread = actual.get("closing_spread")
            closing_total = actual.get("closing_total")

            expected = analysis.get("expected", {})
            predicted_spread = expected.get("predicted_spread", 0)

            if closing_spread is None:
                continue

            edge = predicted_spread + closing_spread
            total_games += 1

            # Spread evaluation
            if abs(edge) >= 1.0:
                if edge > 0:
                    cover_margin = actual_margin + closing_spread
                else:
                    cover_margin = -(actual_margin + closing_spread)

                if cover_margin > 0:
                    spread_wins += 1
                elif cover_margin == 0:
                    spread_pushes += 1
                else:
                    spread_losses += 1

            # ML evaluation
            predicted_winner = away if predicted_spread > 0 else home
            actual_winner = away if actual_margin > 0 else home
            if abs(predicted_spread) >= 3.0:
                if predicted_winner == actual_winner:
                    ml_wins += 1
                else:
                    ml_losses += 1

        # Restore original config values
        cfg.HOME_COURT_ADVANTAGE = old_hca
        cfg.SEASON_WEIGHT = old_sw
        cfg.ROLLING_10_WEIGHT = old_r10w
        cfg.ROLLING_20_WEIGHT = old_r20w
        cfg.LOCATION_BLEND_WEIGHT = old_lbw

    spread_total = spread_wins + spread_losses
    spread_pct = spread_wins / spread_total * 100 if spread_total > 0 else 0
    ml_total = ml_wins + ml_losses
    ml_pct = ml_wins / ml_total * 100 if ml_total > 0 else 0

    return {
        "spread_wins": spread_wins,
        "spread_losses": spread_losses,
        "spread_pushes": spread_pushes,
        "spread_pct": round(spread_pct, 1),
        "ml_wins": ml_wins,
        "ml_losses": ml_losses,
        "ml_pct": round(ml_pct, 1),
        "total_games": total_games,
    }


def run_calibration(start_date: str, end_date: str):
    """Grid search over parameter combinations."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    # Build date list
    date_range = []
    current = start
    while current <= end:
        date_range.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    # Check how many cached data files exist
    cached = sum(1 for d in date_range
                 if (DATA_DIR / f"nba_data_{d.replace('-', '')}.json").exists())
    print(f"\n{'='*70}")
    print(f"NBA MODEL CALIBRATION")
    print(f"Date range: {start_date} to {end_date}")
    print(f"Cached data files: {cached}/{len(date_range)} days")
    print(f"{'='*70}\n")

    if cached == 0:
        print("ERROR: No cached data files found. Run backtest first to cache data.")
        return

    # Generate all parameter combinations
    keys = list(PARAM_GRID.keys())
    values = list(PARAM_GRID.values())
    combos = list(itertools.product(*values))
    print(f"Testing {len(combos)} parameter combinations...\n")

    best_result = None
    best_params = None
    best_spread_pct = 0
    results = []

    for i, combo in enumerate(combos):
        params = dict(zip(keys, combo))
        result = evaluate_params(params, date_range)

        results.append({"params": params, "result": result})

        # Track best by spread ATS%
        if result["spread_pct"] > best_spread_pct and (result["spread_wins"] + result["spread_losses"]) >= 5:
            best_spread_pct = result["spread_pct"]
            best_result = result
            best_params = params

        if (i + 1) % 50 == 0:
            print(f"  Tested {i+1}/{len(combos)} combos... (best so far: {best_spread_pct:.1f}% ATS)")

    # Sort by spread%
    results.sort(key=lambda x: -x["result"]["spread_pct"])

    print(f"\n{'='*70}")
    print("CALIBRATION RESULTS")
    print(f"{'='*70}\n")

    print("Top 10 Parameter Sets:\n")
    for i, r in enumerate(results[:10], 1):
        p = r["params"]
        res = r["result"]
        print(f"  {i}. Spread: {res['spread_wins']}-{res['spread_losses']} ({res['spread_pct']}%) | ML: {res['ml_wins']}-{res['ml_losses']} ({res['ml_pct']}%)")
        print(f"     DEFL={p['EFFICIENCY_DEFLATOR']} HCA={p['HOME_COURT_ADVANTAGE']} "
              f"SW={p['SEASON_WEIGHT']} LBW={p['LOCATION_BLEND_WEIGHT']} FF={p['ff_weight']}")
        print()

    if best_params:
        print(f"{'='*70}")
        print("BEST PARAMETERS")
        print(f"{'='*70}\n")
        for k, v in best_params.items():
            print(f"  {k}: {v}")
        print(f"\n  Spread: {best_result['spread_wins']}-{best_result['spread_losses']}-{best_result['spread_pushes']} ({best_result['spread_pct']}%)")
        print(f"  ML: {best_result['ml_wins']}-{best_result['ml_losses']} ({best_result['ml_pct']}%)")

    # Export results
    export_file = DATA_DIR / "nba_calibration_results.json"
    with open(export_file, "w") as f:
        json.dump({
            "date_range": f"{start_date} to {end_date}",
            "best_params": best_params,
            "best_result": best_result,
            "all_results": results[:50],  # Top 50
        }, f, indent=2, default=str)
    print(f"\n  Results exported to: {export_file}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 nba/nba_calibrate.py 2026-01-15 2026-02-06")
        sys.exit(1)

    start = sys.argv[1]
    end = sys.argv[2]
    for d in [start, end]:
        try:
            datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            print(f"Invalid date format: {d} (use YYYY-MM-DD)")
            sys.exit(1)

    run_calibration(start, end)
