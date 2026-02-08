#!/usr/bin/env python3
"""
NCAA Basketball Model Calibration & Backtesting

Uses historical data files (ncaa_data_*.json + analysis_*.md) to evaluate
model accuracy and find optimal parameters.

Run: python3 calibrate_model.py
"""

import json
import re
import sys
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"

sys.path.insert(0, str(PROJECT_DIR))
from team_mappings import normalize_team_name as canonical_name


def fetch_espn_scores(date_str: str) -> Dict:
    """Fetch final scores from ESPN API for a given date (YYYYMMDD)"""
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
    params = {"dates": date_str, "limit": 200}
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        scores = {}
        for event in data.get("events", []):
            competition = event.get("competitions", [{}])[0]
            competitors = competition.get("competitors", [])
            if len(competitors) != 2:
                continue
            home = away = None
            for team in competitors:
                team_name = team.get("team", {}).get("displayName", "")
                score = int(team.get("score", 0)) if team.get("score") else None
                if team.get("homeAway") == "home":
                    home = {"name": team_name, "score": score}
                else:
                    away = {"name": team_name, "score": score}
            if home and away and home["score"] is not None:
                game_key = f"{away['name']}@{home['name']}"
                scores[game_key] = {
                    "home": home, "away": away,
                    "home_score": home["score"], "away_score": away["score"],
                    "total": home["score"] + away["score"],
                    "margin": home["score"] - away["score"],
                }
        return scores
    except Exception as e:
        print(f"  Error fetching scores for {date_str}: {e}")
        return {}


def match_team(pick_name: str, espn_name: str) -> bool:
    """Check if a pick team name matches an ESPN team name."""
    pick_canon = (canonical_name(pick_name) or pick_name).lower().strip()
    espn_canon = (canonical_name(espn_name) or espn_name).lower().strip()
    if pick_canon == espn_canon:
        return True
    # Substring fallback
    return pick_canon in espn_canon or espn_canon in pick_canon


def parse_detailed_games(analysis_file: Path) -> List[Dict]:
    """
    Parse all detailed game analyses from the markdown report.
    Extracts model predicted spread, predicted total, and line for each game.
    """
    games = []
    with open(analysis_file, 'r') as f:
        content = f.read()

    # Split into game sections
    game_sections = re.split(r'## GAME \d+:', content)

    for section in game_sections[1:]:  # Skip header
        game = {}
        lines = section.strip().split('\n')

        # Extract team names from first line: "#9 Nebraska @ #99 Rutgers"
        # or "Nebraska Cornhuskers @ Rutgers Scarlet Knights"
        first_line = lines[0].strip() if lines else ""
        team_match = re.match(r'(?:#\d+\s+)?(.+?)\s+@\s+(?:#\d+\s+)?(.+)', first_line)
        if not team_match:
            continue
        game['away'] = team_match.group(1).strip()
        game['home'] = team_match.group(2).strip()

        for line in lines:
            # Model spread: "- Predicted spread: -10.9 (from Nebraska perspective)"
            spread_match = re.search(r'Predicted spread:\s+([+-]?[\d.]+)', line)
            if spread_match:
                game['model_spread'] = float(spread_match.group(1))

            # Predicted total: "- Predicted total: 144.6"
            total_match = re.search(r'Predicted total:\s+([\d.]+)', line)
            if total_match:
                game['model_total'] = float(total_match.group(1))

            # Actual line: "- Actual line: -12.5" or "**LINE:** Rutgers +12.5"
            line_match = re.search(r'(?:Actual line|Model spread):\s+([+-]?[\d.]+)', line)
            if line_match and 'actual_spread' not in game:
                pass  # We get this from LINE below

            line_match2 = re.search(r'\*\*LINE:\*\*\s+\S+\s+([+-]?[\d.]+)', line)
            if line_match2:
                game['actual_spread'] = float(line_match2.group(1))

            # Total line: "**TOTAL:** 143.0"
            total_line_match = re.search(r'\*\*TOTAL:\*\*\s+([\d.]+)', line)
            if total_line_match:
                game['actual_total'] = float(total_line_match.group(1))

            # Model spread from VALUE section: "- Model spread: -10.0"
            model_sp = re.search(r'Model spread:\s+([+-]?[\d.]+)', line)
            if model_sp:
                game['final_model_spread'] = float(model_sp.group(1))

        if 'model_spread' in game or 'final_model_spread' in game:
            games.append(game)

    return games


