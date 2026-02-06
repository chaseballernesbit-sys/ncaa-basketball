#!/usr/bin/env python3
"""
NCAA Basketball - Results Tracker
Tracks picks against actual game results to measure model performance.
"""

import json
import re
import requests
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
RESULTS_FILE = PROJECT_DIR / "results_history.json"

def fetch_espn_scores(date_str):
    """Fetch final scores from ESPN API for a given date (YYYYMMDD)"""
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
    params = {"dates": date_str, "limit": 200}
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        scores = {}
        for event in data.get("events", []):
            competition = event.get("competitions", [{}])[0]
            
            # Get teams and scores
            competitors = competition.get("competitors", [])
            if len(competitors) != 2:
                continue
                
            home = away = None
            for team in competitors:
                team_name = team.get("team", {}).get("displayName", "")
                score = int(team.get("score", 0)) if team.get("score") else None
                is_home = team.get("homeAway") == "home"
                
                if is_home:
                    home = {"name": team_name, "score": score}
                else:
                    away = {"name": team_name, "score": score}
            
            if home and away and home["score"] is not None:
                game_key = f"{away['name']}@{home['name']}"
                scores[game_key] = {
                    "home": home,
                    "away": away,
                    "home_score": home["score"],
                    "away_score": away["score"],
                    "total": home["score"] + away["score"],
                    "margin": home["score"] - away["score"],  # positive = home won
                }
        
        return scores
    except Exception as e:
        print(f"Error fetching ESPN scores: {e}")
        return {}


