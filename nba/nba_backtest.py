#!/usr/bin/env python3
"""
NBA Backtest - Run model on past dates and compare picks vs actual results.
Usage:
  Single date:  python3 nba/nba_backtest.py 2026-02-06
  Date range:   python3 nba/nba_backtest.py 2026-01-15 2026-02-06
"""

import sys
import os
import json
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba.nba_scraper import NBADataScraper
from nba.nba_analyzer import NBAAnalyzer
from nba.nba_team_mappings import normalize_team_name

PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data"


def fetch_actual_results(date_str: str) -> dict:
    """Fetch final scores AND closing lines from ESPN for a given date."""
    compact = date_str.replace("-", "")
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    params = {"dates": compact}

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    results = {}
    for event in data.get("events", []):
        competition = event.get("competitions", [{}])[0]
        competitors = competition.get("competitors", [])
        status = event.get("status", {}).get("type", {}).get("name", "")

        if status != "STATUS_FINAL" or len(competitors) < 2:
            continue

        home_comp = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away_comp = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

        home_name = normalize_team_name(home_comp.get("team", {}).get("displayName", ""))
        away_name = normalize_team_name(away_comp.get("team", {}).get("displayName", ""))

        home_score = int(home_comp.get("score", 0))
        away_score = int(away_comp.get("score", 0))

        # Fetch closing odds from ESPN event summary
        game_id = event.get("id", "")
        closing_spread = None
        closing_total = None
        spread_fav = None
        try:
            summary = requests.get(
                f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={game_id}",
                timeout=10
            ).json()
            pickcenter = summary.get("pickcenter", [])
            if pickcenter:
                pc = pickcenter[0]
                closing_total = pc.get("overUnder")
                details = pc.get("details", "")  # e.g. "BOS -5.5"
                if details:
                    parts = details.split()
                    if len(parts) == 2:
                        spread_fav = parts[0]  # abbreviation of favored team
                        spread_val = float(parts[1])  # negative number
                        # Convert to away spread convention
                        if spread_fav == away_comp.get("team", {}).get("abbreviation", ""):
                            closing_spread = spread_val  # away is favored (negative)
                        else:
                            closing_spread = -spread_val  # home is favored, away gets points
        except Exception:
            pass

        key = f"{away_name} @ {home_name}"
        results[key] = {
            "away_name": away_name,
            "home_name": home_name,
            "away_score": away_score,
            "home_score": home_score,
            "total": away_score + home_score,
            "actual_margin": away_score - home_score,
            "closing_spread": closing_spread,  # away team's spread
            "closing_total": closing_total,
        }

    return results