def backtest_date(date_str: str) -> Dict:
    """Run backtest for a single date. Returns accuracy metrics."""
    analysis_file = DATA_DIR / f"analysis_{date_str}.md"
    if not analysis_file.exists():
        return None

    scores = fetch_espn_scores(date_str)
    if not scores:
        return None

    model_games = parse_detailed_games(analysis_file)
    if not model_games:
        return None

    results = {
        'date': date_str,
        'games_analyzed': len(model_games),
        'games_matched': 0,
        'spread_errors': [],      # model_spread - actual_margin
        'total_errors': [],       # model_total - actual_total
        'spread_ats_record': {'w': 0, 'l': 0, 'p': 0},
        'total_ou_record': {'w': 0, 'l': 0, 'p': 0},
        'winner_correct': 0,
        'winner_total': 0,
    }

    for game in model_games:
        away_name = game['away']
        home_name = game['home']

        # Find matching score
        matched_score = None
        for key, score in scores.items():
            if (match_team(away_name, score['away']['name']) and
                match_team(home_name, score['home']['name'])):
                matched_score = score
                break

        if not matched_score:
            continue

        results['games_matched'] += 1
        actual_margin = matched_score['margin']  # home - away (positive = home won)
        actual_total = matched_score['total']

        # Use final_model_spread if available, else model_spread
        model_spread = game.get('final_model_spread', game.get('model_spread'))
        model_total = game.get('model_total')

        # Spread accuracy (model_spread is from away perspective, positive = away is underdog)
        if model_spread is not None:
            # Model predicted margin from home perspective
            model_home_margin = -model_spread if model_spread != 0 else 0
            spread_error = model_spread - (-actual_margin)  # error in away-perspective spread
            results['spread_errors'].append(spread_error)

            # Did model pick the winner correctly?
            results['winner_total'] += 1
            if (model_spread < 0 and actual_margin < 0) or (model_spread > 0 and actual_margin > 0):
                results['winner_correct'] += 1
            elif model_spread == 0:
                pass  # Skip pure toss-ups

            # ATS: did model beat the line?
            actual_spread = game.get('actual_spread')
            if actual_spread is not None:
                # Away perspective: away covers if away_margin + spread > 0
                away_actual_margin = -actual_margin
                value = actual_spread - model_spread
                if value >= 3.0:
                    # Model said take away
                    if away_actual_margin + actual_spread > 0:
                        results['spread_ats_record']['w'] += 1
                    elif away_actual_margin + actual_spread == 0:
                        results['spread_ats_record']['p'] += 1
                    else:
                        results['spread_ats_record']['l'] += 1
                elif value <= -3.0:
                    # Model said take home
                    home_covers = actual_margin - actual_spread > 0
                    if actual_margin - actual_spread > 0:
                        results['spread_ats_record']['w'] += 1
                    elif actual_margin - actual_spread == 0:
                        results['spread_ats_record']['p'] += 1
                    else:
                        results['spread_ats_record']['l'] += 1

        # Total accuracy
        if model_total is not None:
            total_error = model_total - actual_total
            results['total_errors'].append(total_error)

            # O/U: did model beat the line?
            actual_total_line = game.get('actual_total')
            if actual_total_line is not None:
                edge = model_total - actual_total_line
                if edge >= 8.0:
                    # Model said OVER
                    if actual_total > actual_total_line:
                        results['total_ou_record']['w'] += 1
                    elif actual_total == actual_total_line:
                        results['total_ou_record']['p'] += 1
                    else:
                        results['total_ou_record']['l'] += 1
                elif edge <= -8.0:
                    # Model said UNDER
                    if actual_total < actual_total_line:
                        results['total_ou_record']['w'] += 1
                    elif actual_total == actual_total_line:
                        results['total_ou_record']['p'] += 1
                    else:
                        results['total_ou_record']['l'] += 1

    return results