def normalize_team_name(name):
    """Normalize team name for matching"""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [" basketball", " men's", " women's"]:
        name = name.replace(suffix, "")
    # Handle common abbreviations
    replacements = {
        "st.": "state",
        "st ": "state ",
        "u of ": "",
        "university of ": "",
        "unc ": "north carolina ",
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    return name.strip()


def find_game_result(pick_home, pick_away, scores):
    """Find matching game result from scores dict"""
    pick_home_norm = normalize_team_name(pick_home)
    pick_away_norm = normalize_team_name(pick_away)
    
    for game_key, result in scores.items():
        home_norm = normalize_team_name(result["home"]["name"])
        away_norm = normalize_team_name(result["away"]["name"])
        
        # Check if names match (partial match)
        home_match = pick_home_norm in home_norm or home_norm in pick_home_norm
        away_match = pick_away_norm in away_norm or away_norm in pick_away_norm
        
        if home_match and away_match:
            return result
    
    return None


def parse_picks_from_analysis(analysis_file):
    """Parse picks from analysis markdown file"""
    picks = {"spreads": [], "totals": [], "moneylines": []}

    with open(analysis_file, 'r') as f:
        content = f.read()

    # Parse spread picks - format: ">> Team Name +/-XX.X ⭐⭐⭐" followed by "Edge: X.X pts"
    # Match lines like: "  >> Penn State +26.5 ⭐⭐⭐⭐⭐"
    spread_pattern = r">> ([^+\-\n]+?)\s+([+-][\d.]+)\s+⭐"
    edge_pattern = r"Edge: ([\d.]+) pts"

    lines = content.split('\n')
    for i, line in enumerate(lines):
        spread_match = re.search(spread_pattern, line)
        if spread_match and "OVER" not in line and "UNDER" not in line and "ML" not in line:
            team = spread_match.group(1).strip()
            spread = float(spread_match.group(2))

            # Look for edge in next few lines
            edge = 0
            for j in range(i+1, min(i+3, len(lines))):
                edge_match = re.search(edge_pattern, lines[j])
                if edge_match:
                    edge = float(edge_match.group(1))
                    break

            picks["spreads"].append({"team": team, "spread": spread, "edge": edge})

    # Parse totals - format: ">> OVER/UNDER XXX.X (Away vs Home) ⭐⭐⭐"
    total_pattern = r">> (OVER|UNDER) ([\d.]+) \(([^)]+)\)\s+⭐"

    for i, line in enumerate(lines):
        total_match = re.search(total_pattern, line)
        if total_match:
            direction = total_match.group(1)
            line_val = float(total_match.group(2))
            teams = total_match.group(3)

            # Parse "Away vs Home" format
            if " vs " in teams:
                parts = teams.split(" vs ")
                away = parts[0].strip()
                home = parts[1].strip()
            else:
                continue

            # Look for edge
            edge = 0
            for j in range(i+1, min(i+3, len(lines))):
                edge_match = re.search(r"Edge: ([\d.]+)", lines[j])
                if edge_match:
                    edge = float(edge_match.group(1))
                    break

            picks["totals"].append({
                "direction": direction,
                "line": line_val,
                "away": away,
                "home": home,
                "edge": edge
            })

    # Parse moneylines - format: ">> Team ML (-XXX) vs Opponent ⭐⭐⭐"
    ml_pattern = r">> ([^M]+?) ML \(([+-]?\d+)\) vs ([^⭐\n]+)"

    for i, line in enumerate(lines):
        ml_match = re.search(ml_pattern, line)
        if ml_match:
            team = ml_match.group(1).strip()
            odds = int(ml_match.group(2))
            opponent = ml_match.group(3).strip()

            # Look for edge
            edge = 0
            for j in range(i+1, min(i+3, len(lines))):
                edge_match = re.search(r"Edge: ([\d.]+)", lines[j])
                if edge_match:
                    edge = float(edge_match.group(1))
                    break

            picks["moneylines"].append({
                "team": team,
                "odds": odds,
                "opponent": opponent,
                "edge": edge
            })

    return picks


def evaluate_picks(picks, scores, date_str):
    """Evaluate picks against actual results"""
    results = {
        "date": date_str,
        "spreads": {"wins": 0, "losses": 0, "pushes": 0, "details": []},
        "totals": {"wins": 0, "losses": 0, "pushes": 0, "details": []},
        "moneylines": {"wins": 0, "losses": 0, "details": []},
    }
    
    # Evaluate spreads
    for pick in picks["spreads"]:
        team = pick["team"]
        spread = pick["spread"]
        
        # Find the game - need to figure out home/away
        game_found = False
        for game_key, game in scores.items():
            home_name = game["home"]["name"]
            away_name = game["away"]["name"]
            
            team_norm = normalize_team_name(team)
            home_norm = normalize_team_name(home_name)
            away_norm = normalize_team_name(away_name)
            
            if team_norm in home_norm or home_norm in team_norm:
                # Picked home team
                actual_margin = game["margin"]  # home - away
                covered = actual_margin + spread > 0
                push = actual_margin + spread == 0
                game_found = True
            elif team_norm in away_norm or away_norm in team_norm:
                # Picked away team
                actual_margin = -game["margin"]  # away - home
                covered = actual_margin + spread > 0
                push = actual_margin + spread == 0
                game_found = True
            else:
                continue
            
            detail = {
                "pick": f"{team} {spread:+.1f}",
                "game": game_key,
                "final": f"{game['away_score']}-{game['home_score']}",
                "margin": actual_margin,
                "result": "PUSH" if push else ("WIN" if covered else "LOSS"),
                "edge": pick["edge"]
            }
            results["spreads"]["details"].append(detail)
            
            if push:
                results["spreads"]["pushes"] += 1
            elif covered:
                results["spreads"]["wins"] += 1
            else:
                results["spreads"]["losses"] += 1
            break
        
        if not game_found:
            results["spreads"]["details"].append({
                "pick": f"{team} {spread:+.1f}",
                "result": "NOT FOUND"
            })
    
    # Evaluate totals
    for pick in picks["totals"]:
        direction = pick["direction"]
        line = pick["line"]
        home = pick["home"]
        away = pick["away"]
        
        result = find_game_result(home, away, scores)
        if result:
            actual_total = result["total"]
            
            if direction == "OVER":
                won = actual_total > line
                push = actual_total == line
            else:
                won = actual_total < line
                push = actual_total == line
            
            detail = {
                "pick": f"{direction} {line} ({away}@{home})",
                "actual_total": actual_total,
                "result": "PUSH" if push else ("WIN" if won else "LOSS"),
                "edge": pick["edge"]
            }
            results["totals"]["details"].append(detail)
            
            if push:
                results["totals"]["pushes"] += 1
            elif won:
                results["totals"]["wins"] += 1
            else:
                results["totals"]["losses"] += 1
        else:
            results["totals"]["details"].append({
                "pick": f"{direction} {line} ({away}@{home})",
                "result": "NOT FOUND"
            })
    
    # Evaluate moneylines
    for pick in picks["moneylines"]:
        team = pick["team"]
        opponent = pick["opponent"]
        
        # Find game
        for game_key, game in scores.items():
            home_name = game["home"]["name"]
            away_name = game["away"]["name"]
            
            team_norm = normalize_team_name(team)
            home_norm = normalize_team_name(home_name)
            away_norm = normalize_team_name(away_name)
            
            if team_norm in home_norm or home_norm in team_norm:
                won = game["margin"] > 0  # home won
                game_found = True
            elif team_norm in away_norm or away_norm in team_norm:
                won = game["margin"] < 0  # away won
                game_found = True
            else:
                continue
            
            detail = {
                "pick": f"{team} ML ({pick['odds']:+d})",
                "game": game_key,
                "final": f"{game['away_score']}-{game['home_score']}",
                "result": "WIN" if won else "LOSS",
                "edge": pick["edge"]
            }
            results["moneylines"]["details"].append(detail)
            
            if won:
                results["moneylines"]["wins"] += 1
            else:
                results["moneylines"]["losses"] += 1
            break
    
    return results


def load_results_history():
    """Load historical results"""
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE, 'r') as f:
            return json.load(f)
    return {"days": [], "totals": {"spreads": {"w": 0, "l": 0, "p": 0}, 
                                    "totals": {"w": 0, "l": 0, "p": 0},
                                    "moneylines": {"w": 0, "l": 0}}}


