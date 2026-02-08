#!/usr/bin/env python3
"""
NBA Pick Tracker
Saves daily picks to JSON and updates results from ESPN.
Mirrors NHL's prediction_tracker.py pattern.
"""

import json
import sys
import requests
from datetime import datetime, date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from nba.nba_team_mappings import normalize_team_name

PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data"
PICKS_FILE = DATA_DIR / "nba_picks_history.json"


def load_picks() -> dict:
    """Load existing picks history."""
    if PICKS_FILE.exists():
        with open(PICKS_FILE) as f:
            data = json.load(f)
        if "locked_dates" not in data:
            data["locked_dates"] = []
        return data
    return {"picks": [], "locked_dates": []}


def is_day_locked(date_str: str) -> bool:
    """Check if a day's picks are locked."""
    data = load_picks()
    return date_str in data.get("locked_dates", [])


def lock_day(date_str: str):
    """Lock a day's picks so they can't be overwritten."""
    data = load_picks()
    if "locked_dates" not in data:
        data["locked_dates"] = []
    if date_str not in data["locked_dates"]:
        data["locked_dates"].append(date_str)
        save_picks(data)
        print(f"Pick tracker: locked picks for {date_str}")


def save_picks(data: dict):
    """Save picks history."""
    DATA_DIR.mkdir(exist_ok=True)
    with open(PICKS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def save_today_picks(analyses: list, games: list):
    """Save today's actionable picks from analyzer output.

    Before locking, each run overwrites today's picks with the latest.
    After locking, picks are frozen and this function is a no-op for today.

    Args:
        analyses: List of analysis dicts from NBAAnalyzer.analyze_all_games()
        games: List of game dicts from scraper (contains game_id)
    """
    data = load_picks()
    today = date.today().isoformat()

    # Don't touch locked days
    if today in data.get("locked_dates", []):
        print(f"Pick tracker: {today} is locked, skipping save")
        return

    # Build game_id lookup: "away @ home" -> game_id
    game_id_map = {}
    for game in games:
        away = game.get("away", {}).get("name", "")
        home = game.get("home", {}).get("name", "")
        gid = game.get("game_id", "")
        if away and home and gid:
            game_id_map[f"{away} @ {home}"] = gid

    # Remove existing today's picks (overwrite with latest)
    data["picks"] = [p for p in data["picks"] if p.get("date") != today]

    added = 0
    for analysis in analyses:
        if analysis.get("error"):
            continue

        away = analysis.get("away_name", "")
        home = analysis.get("home_name", "")
        key = f"{away} @ {home}"
        game_id = game_id_map.get(key, "")

        if not game_id:
            continue

        sv = analysis.get("spread_value", {})
        tv = analysis.get("total_value", {})
        ml = analysis.get("ml_value", {})
        expected = analysis.get("expected", {})

        pick_team = sv.get("pick_team", "PASS")
        ml_pick_raw = ml.get("ml_pick")

        # Skip games with no actionable picks
        has_spread = pick_team in ("AWAY", "HOME")
        has_ml = ml_pick_raw in ("AWAY_ML", "HOME_ML")

        if not (has_spread or has_ml):
            continue

        # Top-play tagging: quality thresholds per bet type
        top_play_spread = has_spread and sv.get("hit_pct", 0) >= 59
        top_play_ml = has_ml and ml.get("hit_pct", 0) >= 59

        # Only save games with at least one top pick
        if not (top_play_spread or top_play_ml):
            continue

        # Determine ML pick team name and odds
        ml_team = None
        ml_odds = None
        if ml_pick_raw == "AWAY_ML":
            ml_team = away
            ml_odds = ml.get("away_ml")
        elif ml_pick_raw == "HOME_ML":
            ml_team = home
            ml_odds = ml.get("home_ml")

        pick = {
            "game_id": game_id,
            "date": today,
            "away_team": away,
            "home_team": home,
            "spread_pick": pick_team if has_spread else None,
            "spread_line": sv.get("actual_spread"),
            "spread_edge": round(sv.get("value_points", 0), 1) if has_spread else None,
            "spread_grade": sv.get("grade", "") if has_spread else None,
            "spread_hit_pct": round(sv.get("hit_pct", 0)) if has_spread else None,
            "ml_pick": ml_team,
            "ml_odds": ml_odds,
            "ml_grade": ml.get("grade", "") if has_ml else None,
            "ml_hit_pct": round(ml.get("hit_pct", 0)) if has_ml else None,
            "result": None,
            "spread_correct": None,
            "ml_correct": None,
            "actual_away_score": None,
            "actual_home_score": None,
            "top_play_spread": top_play_spread,
            "top_play_ml": top_play_ml,
        }

        data["picks"].append(pick)
        added += 1

    if added > 0:
        save_picks(data)
        print(f"Pick tracker: saved {added} picks for {today}")
    else:
        print(f"Pick tracker: no new picks to save for {today}")


def fetch_espn_scores(date_str: str) -> dict:
    """Fetch final scores from ESPN for a given date. Returns dict keyed by game_id."""
    compact = date_str.replace("-", "")
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    params = {"dates": compact}

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Pick tracker: ESPN fetch error for {date_str}: {e}")
        return {}

    results = {}
    for event in data.get("events", []):
        game_id = event.get("id", "")
        competition = event.get("competitions", [{}])[0]
        competitors = competition.get("competitors", [])
        status = event.get("status", {}).get("type", {}).get("name", "")

        if status != "STATUS_FINAL" or len(competitors) < 2:
            continue

        home_comp = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away_comp = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

        home_score = int(home_comp.get("score", 0))
        away_score = int(away_comp.get("score", 0))

        results[game_id] = {
            "away_score": away_score,
            "home_score": home_score,
            "total": away_score + home_score,
            "margin": away_score - home_score,  # positive = away won
        }

    return results


def update_results():
    """Check pending picks and update with actual results from ESPN."""
    data = load_picks()

    # Find dates with pending results
    pending_dates = set()
    for pick in data["picks"]:
        if pick.get("result") is None:
            pending_dates.add(pick["date"])

    if not pending_dates:
        print("Pick tracker: no pending results to update")
        return 0

    updated = 0
    for date_str in sorted(pending_dates):
        # Don't try to update today's games (not finished yet)
        if date_str == date.today().isoformat():
            continue

        scores = fetch_espn_scores(date_str)
        if not scores:
            continue

        for pick in data["picks"]:
            if pick["date"] != date_str or pick.get("result") is not None:
                continue

            score = scores.get(pick["game_id"])
            if not score:
                continue

            pick["actual_away_score"] = score["away_score"]
            pick["actual_home_score"] = score["home_score"]
            pick["result"] = "final"

            actual_margin = score["margin"]  # away - home
            actual_total = score["total"]

            # Spread check
            if pick.get("spread_pick") and pick.get("spread_line") is not None:
                line = pick["spread_line"]  # away team's spread
                if pick["spread_pick"] == "AWAY":
                    # Away covers if actual_margin + line > 0
                    cover = actual_margin + line
                    pick["spread_correct"] = cover > 0
                elif pick["spread_pick"] == "HOME":
                    # Home covers if -(actual_margin + line) > 0
                    cover = -(actual_margin + line)
                    pick["spread_correct"] = cover > 0

            # ML check
            if pick.get("ml_pick"):
                winner = pick["away_team"] if actual_margin > 0 else pick["home_team"]
                pick["ml_correct"] = pick["ml_pick"] == winner

            updated += 1

    if updated > 0:
        save_picks(data)
        print(f"Pick tracker: updated results for {updated} picks")

    return updated


def seed_from_backtest():
    """Seed picks history from backtest results (one-time migration)."""
    backtest_file = DATA_DIR / "nba_backtest_results.json"
    if not backtest_file.exists():
        print("Pick tracker: no backtest file to seed from")
        return

    data = load_picks()
    existing_keys = {(p["date"], p["away_team"], p["home_team"]) for p in data["picks"]}

    with open(backtest_file) as f:
        backtest = json.load(f)

    added = 0
    for bp in backtest.get("picks", []):
        key = (bp["date"], bp["away_team"], bp["home_team"])
        if key in existing_keys:
            continue

        pick = {
            "game_id": f"bt_{bp['date']}_{bp['away_team'][:3]}_{bp['home_team'][:3]}",
            "date": bp["date"],
            "away_team": bp["away_team"],
            "home_team": bp["home_team"],
            "actual_away_score": bp.get("actual_away_score"),
            "actual_home_score": bp.get("actual_home_score"),
            "result": "final",
        }

        # Spread pick
        if bp.get("spread_pick"):
            pick["spread_pick"] = bp["spread_pick"]
            pick["spread_line"] = bp.get("closing_spread")
            pick["spread_edge"] = bp.get("edge")
            pick["spread_correct"] = bp.get("spread_result") == "WIN"
            pick["spread_grade"] = None
            pick["spread_hit_pct"] = None

        # ML pick
        if bp.get("ml_pick"):
            pick["ml_pick"] = bp["ml_pick"]
            pick["ml_odds"] = None
            pick["ml_correct"] = bp.get("ml_result") == "WIN"
            pick["ml_grade"] = None
            pick["ml_hit_pct"] = None

        # Total pick
        if bp.get("total_pick"):
            pick["total_pick"] = bp["total_pick"]
            pick["total_line"] = bp.get("closing_total")
            pick["total_model"] = bp.get("predicted_total")
            pick["total_correct"] = bp.get("total_result") == "WIN"

        data["picks"].append(pick)
        existing_keys.add(key)
        added += 1

    if added > 0:
        save_picks(data)
        print(f"Pick tracker: seeded {added} picks from backtest")
    else:
        print("Pick tracker: backtest already seeded")


if __name__ == "__main__":
    seed_from_backtest()
    update_results()
    data = load_picks()
    total = len(data["picks"])
    resolved = sum(1 for p in data["picks"] if p.get("result") is not None)
    print(f"\nPick tracker: {total} total picks, {resolved} resolved, {total - resolved} pending")