def run_backtest_single(date_str: str, verbose: bool = True):
    """Run the full backtest for a single date. Returns per-pick results."""
    compact = date_str.replace("-", "")
    data_file = DATA_DIR / f"nba_data_{compact}.json"

    if verbose:
        print(f"\n{'='*70}")
        print(f"NBA BACKTEST - {date_str}")
        print(f"{'='*70}\n")

    # Step 1: Scrape data for that date (or use cached)
    if data_file.exists():
        if verbose:
            print(f"Using cached data: {data_file}")
        with open(data_file) as f:
            data = json.load(f)
    else:
        if verbose:
            print("Scraping data...")
        scraper = NBADataScraper()
        data = scraper.run(date_str=date_str)

    # Step 2: Run analyzer
    if verbose:
        print("Running analyzer...")
    analyzer = NBAAnalyzer(data)
    analyses = analyzer.analyze_all_games()

    # Step 3: Fetch actual results + closing lines from ESPN
    if verbose:
        print("Fetching actual results + closing lines from ESPN...")
    actual_results = fetch_actual_results(date_str)
    if verbose:
        print(f"Final scores found: {len(actual_results)} games\n")

    if not actual_results:
        if verbose:
            print("ERROR: No final scores found. Games may not have been played yet.")
        return [], {}

    # Step 4: Compare picks vs results
    spread_wins = 0
    spread_losses = 0
    spread_pushes = 0
    ml_wins = 0
    ml_losses = 0
    total_wins = 0
    total_losses = 0
    per_pick_results = []

    for analysis in analyses:
        if analysis.get("error"):
            continue

        away = analysis["away_name"]
        home = analysis["home_name"]
        key = f"{away} @ {home}"

        actual = actual_results.get(key)
        if not actual:
            if verbose:
                print(f"  {key}: No final score found")
            continue

        actual_margin = actual["actual_margin"]  # away - home
        actual_total_score = actual["total"]
        away_score = actual["away_score"]
        home_score = actual["home_score"]
        closing_spread = actual.get("closing_spread")  # away team's spread from ESPN
        closing_total = actual.get("closing_total")

        expected = analysis.get("expected", {})
        predicted_spread = expected.get("predicted_spread", 0)
        predicted_total = expected.get("predicted_total", 0)
        sit = analysis.get("situational", {})

        # Use closing line from ESPN for evaluation
        line_spread = closing_spread
        line_total = closing_total

        # Calculate edge using closing line
        if line_spread is not None:
            edge = predicted_spread + line_spread
        else:
            edge = 0

        if verbose:
            print(f"  {away} @ {home}")
            print(f"    Actual: {away} {away_score} - {home} {home_score} (margin: {actual_margin:+.0f})")
            print(f"    Model:  predicted margin {predicted_spread:+.1f}, closing line: {line_spread if line_spread is not None else 'N/A'}, edge: {edge:+.1f}")

        pick_record = {
            "date": date_str,
            "away_team": away,
            "home_team": home,
            "predicted_spread": predicted_spread,
            "predicted_total": predicted_total,
            "closing_spread": line_spread,
            "closing_total": line_total,
            "actual_away_score": away_score,
            "actual_home_score": home_score,
            "actual_margin": actual_margin,
            "actual_total": actual_total_score,
            "edge": round(edge, 1),
            "sit_adjustment": sit.get("total_adjustment", 0),
            "adjustments": sit.get("adjustments", []),
        }

        # Spread pick evaluation
        if line_spread is not None and abs(edge) >= 1.0:
            if edge > 0:
                pick_team = away
                pick_side = "AWAY"
                cover_margin = actual_margin + line_spread
            else:
                pick_team = home
                pick_side = "HOME"
                cover_margin = -(actual_margin + line_spread)

            if cover_margin > 0:
                result = "WIN"
                spread_wins += 1
            elif cover_margin == 0:
                result = "PUSH"
                spread_pushes += 1
            else:
                result = "LOSS"
                spread_losses += 1

            pick_record["spread_pick"] = pick_side
            pick_record["spread_result"] = result
            pick_record["cover_margin"] = round(cover_margin, 1)

            if verbose:
                print(f"    Spread pick: {pick_team} ({pick_side}) {line_spread:+.1f} -> {result} (covered by {cover_margin:+.1f})")

        # ML pick evaluation
        winner_actual = away if actual_margin > 0 else home
        predicted_winner = away if predicted_spread > 0 else home
        margin_threshold = 3.0

        if abs(predicted_spread) >= margin_threshold:
            if predicted_winner == winner_actual:
                ml_result = "WIN"
                ml_wins += 1
            else:
                ml_result = "LOSS"
                ml_losses += 1
            pick_record["ml_pick"] = predicted_winner
            pick_record["ml_result"] = ml_result
            if verbose:
                print(f"    ML pick: {predicted_winner} -> {ml_result}")

        # Totals evaluation
        if line_total and abs(predicted_total - line_total) >= 3.0:
            if predicted_total > line_total:
                total_pick = "OVER"
                total_correct = actual_total_score > line_total
            else:
                total_pick = "UNDER"
                total_correct = actual_total_score < line_total

            if total_correct:
                total_wins += 1
                t_result = "WIN"
            else:
                total_losses += 1
                t_result = "LOSS"
            pick_record["total_pick"] = total_pick
            pick_record["total_result"] = t_result
            if verbose:
                print(f"    Total pick: {total_pick} {line_total} (actual: {actual_total_score}) -> {t_result}")

        per_pick_results.append(pick_record)
        if verbose:
            print()

    summary = {
        "spread_wins": spread_wins,
        "spread_losses": spread_losses,
        "spread_pushes": spread_pushes,
        "ml_wins": ml_wins,
        "ml_losses": ml_losses,
        "total_wins": total_wins,
        "total_losses": total_losses,
    }

    if verbose:
        _print_summary(summary)

    return per_pick_results, summary