def compute_summary(all_results: List[Dict]) -> Dict:
    """Compute aggregate metrics across all backtested dates."""
    all_spread_errors = []
    all_total_errors = []
    total_matched = 0
    total_analyzed = 0
    winner_correct = 0
    winner_total = 0
    ats = {'w': 0, 'l': 0, 'p': 0}
    ou = {'w': 0, 'l': 0, 'p': 0}

    for r in all_results:
        all_spread_errors.extend(r['spread_errors'])
        all_total_errors.extend(r['total_errors'])
        total_matched += r['games_matched']
        total_analyzed += r['games_analyzed']
        winner_correct += r['winner_correct']
        winner_total += r['winner_total']
        for k in ['w', 'l', 'p']:
            ats[k] += r['spread_ats_record'][k]
            ou[k] += r['total_ou_record'][k]

    summary = {
        'dates_tested': len(all_results),
        'games_analyzed': total_analyzed,
        'games_matched': total_matched,
        'match_rate': f"{total_matched/total_analyzed*100:.1f}%" if total_analyzed else "N/A",
    }

    if all_spread_errors:
        import math
        mae = sum(abs(e) for e in all_spread_errors) / len(all_spread_errors)
        rmse = math.sqrt(sum(e**2 for e in all_spread_errors) / len(all_spread_errors))
        mean_error = sum(all_spread_errors) / len(all_spread_errors)
        summary['spread'] = {
            'n': len(all_spread_errors),
            'MAE': round(mae, 2),
            'RMSE': round(rmse, 2),
            'mean_error': round(mean_error, 2),  # Positive = model over-predicts away
        }

    if winner_total:
        summary['winner_accuracy'] = f"{winner_correct}/{winner_total} ({winner_correct/winner_total*100:.1f}%)"

    if all_total_errors:
        import math
        mae = sum(abs(e) for e in all_total_errors) / len(all_total_errors)
        rmse = math.sqrt(sum(e**2 for e in all_total_errors) / len(all_total_errors))
        mean_error = sum(all_total_errors) / len(all_total_errors)
        summary['totals'] = {
            'n': len(all_total_errors),
            'MAE': round(mae, 2),
            'RMSE': round(rmse, 2),
            'mean_error': round(mean_error, 2),  # Positive = model over-predicts total
        }

    ats_total = ats['w'] + ats['l']
    if ats_total:
        summary['ATS_record'] = f"{ats['w']}-{ats['l']}-{ats['p']} ({ats['w']/ats_total*100:.1f}%)"
    else:
        summary['ATS_record'] = "No picks met threshold"

    ou_total = ou['w'] + ou['l']
    if ou_total:
        summary['OU_record'] = f"{ou['w']}-{ou['l']}-{ou['p']} ({ou['w']/ou_total*100:.1f}%)"
    else:
        summary['OU_record'] = "No picks met threshold"

    return summary