def save_results_history(history):
    """Save results history"""
    with open(RESULTS_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def main():
    """Track results for recent days"""
    print("=" * 60)
    print("NCAA BASKETBALL - RESULTS TRACKER")
    print("=" * 60)
    
    history = load_results_history()
    tracked_dates = [d["date"] for d in history["days"]]
    
    # Check last 3 days
    for days_ago in range(1, 4):
        check_date = datetime.now() - timedelta(days=days_ago)
        date_str = check_date.strftime("%Y%m%d")
        display_date = check_date.strftime("%Y-%m-%d")
        
        if date_str in tracked_dates:
            print(f"\n{display_date}: Already tracked")
            continue
        
        # Check if we have analysis file
        analysis_file = DATA_DIR / f"analysis_{date_str}.md"
        if not analysis_file.exists():
            print(f"\n{display_date}: No analysis file found")
            continue
        
        print(f"\n{display_date}: Fetching scores...")
        scores = fetch_espn_scores(date_str)
        
        if not scores:
            print(f"  No scores available yet")
            continue
        
        print(f"  Found {len(scores)} completed games")
        
        # Parse picks and evaluate
        picks = parse_picks_from_analysis(analysis_file)
        print(f"  Parsed: {len(picks['spreads'])} spreads, {len(picks['totals'])} totals, {len(picks['moneylines'])} MLs")
        
        results = evaluate_picks(picks, scores, date_str)
        
        # Print results
        print(f"\n  SPREADS: {results['spreads']['wins']}-{results['spreads']['losses']}-{results['spreads']['pushes']}")
        for d in results['spreads']['details'][:5]:
            print(f"    {d['result']}: {d['pick']} | {d.get('final', 'N/A')}")
        
        print(f"\n  TOTALS: {results['totals']['wins']}-{results['totals']['losses']}-{results['totals']['pushes']}")
        for d in results['totals']['details'][:5]:
            print(f"    {d['result']}: {d['pick']} | Total: {d.get('actual_total', 'N/A')}")
        
        print(f"\n  MONEYLINES: {results['moneylines']['wins']}-{results['moneylines']['losses']}")
        for d in results['moneylines']['details'][:5]:
            print(f"    {d['result']}: {d['pick']} | {d.get('final', 'N/A')}")
        
        # Update history
        history["days"].append(results)
        history["totals"]["spreads"]["w"] += results["spreads"]["wins"]
        history["totals"]["spreads"]["l"] += results["spreads"]["losses"]
        history["totals"]["spreads"]["p"] += results["spreads"]["pushes"]
        history["totals"]["totals"]["w"] += results["totals"]["wins"]
        history["totals"]["totals"]["l"] += results["totals"]["losses"]
        history["totals"]["totals"]["p"] += results["totals"]["pushes"]
        history["totals"]["moneylines"]["w"] += results["moneylines"]["wins"]
        history["totals"]["moneylines"]["l"] += results["moneylines"]["losses"]
    
    # Print overall summary
    print("\n" + "=" * 60)
    print("OVERALL RECORD")
    print("=" * 60)
    
    t = history["totals"]
    spread_total = t["spreads"]["w"] + t["spreads"]["l"]
    total_total = t["totals"]["w"] + t["totals"]["l"]
    ml_total = t["moneylines"]["w"] + t["moneylines"]["l"]
    
    if spread_total > 0:
        spread_pct = t["spreads"]["w"] / spread_total * 100
        print(f"Spreads:    {t['spreads']['w']}-{t['spreads']['l']}-{t['spreads']['p']} ({spread_pct:.1f}%)")
    
    if total_total > 0:
        total_pct = t["totals"]["w"] / total_total * 100
        print(f"Totals:     {t['totals']['w']}-{t['totals']['l']}-{t['totals']['p']} ({total_pct:.1f}%)")
    
    if ml_total > 0:
        ml_pct = t["moneylines"]["w"] / ml_total * 100
        print(f"Moneylines: {t['moneylines']['w']}-{t['moneylines']['l']} ({ml_pct:.1f}%)")
    
    save_results_history(history)
    print(f"\nResults saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