def _print_summary(s: dict, label: str = "BACKTEST SUMMARY"):
    """Print a formatted summary."""
    print(f"{'='*70}")
    print(label)
    print(f"{'='*70}\n")

    spread_total = s["spread_wins"] + s["spread_losses"] + s["spread_pushes"]
    if spread_total > 0:
        win_pct = s["spread_wins"] / (s["spread_wins"] + s["spread_losses"]) * 100 if (s["spread_wins"] + s["spread_losses"]) > 0 else 0
        print(f"  SPREAD:     {s['spread_wins']}-{s['spread_losses']}-{s['spread_pushes']}  ({win_pct:.0f}%)")

    ml_total = s["ml_wins"] + s["ml_losses"]
    if ml_total > 0:
        ml_pct = s["ml_wins"] / ml_total * 100
        print(f"  MONEYLINE:  {s['ml_wins']}-{s['ml_losses']}  ({ml_pct:.0f}%)")

    totals_total = s["total_wins"] + s["total_losses"]
    if totals_total > 0:
        totals_pct = s["total_wins"] / totals_total * 100
        print(f"  TOTALS:     {s['total_wins']}-{s['total_losses']}  ({totals_pct:.0f}%)")

    overall_w = s["spread_wins"] + s["ml_wins"] + s["total_wins"]
    overall_l = s["spread_losses"] + s["ml_losses"] + s["total_losses"]
    if overall_w + overall_l > 0:
        overall_pct = overall_w / (overall_w + overall_l) * 100
        print(f"\n  OVERALL:    {overall_w}-{overall_l}  ({overall_pct:.0f}%)")

    print()


def run_backtest_range(start_date: str, end_date: str):
    """Run backtest across a date range and aggregate results."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    print(f"\n{'='*70}")
    print(f"NBA BACKTEST RANGE: {start_date} to {end_date}")
    print(f"{'='*70}\n")

    all_picks = []
    agg = {
        "spread_wins": 0, "spread_losses": 0, "spread_pushes": 0,
        "ml_wins": 0, "ml_losses": 0,
        "total_wins": 0, "total_losses": 0,
    }
    dates_tested = 0

    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        try:
            picks, summary = run_backtest_single(date_str, verbose=False)
            if picks:
                all_picks.extend(picks)
                for key in agg:
                    agg[key] += summary.get(key, 0)
                dates_tested += 1
                s_w = summary["spread_wins"]
                s_l = summary["spread_losses"]
                s_tot = s_w + s_l
                s_pct = f"{s_w / s_tot * 100:.0f}%" if s_tot > 0 else "N/A"
                print(f"  {date_str}: {len(picks)} games | Spread: {s_w}-{s_l} ({s_pct}) | ML: {summary['ml_wins']}-{summary['ml_losses']} | Totals: {summary['total_wins']}-{summary['total_losses']}")
            else:
                print(f"  {date_str}: No games/results")
        except Exception as e:
            print(f"  {date_str}: ERROR - {e}")

        current += timedelta(days=1)
        time.sleep(0.5)  # Be polite to ESPN API

    # Export per-pick JSON
    export_file = DATA_DIR / "nba_backtest_results.json"
    with open(export_file, "w") as f:
        json.dump({
            "date_range": f"{start_date} to {end_date}",
            "dates_tested": dates_tested,
            "total_picks": len(all_picks),
            "summary": agg,
            "picks": all_picks,
        }, f, indent=2, default=str)
    print(f"\n  Per-pick results exported to: {export_file}")

    # Aggregate summary
    print()
    _print_summary(agg, label=f"AGGREGATE BACKTEST: {start_date} to {end_date} ({dates_tested} days)")

    return all_picks, agg


# Backward-compatible single-date function
def run_backtest(date_str: str):
    """Run the full backtest for a given date (backward-compatible wrapper)."""
    run_backtest_single(date_str, verbose=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Single date:  python3 nba/nba_backtest.py 2026-02-06")
        print("  Date range:   python3 nba/nba_backtest.py 2026-01-15 2026-02-06")
        sys.exit(1)

    target_date = sys.argv[1]
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        print(f"Invalid date format: {target_date} (use YYYY-MM-DD)")
        sys.exit(1)

    if len(sys.argv) >= 3:
        end_date = sys.argv[2]
        try:
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            print(f"Invalid end date format: {end_date} (use YYYY-MM-DD)")
            sys.exit(1)
        run_backtest_range(target_date, end_date)
    else:
        run_backtest(target_date)