def main():
    print("=" * 60)
    print("NCAA BASKETBALL MODEL CALIBRATION")
    print("=" * 60)

    # Find all available analysis files
    analysis_files = sorted(DATA_DIR.glob("analysis_*.md"))
    if not analysis_files:
        print("No analysis files found in data/")
        return

    print(f"Found {len(analysis_files)} analysis files")

    all_results = []
    for f in analysis_files:
        date_str = f.stem.replace("analysis_", "")
        # Skip today (games haven't finished)
        today = datetime.now().strftime("%Y%m%d")
        if date_str >= today:
            print(f"\n{date_str}: Skipping (today/future)")
            continue

        print(f"\n{date_str}: Backtesting...")
        result = backtest_date(date_str)
        if result:
            print(f"  Matched {result['games_matched']}/{result['games_analyzed']} games")
            if result['spread_errors']:
                mae = sum(abs(e) for e in result['spread_errors']) / len(result['spread_errors'])
                print(f"  Spread MAE: {mae:.1f} pts")
            if result['total_errors']:
                mae = sum(abs(e) for e in result['total_errors']) / len(result['total_errors'])
                print(f"  Total MAE: {mae:.1f} pts")
            all_results.append(result)
        else:
            print(f"  No data available")

    if not all_results:
        print("\nNo results to summarize.")
        return

    # Compute and display summary
    summary = compute_summary(all_results)

    print("\n" + "=" * 60)
    print("CALIBRATION SUMMARY")
    print("=" * 60)
    print(f"Dates tested: {summary['dates_tested']}")
    print(f"Games analyzed: {summary['games_analyzed']}")
    print(f"Games matched: {summary['games_matched']} ({summary['match_rate']})")

    if 'spread' in summary:
        s = summary['spread']
        print(f"\nSPREAD PREDICTION ACCURACY ({s['n']} games):")
        print(f"  Mean Absolute Error: {s['MAE']} pts")
        print(f"  RMSE:                {s['RMSE']} pts")
        print(f"  Mean Error (bias):   {s['mean_error']:+.2f} pts")
        if s['mean_error'] > 1:
            print(f"  --> Model over-predicts away team (or under-predicts home)")
        elif s['mean_error'] < -1:
            print(f"  --> Model over-predicts home team (or under-predicts away)")

    if 'winner_accuracy' in summary:
        print(f"\nStraight-up winner: {summary['winner_accuracy']}")

    print(f"\nATS Record: {summary['ATS_record']}")

    if 'totals' in summary:
        t = summary['totals']
        print(f"\nTOTALS PREDICTION ACCURACY ({t['n']} games):")
        print(f"  Mean Absolute Error: {t['MAE']} pts")
        print(f"  RMSE:                {t['RMSE']} pts")
        print(f"  Mean Error (bias):   {t['mean_error']:+.2f} pts")
        if t['mean_error'] > 2:
            print(f"  --> Model over-predicts totals (need more regression)")
        elif t['mean_error'] < -2:
            print(f"  --> Model under-predicts totals (too much regression)")

    print(f"\nO/U Record: {summary['OU_record']}")

    # Recommendations
    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)

    if 'spread' in summary:
        if summary['spread']['MAE'] > 10:
            print("- Spread MAE > 10: Model needs significant work on efficiency formula")
        elif summary['spread']['MAE'] > 8:
            print("- Spread MAE 8-10: Decent but room for improvement")
        else:
            print("- Spread MAE < 8: Good accuracy for college basketball")

        bias = summary['spread']['mean_error']
        if abs(bias) > 1.5:
            print(f"- Spread bias of {bias:+.1f}: Adjust EFFICIENCY_DEFLATOR or HCA")

    if 'totals' in summary:
        bias = summary['totals']['mean_error']
        if bias > 3:
            print(f"- Totals bias of {bias:+.1f}: Increase TOTAL_REGRESSION (currently over-predicting)")
        elif bias < -3:
            print(f"- Totals bias of {bias:+.1f}: Decrease TOTAL_REGRESSION (currently under-predicting)")
        else:
            print(f"- Totals bias of {bias:+.1f}: Regression factor looks reasonable")

    # Save calibration results
    cal_file = DATA_DIR / "calibration_results.json"
    with open(cal_file, 'w') as f:
        json.dump({
            'run_date': datetime.now().isoformat(),
            'summary': summary,
            'daily_results': [{
                'date': r['date'],
                'matched': r['games_matched'],
                'analyzed': r['games_analyzed'],
                'spread_mae': round(sum(abs(e) for e in r['spread_errors']) / len(r['spread_errors']), 2) if r['spread_errors'] else None,
                'total_mae': round(sum(abs(e) for e in r['total_errors']) / len(r['total_errors']), 2) if r['total_errors'] else None,
            } for r in all_results]
        }, f, indent=2)
    print(f"\nCalibration results saved to {cal_file}")


if __name__ == "__main__":
    main()
