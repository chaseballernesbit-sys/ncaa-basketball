#!/usr/bin/env python3
"""
NCAA Basketball Data Scraper - Enhanced Version
Scrapes team stats, schedules, and betting odds from multiple sources.

Data Sources:
- ESPN API: Schedules, scores, team info (FREE, reliable)
- The Odds API: Betting lines from multiple sportsbooks (FREE 500 req/month)
- BartTorvik: Advanced metrics - T-Rank, Four Factors (FREE, may need Selenium)
- Sports-Reference: Additional stats (FREE, rate limited 20 req/min)
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re
import sys
import os

# Add project directory to path for imports
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from config import (
    DATA_DIR, LOGS_DIR, ODDS_API_KEY,
    REQUEST_DELAY, USER_AGENT, LINE_HISTORY_DIR
)
from team_mappings import normalize_team_name, get_conference_multiplier

# KenPom import folder
KENPOM_DIR = PROJECT_DIR / "kenpom"
KENPOM_DIR.mkdir(exist_ok=True)

# Configure logging
log_file = LOGS_DIR / f"scraper_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class NCAADataScraper:
    """Enhanced NCAA Basketball Data Scraper with multiple sources"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
        self.today = datetime.now().strftime('%Y-%m-%d')
        self.today_yyyymmdd = datetime.now().strftime('%Y%m%d')
        self.line_history_file = LINE_HISTORY_DIR / f"lines_{self.today_yyyymmdd}.json"

    # =========================================================================
    # LINE MOVEMENT TRACKING
    # =========================================================================

    def load_line_history(self) -> Dict:
        """Load existing line history for today"""
        if self.line_history_file.exists():
            try:
                with open(self.line_history_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.debug(f"Error loading line history: {e}")
        return {"games": {}, "snapshots": []}

    def save_line_history(self, history: Dict):
        """Save line history to file"""
        try:
            with open(self.line_history_file, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving line history: {e}")

    def update_line_history(self, odds_data: Dict[str, Dict]) -> Dict:
        """
        Update line history with current odds snapshot.
        Returns history with opening lines and movement data.
        """
        history = self.load_line_history()
        current_time = datetime.now().strftime('%H:%M')

        # Record this snapshot
        snapshot = {
            "time": current_time,
            "timestamp": datetime.now().isoformat(),
        }
        history["snapshots"].append(snapshot)

        for game_key, odds in odds_data.items():
            consensus = odds.get("consensus", {})
            current_spread = consensus.get("spread")
            current_total = consensus.get("total")

            if game_key not in history["games"]:
                # First time seeing this game - this is our "opening" line
                history["games"][game_key] = {
                    "opening_spread": current_spread,
                    "opening_total": current_total,
                    "opening_time": current_time,
                    "current_spread": current_spread,
                    "current_total": current_total,
                    "last_updated": current_time,
                    "spread_history": [{
                        "time": current_time,
                        "spread": current_spread
                    }] if current_spread else [],
                    "total_history": [{
                        "time": current_time,
                        "total": current_total
                    }] if current_total else [],
                }
            else:
                # Update existing game
                game_history = history["games"][game_key]

                # Update current values
                if current_spread is not None:
                    game_history["current_spread"] = current_spread
                    game_history["spread_history"].append({
                        "time": current_time,
                        "spread": current_spread
                    })

                if current_total is not None:
                    game_history["current_total"] = current_total
                    game_history["total_history"].append({
                        "time": current_time,
                        "total": current_total
                    })

                game_history["last_updated"] = current_time

        self.save_line_history(history)
        logger.info(f"Line history updated - tracking {len(history['games'])} games, {len(history['snapshots'])} snapshots today")

        return history

    def calculate_line_movement(self, history: Dict) -> Dict[str, Dict]:
        """
        Calculate line movement for each game.
        Returns movement data with signals for sharp action.
        """
        movement = {}

        for game_key, game_data in history.get("games", {}).items():
            opening_spread = game_data.get("opening_spread")
            current_spread = game_data.get("current_spread")
            opening_total = game_data.get("opening_total")
            current_total = game_data.get("current_total")

            spread_move = None
            total_move = None
            signals = []

            # Calculate spread movement
            if opening_spread is not None and current_spread is not None:
                spread_move = round(current_spread - opening_spread, 1)

                # Significant movement signals
                if abs(spread_move) >= 2.5:
                    direction = "toward favorite" if spread_move < 0 else "toward underdog"
                    signals.append(f"SHARP: Spread moved {abs(spread_move)} pts {direction}")
                elif abs(spread_move) >= 1.5:
                    direction = "toward favorite" if spread_move < 0 else "toward underdog"
                    signals.append(f"Notable spread movement ({abs(spread_move)} pts {direction})")

            # Calculate total movement
            if opening_total is not None and current_total is not None:
                total_move = round(current_total - opening_total, 1)

                if abs(total_move) >= 3:
                    direction = "up" if total_move > 0 else "down"
                    signals.append(f"SHARP: Total moved {abs(total_move)} pts {direction}")
                elif abs(total_move) >= 2:
                    direction = "up" if total_move > 0 else "down"
                    signals.append(f"Notable total movement ({abs(total_move)} pts {direction})")

            movement[game_key] = {
                "opening_spread": opening_spread,
                "current_spread": current_spread,
                "spread_movement": spread_move,
                "opening_total": opening_total,
                "current_total": current_total,
                "total_movement": total_move,
                "opening_time": game_data.get("opening_time"),
                "snapshots_count": len(game_data.get("spread_history", [])),
                "signals": signals,
                "has_sharp_action": any("SHARP" in s for s in signals),
            }

        return movement

    def _rate_limit(self, seconds: float = None):
        """Sleep to respect rate limits"""
        time.sleep(seconds or REQUEST_DELAY)

    def _safe_float(self, value: str) -> Optional[float]:
        """Safely convert string to float"""
        try:
            clean = str(value).strip().replace('%', '').replace(',', '')
            return float(clean) if clean and clean not in ['-', '', 'None'] else None
        except (ValueError, TypeError):
            return None

    def _safe_int(self, value: str) -> Optional[int]:
        """Safely convert string to int"""
        try:
            clean = str(value).strip().replace(',', '')
            return int(float(clean)) if clean and clean not in ['-', '', 'None'] else None
        except (ValueError, TypeError):
            return None

    # =========================================================================
    # INJURIES - Scrape from ESPN
    # =========================================================================

    def scrape_espn_injuries(self, team_id: str) -> List[Dict]:
        """Scrape injury report for a team from ESPN, including player PPG when available"""
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{team_id}"
            response = self.session.get(url, timeout=15)

            if response.status_code != 200:
                return []

            data = response.json()
            injuries = []

            # ESPN sometimes includes injuries in team data
            team_data = data.get('team', {})

            # Check for injuries in the athletes section if available
            for athlete in team_data.get('athletes', []):
                injury_status = athlete.get('injuries', [])
                if injury_status:
                    player_name = athlete.get('displayName', 'Unknown')

                    # Try to get player PPG from stats
                    ppg = None
                    try:
                        stats = athlete.get('statistics', [])
                        if stats and isinstance(stats, list):
                            for stat in stats:
                                if stat.get('abbreviation') == 'PTS':
                                    ppg = float(stat.get('displayValue', 0))
                                    break
                        # Also check different stat format
                        if ppg is None:
                            stat_summary = athlete.get('statsSummary', {})
                            if stat_summary.get('displayValue'):
                                # Format is often "X.X PPG, Y.Y RPG"
                                parts = stat_summary.get('displayValue', '').split(',')
                                for part in parts:
                                    if 'PPG' in part:
                                        ppg = float(part.replace('PPG', '').strip())
                                        break
                    except:
                        pass

                    for injury in injury_status:
                        inj_data = {
                            'player': player_name,
                            'position': athlete.get('position', {}).get('abbreviation', ''),
                            'status': injury.get('status', 'Unknown'),
                            'type': injury.get('type', {}).get('description', ''),
                            'detail': injury.get('details', {}).get('detail', ''),
                        }
                        if ppg is not None:
                            inj_data['ppg'] = round(ppg, 1)
                        injuries.append(inj_data)

            return injuries

        except Exception as e:
            logger.debug(f"Error fetching injuries for team {team_id}: {e}")
            return []

    def scrape_team_schedule(self, team_id: str, limit: int = 15) -> List[Dict]:
        """Get recent and upcoming games for a team"""
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{team_id}/schedule"
            response = self.session.get(url, timeout=15)

            if response.status_code != 200:
                return []

            data = response.json()
            games = []

            for event in data.get('events', [])[-limit:]:
                competition = event.get('competitions', [{}])[0]
                competitors = competition.get('competitors', [])

                game_date = event.get('date', '')

                # Determine if home or away
                is_home = False
                opponent = None
                team_score = None
                opp_score = None

                for comp in competitors:
                    if str(comp.get('id')) == str(team_id):
                        is_home = comp.get('homeAway') == 'home'
                        score_data = comp.get('score')
                        if isinstance(score_data, dict):
                            team_score = score_data.get('value')
                        elif score_data is not None:
                            team_score = score_data
                    else:
                        opponent = comp.get('team', {}).get('displayName', 'Unknown')
                        score_data = comp.get('score')
                        if isinstance(score_data, dict):
                            opp_score = score_data.get('value')
                        elif score_data is not None:
                            opp_score = score_data

                # Determine result based on scores (completed games have scores)
                result = None
                is_completed = team_score is not None and opp_score is not None
                if is_completed:
                    try:
                        result = 'W' if float(team_score) > float(opp_score) else 'L'
                    except:
                        pass

                games.append({
                    'date': game_date,
                    'opponent': opponent,
                    'is_home': is_home,
                    'status': 'STATUS_FINAL' if is_completed else 'SCHEDULED',
                    'team_score': team_score,
                    'opp_score': opp_score,
                    'result': result,
                })

            return games

        except Exception as e:
            logger.debug(f"Error fetching schedule for team {team_id}: {e}")
            return []

    def calculate_recent_form(self, schedule: List[Dict]) -> Dict:
        """Calculate recent form metrics from schedule"""
        # Filter to completed games only
        completed = [g for g in schedule if g.get('result')]

        if not completed:
            return {'last_10_record': 'N/A', 'streak': 0, 'form_adjustment': 0}

        # Last 10 games
        last_10 = completed[-10:] if len(completed) >= 10 else completed
        wins_last_10 = sum(1 for g in last_10 if g['result'] == 'W')
        losses_last_10 = len(last_10) - wins_last_10

        # Current streak
        streak = 0
        if completed:
            streak_type = completed[-1]['result']
            for game in reversed(completed):
                if game['result'] == streak_type:
                    streak += 1 if streak_type == 'W' else -1
                else:
                    break

        # Last 5 for cold streak detection
        last_5 = completed[-5:] if len(completed) >= 5 else completed
        losses_last_5 = sum(1 for g in last_5 if g['result'] == 'L')

        # Calculate form adjustment
        form_adj = 0
        if wins_last_10 >= 9:
            form_adj = 3.0  # Very hot
        elif wins_last_10 >= 7:
            form_adj = 2.0  # Hot
        elif losses_last_5 >= 4:
            form_adj = -2.5  # Very cold
        elif losses_last_5 >= 3:
            form_adj = -1.5  # Cold

        return {
            'last_10_record': f"{wins_last_10}-{losses_last_10}",
            'last_10_wins': wins_last_10,
            'last_5_losses': losses_last_5,
            'streak': streak,
            'form_adjustment': form_adj,
        }

    def calculate_rest_days(self, schedule: List[Dict], game_date: str) -> Dict:
        """Calculate days of rest before a game"""
        from datetime import datetime

        try:
            target_date = datetime.fromisoformat(game_date.replace('Z', '+00:00'))
        except:
            return {'rest_days': None, 'fatigue_adjustment': 0}

        # Find most recent completed game before target date
        completed = [g for g in schedule if g.get('status') == 'STATUS_FINAL']

        last_game_date = None
        games_in_last_7 = 0

        for game in completed:
            try:
                game_dt = datetime.fromisoformat(game['date'].replace('Z', '+00:00'))
                if game_dt < target_date:
                    if last_game_date is None or game_dt > last_game_date:
                        last_game_date = game_dt

                    # Count games in last 7 days
                    days_ago = (target_date - game_dt).days
                    if days_ago <= 7:
                        games_in_last_7 += 1
            except:
                continue

        if last_game_date is None:
            return {'rest_days': None, 'fatigue_adjustment': 0, 'games_last_7_days': 0}

        rest_days = (target_date - last_game_date).days

        # Calculate fatigue adjustment
        fatigue_adj = 0
        if rest_days == 1:
            fatigue_adj = -2.5  # Back to back
        elif rest_days == 2 and games_in_last_7 >= 3:
            fatigue_adj = -2.0  # 3 in 5 days
        elif games_in_last_7 >= 4:
            fatigue_adj = -3.0  # 4 in 7 days

        return {
            'rest_days': rest_days,
            'games_last_7_days': games_in_last_7,
            'fatigue_adjustment': fatigue_adj,
            'is_back_to_back': rest_days == 1,
        }

    # =========================================================================
    # KENPOM CSV IMPORT (User downloads from kenpom.com)
    # =========================================================================

    def import_kenpom_csv(self) -> Dict[str, Dict]:
        """
        Import efficiency data from CSV file (KenPom or BartTorvik format).

        User downloads CSV and places in /kenpom folder.
        Script automatically finds the most recent CSV file.

        Supports both KenPom and BartTorvik CSV exports.
        """
        import csv

        # Find the most recent CSV in kenpom folder
        csv_files = list(KENPOM_DIR.glob("*.csv"))

        if not csv_files:
            logger.info("No efficiency CSV found in /kenpom folder. To use KenPom/BartTorvik data:")
            logger.info("  1. Go to kenpom.com or barttorvik.com")
            logger.info("  2. Export/download the CSV")
            logger.info("  3. Save it to: /Users/mac/Documents/ncaa-basketball/kenpom/")
            return {}

        # Get the most recently modified CSV
        latest_csv = max(csv_files, key=lambda f: f.stat().st_mtime)
        file_age_hours = (time.time() - latest_csv.stat().st_mtime) / 3600

        logger.info(f"Loading efficiency data from: {latest_csv.name}")
        if file_age_hours > 24:
            logger.warning(f"  ⚠️  CSV is {file_age_hours:.0f} hours old. Consider updating.")
        else:
            logger.info(f"  ✓ CSV is {file_age_hours:.1f} hours old")

        teams = {}

        try:
            with open(latest_csv, 'r', encoding='utf-8-sig') as f:
                # Try to detect the CSV format
                sample = f.read(2000)
                f.seek(0)

                # Detect delimiter (comma or tab)
                delimiter = '\t' if '\t' in sample else ','

                reader = csv.DictReader(f, delimiter=delimiter)

                # Map various possible column names to our standard names
                # Supports both KenPom and BartTorvik formats
                column_maps = {
                    'team': ['Team', 'team', 'TeamName', 'School'],
                    'rank': ['Rk', 'Rank', 'rk', 'rank'],
                    'conf': ['Conf', 'Conference', 'conf'],
                    'record': ['W-L', 'Record', 'W/L', 'Rec'],
                    # Efficiency metrics
                    'adj_em': ['AdjEM', 'AdjNEM', 'NetRtg', 'adjEM', 'Adj EM'],
                    'adj_oe': ['AdjO', 'AdjOE', 'ORtg', 'adjO', 'Adj O'],
                    'adj_oe_rank': ['AdjO_Rank', 'ORtg_Rank', 'OE_Rank'],
                    'adj_de': ['AdjD', 'AdjDE', 'DRtg', 'adjD', 'Adj D'],
                    'adj_de_rank': ['AdjD_Rank', 'DRtg_Rank', 'DE_Rank'],
                    'adj_tempo': ['AdjT', 'AdjTempo', 'Tempo', 'adjT', 'Adj T'],
                    'adj_tempo_rank': ['AdjT_Rank', 'Tempo_Rank'],
                    # Luck and SOS
                    'luck': ['Luck', 'luck'],
                    'luck_rank': ['Luck_Rank'],
                    'sos': ['SOS AdjEM', 'SOS_AdjEM', 'SOS', 'sos', 'SOS_NetRtg', 'Strength of Schedule'],
                    'sos_rank': ['SOS_Rank', 'SOS Rank'],
                    'sos_oe': ['SOS_ORtg', 'SOS_OppO', 'SOS OppO', 'OppO', 'SOS_O'],
                    'sos_oe_rank': ['SOS_ORtg_Rank', 'SOS_OppO_Rank', 'SOS OppO Rank'],
                    'sos_de': ['SOS_DRtg', 'SOS_OppD', 'SOS OppD', 'OppD', 'SOS_D'],
                    'sos_de_rank': ['SOS_DRtg_Rank', 'SOS_OppD_Rank', 'SOS OppD Rank'],
                    'ncsos': ['NCSOS', 'NCSOS_AdjEM', 'NC SOS AdjEM', 'NC_SOS'],
                    'ncsos_rank': ['NCSOS_Rank', 'NCSOS Rank'],
                    # Four Factors (if available)
                    'efg_o': ['eFG%', 'EFG_O', 'eFG_O', 'EFG%O'],
                    'efg_d': ['eFG%D', 'EFG_D', 'eFG_D', 'Opp eFG%'],
                    'tov_o': ['TOV%', 'TO%', 'TO_O'],
                    'tov_d': ['Opp TOV%', 'TO%D', 'TO_D'],
                    'orb': ['ORB%', 'OR%', 'ORB'],
                    'drb': ['DRB%', 'DR%', 'DRB'],
                    'ftr': ['FTR', 'FT Rate', 'FT_Rate'],
                    'ftrd': ['FTRD', 'Opp FTR', 'Opp FT Rate'],
                }

                def get_col(row, key):
                    """Get value from row using multiple possible column names"""
                    for col_name in column_maps.get(key, []):
                        if col_name in row and row[col_name]:
                            return row[col_name]
                    return None

                for row in reader:
                    try:
                        team_name = get_col(row, 'team')
                        if not team_name:
                            continue

                        # Clean team name (remove seed numbers, asterisks, etc.)
                        team_name = re.sub(r'^\d+\s*', '', str(team_name))  # Remove leading numbers
                        team_name = team_name.replace('*', '').strip()
                        team_name = normalize_team_name(team_name)

                        if not team_name:
                            continue

                        teams[team_name] = {
                            # Core rankings
                            'kenpom_rank': self._safe_int(get_col(row, 'rank')),
                            'conference': get_col(row, 'conf') or '',
                            'record': get_col(row, 'record') or '',

                            # Efficiency metrics (THE KEY STATS)
                            'adj_em': self._safe_float(get_col(row, 'adj_em')),
                            'adj_oe': self._safe_float(get_col(row, 'adj_oe')),
                            'adj_oe_rank': self._safe_int(get_col(row, 'adj_oe_rank')),
                            'adj_de': self._safe_float(get_col(row, 'adj_de')),
                            'adj_de_rank': self._safe_int(get_col(row, 'adj_de_rank')),
                            'adj_tempo': self._safe_float(get_col(row, 'adj_tempo')),
                            'adj_tempo_rank': self._safe_int(get_col(row, 'adj_tempo_rank')),

                            # Luck factor (important for regression)
                            'luck': self._safe_float(get_col(row, 'luck')),
                            'luck_rank': self._safe_int(get_col(row, 'luck_rank')),

                            # Strength of Schedule (crucial for mid-majors)
                            'sos': self._safe_float(get_col(row, 'sos')),
                            'sos_rank': self._safe_int(get_col(row, 'sos_rank')),
                            'sos_oe': self._safe_float(get_col(row, 'sos_oe')),
                            'sos_oe_rank': self._safe_int(get_col(row, 'sos_oe_rank')),
                            'sos_de': self._safe_float(get_col(row, 'sos_de')),
                            'sos_de_rank': self._safe_int(get_col(row, 'sos_de_rank')),
                            'ncsos': self._safe_float(get_col(row, 'ncsos')),
                            'ncsos_rank': self._safe_int(get_col(row, 'ncsos_rank')),

                            # Four Factors (if available in export)
                            'efg_o': self._safe_float(get_col(row, 'efg_o')),
                            'efg_d': self._safe_float(get_col(row, 'efg_d')),
                            'tov_o': self._safe_float(get_col(row, 'tov_o')),
                            'tov_d': self._safe_float(get_col(row, 'tov_d')),
                            'orb': self._safe_float(get_col(row, 'orb')),
                            'drb': self._safe_float(get_col(row, 'drb')),
                            'ftr': self._safe_float(get_col(row, 'ftr')),
                            'ftrd': self._safe_float(get_col(row, 'ftrd')),

                            'source': 'kenpom'
                        }

                    except Exception as e:
                        logger.debug(f"Error parsing row: {e}")
                        continue

            logger.info(f"✓ Loaded {len(teams)} teams from CSV")
            return teams

        except Exception as e:
            logger.error(f"Error reading CSV: {e}")
            return {}

    # =========================================================================
    # ESPN API - Schedules and Scores (FREE, NO AUTH, RELIABLE)
    # =========================================================================

    def scrape_espn_schedule(self, date_str: str = None) -> List[Dict]:
        """
        Scrape today's games from ESPN's hidden API.

        Args:
            date_str: Date in YYYYMMDD format. Defaults to today.

        Returns:
            List of game dictionaries with teams, times, venues
        """
        if date_str is None:
            date_str = self.today_yyyymmdd

        url = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
        params = {
            "dates": date_str,
            "groups": 50,  # All Division I games
            "limit": 400   # Get all games
        }

        logger.info(f"Fetching ESPN schedule for {date_str}")

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            games = []
            for event in data.get("events", []):
                competition = event.get("competitions", [{}])[0]
                competitors = competition.get("competitors", [])

                if len(competitors) != 2:
                    continue

                # ESPN lists home team second
                away_team = None
                home_team = None
                for comp in competitors:
                    if comp.get("homeAway") == "away":
                        away_team = comp
                    else:
                        home_team = comp

                if not away_team or not home_team:
                    continue

                # Skip finished games
                status = event.get("status", {}).get("type", {}).get("name", "STATUS_SCHEDULED")
                if status in ["STATUS_FINAL", "STATUS_FINAL_OT"]:
                    continue

                # Get ESPN odds if available
                odds_data = competition.get("odds", [{}])[0] if competition.get("odds") else {}
                espn_spread = odds_data.get("details", "")
                espn_total = odds_data.get("overUnder")

                game = {
                    "game_id": event.get("id"),
                    "name": event.get("name", ""),
                    "date": event.get("date"),
                    "status": status,
                    "venue": competition.get("venue", {}).get("fullName", ""),
                    "neutral_site": competition.get("neutralSite", False),
                    "conference_game": competition.get("conferenceCompetition", False),
                    "broadcast": "",
                    "away": {
                        "name": normalize_team_name(away_team.get("team", {}).get("displayName", "")),
                        "abbreviation": away_team.get("team", {}).get("abbreviation", ""),
                        "espn_id": away_team.get("team", {}).get("id"),
                        "rank": away_team.get("curatedRank", {}).get("current"),
                        "record": away_team.get("records", [{}])[0].get("summary", "") if away_team.get("records") else "",
                        "score": int(away_team.get("score", 0)) if away_team.get("score") else None,
                    },
                    "home": {
                        "name": normalize_team_name(home_team.get("team", {}).get("displayName", "")),
                        "abbreviation": home_team.get("team", {}).get("abbreviation", ""),
                        "espn_id": home_team.get("team", {}).get("id"),
                        "rank": home_team.get("curatedRank", {}).get("current"),
                        "record": home_team.get("records", [{}])[0].get("summary", "") if home_team.get("records") else "",
                        "score": int(home_team.get("score", 0)) if home_team.get("score") else None,
                    },
                    "espn_odds": {
                        "spread_details": espn_spread,
                        "total": self._safe_float(espn_total),
                    },
                    "odds": None  # Will be filled by The Odds API
                }

                # Try to get broadcast info
                broadcasts = competition.get("broadcasts", [])
                if broadcasts:
                    game["broadcast"] = broadcasts[0].get("names", [""])[0] if broadcasts[0].get("names") else ""

                games.append(game)

            logger.info(f"Found {len(games)} games from ESPN")
            return games

        except requests.RequestException as e:
            logger.error(f"ESPN API error: {e}")
            return []

    def scrape_espn_team_stats(self, team_id: str) -> Dict:
        """Get team stats from ESPN API and calculate advanced metrics"""
        try:
            # Get both statistics AND team info (for defensive PPG)
            stats_url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{team_id}/statistics"
            team_url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{team_id}"

            stats_response = self.session.get(stats_url, timeout=30)
            team_response = self.session.get(team_url, timeout=30)

            if stats_response.status_code != 200:
                return {}

            data = stats_response.json()
            raw_stats = {}

            # Navigate ESPN's actual structure: results.stats.categories
            for category in data.get("results", {}).get("stats", {}).get("categories", []):
                cat_name = category.get("name", "")
                for stat in category.get("stats", []):
                    name = stat.get("name", "")
                    value = stat.get("value")
                    raw_stats[name] = value

            # Get defensive PPG from team endpoint
            ppg_allowed = 70.0  # Default
            if team_response.status_code == 200:
                team_data = team_response.json()
                record_items = team_data.get('team', {}).get('record', {}).get('items', [])
                for item in record_items:
                    if item.get('type') == 'total':
                        for stat in item.get('stats', []):
                            if stat.get('name') == 'avgPointsAgainst':
                                ppg_allowed = stat.get('value', 70.0)
                                break

            # Calculate advanced metrics from raw stats
            stats = {}

            # Basic stats
            stats['games'] = raw_stats.get('gamesPlayed', 0)
            stats['pts_per_game'] = raw_stats.get('avgPoints', 0)
            stats['pts_allowed_per_game'] = ppg_allowed

            # Shooting stats
            fga = raw_stats.get('avgFieldGoalsAttempted', 60)
            fgm = raw_stats.get('avgFieldGoalsMade', 25)
            fg3a = raw_stats.get('avgThreePointFieldGoalsAttempted', 20)
            fg3m = raw_stats.get('avgThreePointFieldGoalsMade', 7)
            fta = raw_stats.get('avgFreeThrowsAttempted', 20)
            ftm = raw_stats.get('avgFreeThrowsMade', 14)

            stats['fg_pct'] = raw_stats.get('fieldGoalPct', 45)
            stats['fg3_pct'] = raw_stats.get('threePointFieldGoalPct', 33)
            stats['ft_pct'] = raw_stats.get('freeThrowPct', 70)

            # Calculate eFG% = (FGM + 0.5 * 3PM) / FGA
            if fga > 0:
                stats['efg_o'] = round(((fgm + 0.5 * fg3m) / fga) * 100, 1)
            else:
                stats['efg_o'] = 50.0

            # Turnovers and assists
            tov = raw_stats.get('avgTurnovers', 13)
            ast = raw_stats.get('avgAssists', 14)

            # Calculate possessions (per game) = FGA + 0.475*FTA + TOV - ORB
            orb = raw_stats.get('avgOffensiveRebounds', 10)
            possessions = fga + 0.475 * fta + tov - orb
            possessions = max(possessions, 60)  # Floor

            stats['adj_tempo'] = round(possessions, 1)

            # Calculate TOV% = TOV / (FGA + 0.44*FTA + TOV) * 100
            tov_denominator = fga + 0.44 * fta + tov
            if tov_denominator > 0:
                stats['tov_o'] = round((tov / tov_denominator) * 100, 1)
            else:
                stats['tov_o'] = 15.0

            # Calculate ORB%
            drb = raw_stats.get('avgDefensiveRebounds', 25)
            total_reb = orb + drb
            if total_reb > 0:
                stats['orb'] = round((orb / total_reb) * 100, 1)
                stats['drb'] = round((drb / total_reb) * 100, 1)
            else:
                stats['orb'] = 30.0
                stats['drb'] = 70.0

            # Calculate FTR = FTA / FGA * 100
            if fga > 0:
                stats['ftr'] = round((fta / fga) * 100, 1)
            else:
                stats['ftr'] = 30.0

            # Calculate offensive efficiency (points per 100 possessions)
            ppg = raw_stats.get('avgPoints', 70)
            if possessions > 0:
                stats['adj_oe'] = round((ppg / possessions) * 100, 1)
            else:
                stats['adj_oe'] = 100.0

            # Store raw defensive stats
            stats['steals_per_game'] = raw_stats.get('avgSteals', 6)
            stats['blocks_per_game'] = raw_stats.get('avgBlocks', 3)

            # Calculate DEFENSIVE EFFICIENCY from points allowed
            # adj_de = (PPG Allowed / Possessions) * 100
            if possessions > 0:
                stats['adj_de'] = round((ppg_allowed / possessions) * 100, 1)
            else:
                stats['adj_de'] = 100.0

            # Estimate defensive eFG% from PPG allowed
            # Average D1 team allows ~72 PPG with ~50% eFG against
            # Scale based on points allowed relative to average
            avg_ppg_allowed = 72.0
            efg_adjustment = (ppg_allowed - avg_ppg_allowed) / avg_ppg_allowed * 10
            stats['efg_d'] = round(50.0 + efg_adjustment, 1)
            stats['efg_d'] = max(42.0, min(58.0, stats['efg_d']))  # Clamp to reasonable range

            # Estimate defensive turnover forcing rate
            steals = raw_stats.get('avgSteals', 6)
            # More steals = force more turnovers
            stats['tov_d'] = round(15.0 + (steals - 6) * 0.8, 1)
            stats['tov_d'] = max(12.0, min(22.0, stats['tov_d']))

            # Estimate opponent FTR (fewer fouls = better defense usually)
            # Use blocks as proxy - more blocks often means more aggressive D
            blocks = raw_stats.get('avgBlocks', 3)
            stats['ftrd'] = round(30.0 + (blocks - 3) * 2.0, 1)
            stats['ftrd'] = max(22.0, min(40.0, stats['ftrd']))

            # Calculate AdjEM (Adjusted Efficiency Margin)
            stats['adj_em'] = round(stats['adj_oe'] - stats['adj_de'], 1)

            stats['source'] = 'espn'
            return stats

        except Exception as e:
            logger.debug(f"ESPN team stats error for {team_id}: {e}")
            return {}

    # =========================================================================
    # THE ODDS API - Betting Lines (FREE 500 requests/month)
    # =========================================================================

    def scrape_odds_api(self) -> Dict[str, Dict]:
        """
        Fetch current betting odds from The Odds API.

        Returns:
            Dictionary mapping game keys to odds data
        """
        if not ODDS_API_KEY:
            logger.warning("=" * 50)
            logger.warning("No ODDS_API_KEY set. Skipping odds fetch.")
            logger.warning("Get a FREE key at: https://the-odds-api.com/")
            logger.warning("Then set: export ODDS_API_KEY='your_key_here'")
            logger.warning("=" * 50)
            return {}

        url = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": "spreads,totals,h2h",
            "oddsFormat": "american",
            "bookmakers": "draftkings,fanduel,betmgm,caesars,pointsbetus,betrivers"
        }

        logger.info("Fetching odds from The Odds API")

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Check remaining requests
            remaining = response.headers.get('x-requests-remaining', 'unknown')
            used = response.headers.get('x-requests-used', 'unknown')
            logger.info(f"Odds API: {remaining} requests remaining ({used} used this month)")

            odds_by_game = {}
            for game in data:
                away_team = normalize_team_name(game.get("away_team", ""))
                home_team = normalize_team_name(game.get("home_team", ""))
                game_key = f"{away_team}@{home_team}"

                odds_data = {
                    "commence_time": game.get("commence_time"),
                    "bookmakers": {},
                    "consensus": {
                        "spread": None,
                        "total": None,
                    },
                    "best_odds": {
                        "away_spread": None,
                        "home_spread": None,
                        "over": None,
                        "under": None,
                        "away_ml": None,
                        "home_ml": None,
                    }
                }

                spreads_collected = []
                totals_collected = []

                for bookmaker in game.get("bookmakers", []):
                    book_name = bookmaker.get("title", "")
                    book_odds = {}

                    for market in bookmaker.get("markets", []):
                        market_key = market.get("key")
                        outcomes = market.get("outcomes", [])

                        if market_key == "spreads":
                            for outcome in outcomes:
                                team = normalize_team_name(outcome.get("name", ""))
                                spread = outcome.get("point")
                                price = outcome.get("price")

                                if spread is not None:
                                    spreads_collected.append(spread if team == away_team else -spread)

                                if team == away_team:
                                    book_odds["away_spread"] = spread
                                    book_odds["away_spread_price"] = price
                                elif team == home_team:
                                    book_odds["home_spread"] = spread
                                    book_odds["home_spread_price"] = price

                        elif market_key == "totals":
                            for outcome in outcomes:
                                point = outcome.get("point")
                                price = outcome.get("price")

                                if point is not None:
                                    totals_collected.append(point)

                                if outcome.get("name") == "Over":
                                    book_odds["over"] = point
                                    book_odds["over_price"] = price
                                else:
                                    book_odds["under"] = point
                                    book_odds["under_price"] = price

                        elif market_key == "h2h":
                            for outcome in outcomes:
                                team = normalize_team_name(outcome.get("name", ""))
                                price = outcome.get("price")
                                if team == away_team:
                                    book_odds["away_ml"] = price
                                elif team == home_team:
                                    book_odds["home_ml"] = price

                    odds_data["bookmakers"][book_name] = book_odds

                    # Track best odds
                    self._update_best_odds(odds_data, book_odds, book_name)

                # Calculate consensus lines
                if spreads_collected:
                    odds_data["consensus"]["spread"] = round(sum(spreads_collected) / len(spreads_collected), 1)
                if totals_collected:
                    odds_data["consensus"]["total"] = round(sum(totals_collected) / len(totals_collected), 1)

                odds_by_game[game_key] = odds_data

            logger.info(f"Found odds for {len(odds_by_game)} games")
            return odds_by_game

        except requests.RequestException as e:
            logger.error(f"Odds API error: {e}")
            return {}

    def _update_best_odds(self, odds_data: Dict, book_odds: Dict, book_name: str):
        """Track best available odds across books"""
        best = odds_data["best_odds"]

        # Best away spread (want highest/least negative number)
        if book_odds.get("away_spread") is not None:
            current = best["away_spread"]
            if current is None or book_odds["away_spread"] > current["spread"]:
                best["away_spread"] = {
                    "spread": book_odds["away_spread"],
                    "price": book_odds.get("away_spread_price"),
                    "book": book_name
                }

        # Best home spread
        if book_odds.get("home_spread") is not None:
            current = best["home_spread"]
            if current is None or book_odds["home_spread"] > current["spread"]:
                best["home_spread"] = {
                    "spread": book_odds["home_spread"],
                    "price": book_odds.get("home_spread_price"),
                    "book": book_name
                }

        # Best over (want lowest line)
        if book_odds.get("over") is not None:
            current = best["over"]
            if current is None or book_odds["over"] < current["total"]:
                best["over"] = {
                    "total": book_odds["over"],
                    "price": book_odds.get("over_price"),
                    "book": book_name
                }

        # Best under (want highest line)
        if book_odds.get("under") is not None:
            current = best["under"]
            if current is None or book_odds["under"] > current["total"]:
                best["under"] = {
                    "total": book_odds["under"],
                    "price": book_odds.get("under_price"),
                    "book": book_name
                }

        # Best moneylines (want highest price)
        if book_odds.get("away_ml") is not None:
            current = best["away_ml"]
            if current is None or book_odds["away_ml"] > current["price"]:
                best["away_ml"] = {"price": book_odds["away_ml"], "book": book_name}

        if book_odds.get("home_ml") is not None:
            current = best["home_ml"]
            if current is None or book_odds["home_ml"] > current["price"]:
                best["home_ml"] = {"price": book_odds["home_ml"], "book": book_name}

    # =========================================================================
    # BARTTORVIK - Advanced Metrics (Free, may need Selenium for Cloudflare)
    # =========================================================================

    def scrape_barttorvik(self) -> Dict[str, Dict]:
        """
        Scrape T-Rank ratings from BartTorvik.
        Try JSON endpoint first (faster), fall back to HTML scraping.
        """
        # Try the JSON API endpoint first (less likely to be blocked)
        json_url = "https://barttorvik.com/getadvstats.php"
        params = {
            "year": datetime.now().year,
            "csv": 1  # Request CSV format which is easier to parse
        }

        logger.info("Fetching BartTorvik T-Rank data (trying CSV endpoint)")

        try:
            response = self.session.get(json_url, params=params, timeout=30, headers={
                'User-Agent': USER_AGENT,
                'Accept': 'text/csv,text/plain,*/*',
                'Referer': 'https://barttorvik.com/'
            })

            if response.status_code == 200 and len(response.text) > 1000:
                # Parse CSV response
                teams = self._parse_barttorvik_csv(response.text)
                if teams:
                    logger.info(f"Scraped {len(teams)} teams from BartTorvik CSV")
                    return teams

        except Exception as e:
            logger.debug(f"BartTorvik CSV endpoint failed: {e}")

        # Fall back to HTML scraping
        url = "https://barttorvik.com/trank.php"
        params = {
            "year": datetime.now().year,
            "sort": "",
            "lastx": "0",
            "conlimit": "All",
        }

        logger.info("Trying BartTorvik HTML endpoint")

        try:
            response = self.session.get(url, params=params, timeout=30)

            # Check for Cloudflare block
            if "Verifying your browser" in response.text or response.status_code == 403:
                logger.warning("BartTorvik blocked by Cloudflare - trying Selenium fallback")
                return self._scrape_barttorvik_selenium()

            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            teams = {}
            table = soup.find('table', {'id': 'ratings-table'}) or soup.find('table')

            if not table:
                logger.warning("Could not find ratings table on BartTorvik")
                return {}

            rows = table.find_all('tr')[1:]  # Skip header
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 15:
                    continue

                try:
                    team_name = normalize_team_name(cols[1].get_text(strip=True))

                    teams[team_name] = {
                        "torvik_rank": self._safe_int(cols[0].get_text(strip=True)),
                        "conference": cols[2].get_text(strip=True),
                        "record": cols[3].get_text(strip=True),
                        "adj_oe": self._safe_float(cols[4].get_text(strip=True)),
                        "adj_de": self._safe_float(cols[5].get_text(strip=True)),
                        "barthag": self._safe_float(cols[6].get_text(strip=True)),
                        "adj_tempo": self._safe_float(cols[7].get_text(strip=True)),
                        "efg_o": self._safe_float(cols[8].get_text(strip=True)),
                        "efg_d": self._safe_float(cols[9].get_text(strip=True)),
                        "tov_o": self._safe_float(cols[10].get_text(strip=True)),
                        "tov_d": self._safe_float(cols[11].get_text(strip=True)),
                        "orb": self._safe_float(cols[12].get_text(strip=True)),
                        "drb": self._safe_float(cols[13].get_text(strip=True)),
                        "ftr": self._safe_float(cols[14].get_text(strip=True)),
                        "ftrd": self._safe_float(cols[15].get_text(strip=True)) if len(cols) > 15 else None,
                        "source": "barttorvik"
                    }

                    # Calculate AdjEM
                    if teams[team_name].get("adj_oe") and teams[team_name].get("adj_de"):
                        teams[team_name]["adj_em"] = round(
                            teams[team_name]["adj_oe"] - teams[team_name]["adj_de"], 2
                        )

                except (IndexError, ValueError) as e:
                    logger.debug(f"Error parsing BartTorvik row: {e}")
                    continue

            logger.info(f"Scraped {len(teams)} teams from BartTorvik")
            return teams

        except requests.RequestException as e:
            logger.error(f"BartTorvik error: {e}")
            return {}

    def _parse_barttorvik_csv(self, csv_text: str) -> Dict[str, Dict]:
        """Parse BartTorvik CSV response"""
        try:
            import csv
            from io import StringIO

            teams = {}
            reader = csv.DictReader(StringIO(csv_text))

            for row in reader:
                try:
                    team_name = normalize_team_name(row.get('team', row.get('Team', '')))
                    if not team_name:
                        continue

                    teams[team_name] = {
                        "torvik_rank": self._safe_int(row.get('rk', row.get('Rk', ''))),
                        "conference": row.get('conf', row.get('Conf', '')),
                        "record": row.get('rec', row.get('Rec', '')),
                        "adj_oe": self._safe_float(row.get('adjoe', row.get('AdjOE', ''))),
                        "adj_de": self._safe_float(row.get('adjde', row.get('AdjDE', ''))),
                        "barthag": self._safe_float(row.get('barthag', row.get('Barthag', ''))),
                        "adj_tempo": self._safe_float(row.get('adjt', row.get('AdjT', ''))),
                        "efg_o": self._safe_float(row.get('efgo', row.get('EFG%O', ''))),
                        "efg_d": self._safe_float(row.get('efgd', row.get('EFG%D', ''))),
                        "tov_o": self._safe_float(row.get('tovo', row.get('TO%O', ''))),
                        "tov_d": self._safe_float(row.get('tovd', row.get('TO%D', ''))),
                        "orb": self._safe_float(row.get('orb', row.get('ORB%', ''))),
                        "drb": self._safe_float(row.get('drb', row.get('DRB%', ''))),
                        "ftr": self._safe_float(row.get('ftr', row.get('FTR', ''))),
                        "ftrd": self._safe_float(row.get('ftrd', row.get('FTRD', ''))),
                        "source": "barttorvik"
                    }

                    # Calculate AdjEM
                    if teams[team_name].get("adj_oe") and teams[team_name].get("adj_de"):
                        teams[team_name]["adj_em"] = round(
                            teams[team_name]["adj_oe"] - teams[team_name]["adj_de"], 2
                        )

                except Exception as e:
                    logger.debug(f"Error parsing BartTorvik CSV row: {e}")
                    continue

            return teams

        except Exception as e:
            logger.debug(f"BartTorvik CSV parsing failed: {e}")
            return {}

    def _scrape_barttorvik_selenium(self) -> Dict[str, Dict]:
        """Selenium fallback for BartTorvik when Cloudflare blocks"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            logger.info("Attempting Selenium fallback for BartTorvik")

            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument(f"user-agent={USER_AGENT}")

            driver = webdriver.Chrome(options=options)
            driver.get("https://barttorvik.com/trank.php")

            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            driver.quit()

            teams = {}
            table = soup.find('table')
            if table:
                for row in table.find_all('tr')[1:]:
                    cols = row.find_all('td')
                    if len(cols) >= 15:
                        try:
                            team_name = normalize_team_name(cols[1].get_text(strip=True))
                            teams[team_name] = {
                                "torvik_rank": self._safe_int(cols[0].get_text(strip=True)),
                                "conference": cols[2].get_text(strip=True),
                                "record": cols[3].get_text(strip=True),
                                "adj_oe": self._safe_float(cols[4].get_text(strip=True)),
                                "adj_de": self._safe_float(cols[5].get_text(strip=True)),
                                "barthag": self._safe_float(cols[6].get_text(strip=True)),
                                "adj_tempo": self._safe_float(cols[7].get_text(strip=True)),
                                "efg_o": self._safe_float(cols[8].get_text(strip=True)),
                                "efg_d": self._safe_float(cols[9].get_text(strip=True)),
                                "tov_o": self._safe_float(cols[10].get_text(strip=True)),
                                "tov_d": self._safe_float(cols[11].get_text(strip=True)),
                                "orb": self._safe_float(cols[12].get_text(strip=True)),
                                "drb": self._safe_float(cols[13].get_text(strip=True)),
                                "ftr": self._safe_float(cols[14].get_text(strip=True)),
                                "source": "barttorvik_selenium"
                            }
                            if teams[team_name].get("adj_oe") and teams[team_name].get("adj_de"):
                                teams[team_name]["adj_em"] = round(
                                    teams[team_name]["adj_oe"] - teams[team_name]["adj_de"], 2
                                )
                        except:
                            continue

            logger.info(f"Selenium scraped {len(teams)} teams from BartTorvik")
            return teams

        except ImportError:
            logger.error("Selenium not installed. Run: pip install selenium")
            return {}
        except Exception as e:
            logger.error(f"Selenium error: {e}")
            return {}

    # =========================================================================
    # SPORTS REFERENCE - Additional Stats (Rate limited: 20 req/min)
    # =========================================================================

    def scrape_sports_reference(self) -> Dict[str, Dict]:
        """Scrape basic and advanced stats from Sports-Reference"""
        year = datetime.now().year
        teams = {}

        # Basic stats
        basic_url = f"https://www.sports-reference.com/cbb/seasons/men/{year}-school-stats.html"
        logger.info("Fetching Sports-Reference stats (respecting rate limits)")

        try:
            self._rate_limit(3)  # Extra delay for SR
            response = self.session.get(basic_url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            table = soup.find('table', {'id': 'basic_school_stats'})

            if table:
                tbody = table.find('tbody')
                if tbody:
                    for row in tbody.find_all('tr'):
                        if 'thead' in row.get('class', []):
                            continue

                        cols = row.find_all(['th', 'td'])
                        if len(cols) < 20:
                            continue

                        try:
                            team_link = cols[0].find('a')
                            if not team_link:
                                continue

                            team_name = normalize_team_name(team_link.get_text(strip=True))

                            teams[team_name] = {
                                "games": self._safe_int(cols[1].get_text(strip=True)),
                                "wins": self._safe_int(cols[2].get_text(strip=True)),
                                "losses": self._safe_int(cols[3].get_text(strip=True)),
                                "srs": self._safe_float(cols[5].get_text(strip=True)),
                                "sos": self._safe_float(cols[6].get_text(strip=True)),
                                "pts_per_game": self._safe_float(cols[8].get_text(strip=True)),
                                "opp_pts_per_game": self._safe_float(cols[9].get_text(strip=True)),
                                "fg_pct": self._safe_float(cols[11].get_text(strip=True)),
                                "fg3_pct": self._safe_float(cols[14].get_text(strip=True)),
                                "ft_pct": self._safe_float(cols[17].get_text(strip=True)),
                            }
                        except (IndexError, ValueError):
                            continue

                logger.info(f"Scraped {len(teams)} teams basic stats from SR")

        except requests.RequestException as e:
            logger.error(f"Sports-Reference basic error: {e}")

        # Advanced stats
        adv_url = f"https://www.sports-reference.com/cbb/seasons/men/{year}-advanced-school-stats.html"

        try:
            self._rate_limit(3)
            response = self.session.get(adv_url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            table = soup.find('table', {'id': 'adv_school_stats'})

            if table:
                tbody = table.find('tbody')
                if tbody:
                    for row in tbody.find_all('tr'):
                        if 'thead' in row.get('class', []):
                            continue

                        cols = row.find_all(['th', 'td'])
                        if len(cols) < 17:
                            continue

                        try:
                            team_link = cols[0].find('a')
                            if not team_link:
                                continue

                            team_name = normalize_team_name(team_link.get_text(strip=True))

                            if team_name not in teams:
                                teams[team_name] = {}

                            teams[team_name].update({
                                "sr_pace": self._safe_float(cols[3].get_text(strip=True)),
                                "sr_off_rtg": self._safe_float(cols[4].get_text(strip=True)),
                                "sr_def_rtg": self._safe_float(cols[6].get_text(strip=True)),
                                "sr_net_rtg": self._safe_float(cols[8].get_text(strip=True)),
                                "sr_efg_pct": self._safe_float(cols[9].get_text(strip=True)),
                                "sr_tov_pct": self._safe_float(cols[10].get_text(strip=True)),
                                "sr_orb_pct": self._safe_float(cols[11].get_text(strip=True)),
                                "sr_ft_rate": self._safe_float(cols[12].get_text(strip=True)),
                                "sr_opp_efg": self._safe_float(cols[13].get_text(strip=True)),
                                "sr_opp_tov": self._safe_float(cols[14].get_text(strip=True)),
                                "sr_drb_pct": self._safe_float(cols[15].get_text(strip=True)),
                                "sr_opp_ftr": self._safe_float(cols[16].get_text(strip=True)),
                            })
                        except (IndexError, ValueError):
                            continue

                logger.info(f"Added advanced stats for {len(teams)} teams from SR")

        except requests.RequestException as e:
            logger.error(f"Sports-Reference advanced error: {e}")

        return teams

    # =========================================================================
    # DATA MERGING AND COMPILATION
    # =========================================================================

    def merge_team_data(self, barttorvik: Dict, sports_ref: Dict) -> Dict[str, Dict]:
        """Merge team data from multiple sources, preferring BartTorvik"""
        merged = {}

        # Start with BartTorvik (most comprehensive for efficiency metrics)
        for team, data in barttorvik.items():
            merged[team] = data.copy()
            merged[team]["data_sources"] = ["barttorvik"]

        # Add/fill from Sports-Reference
        for team, data in sports_ref.items():
            if team not in merged:
                merged[team] = {"data_sources": []}

            # Add SR-specific fields
            for key in ["srs", "sos", "ft_pct", "fg3_pct", "pts_per_game",
                        "opp_pts_per_game", "sr_pace", "sr_off_rtg", "sr_def_rtg",
                        "sr_net_rtg", "sr_efg_pct", "sr_tov_pct", "sr_orb_pct",
                        "sr_ft_rate", "sr_opp_efg", "sr_opp_tov", "sr_drb_pct",
                        "sr_opp_ftr", "games", "wins", "losses"]:
                if data.get(key) is not None:
                    # Only overwrite if Torvik doesn't have equivalent
                    torvik_equiv = {
                        "sr_pace": "adj_tempo",
                        "sr_off_rtg": "adj_oe",
                        "sr_def_rtg": "adj_de",
                        "sr_efg_pct": "efg_o",
                        "sr_tov_pct": "tov_o",
                        "sr_orb_pct": "orb",
                        "sr_opp_efg": "efg_d",
                        "sr_opp_tov": "tov_d",
                        "sr_drb_pct": "drb",
                    }
                    torvik_key = torvik_equiv.get(key)
                    if torvik_key and merged[team].get(torvik_key) is not None:
                        merged[team][key] = data[key]  # Keep both
                    else:
                        merged[team][key] = data[key]

            if "sports_reference" not in merged[team].get("data_sources", []):
                merged[team]["data_sources"].append("sports_reference")

        return merged

    def scrape_espn_teams_from_games(self, games: List[Dict]) -> Dict[str, Dict]:
        """Fetch ESPN stats, injuries, and recent form for all teams in today's games"""
        teams = {}
        team_ids = set()
        game_dates = {}

        # Collect unique team IDs from games
        for game in games:
            game_date = game.get('date', '')
            if game.get('away', {}).get('espn_id'):
                team_ids.add((game['away']['name'], game['away']['espn_id']))
                game_dates[game['away']['espn_id']] = game_date
            if game.get('home', {}).get('espn_id'):
                team_ids.add((game['home']['name'], game['home']['espn_id']))
                game_dates[game['home']['espn_id']] = game_date

        logger.info(f"Fetching ESPN stats for {len(team_ids)} teams")

        for team_name, team_id in team_ids:
            try:
                # Get basic stats
                stats = self.scrape_espn_team_stats(team_id)
                if stats:
                    teams[team_name] = stats
                    teams[team_name]['espn_id'] = team_id

                    # Get recent schedule for form and rest calculations
                    schedule = self.scrape_team_schedule(team_id, limit=15)
                    if schedule:
                        # Calculate recent form
                        form = self.calculate_recent_form(schedule)
                        teams[team_name]['last_10_record'] = form.get('last_10_record')
                        teams[team_name]['last_10_wins'] = form.get('last_10_wins')
                        teams[team_name]['streak'] = form.get('streak')
                        teams[team_name]['form_adjustment'] = form.get('form_adjustment', 0)

                        # Calculate rest days
                        game_date = game_dates.get(team_id, '')
                        if game_date:
                            rest = self.calculate_rest_days(schedule, game_date)
                            teams[team_name]['rest_days'] = rest.get('rest_days')
                            teams[team_name]['games_last_7_days'] = rest.get('games_last_7_days')
                            teams[team_name]['is_back_to_back'] = rest.get('is_back_to_back', False)
                            teams[team_name]['fatigue_adjustment'] = rest.get('fatigue_adjustment', 0)

                    # Get injuries (quick check, don't fail if unavailable)
                    try:
                        injuries = self.scrape_espn_injuries(team_id)
                        if injuries:
                            teams[team_name]['injuries'] = injuries
                    except:
                        pass

                self._rate_limit(0.4)  # Slightly more delay for additional requests
            except Exception as e:
                logger.debug(f"Error fetching ESPN stats for {team_name}: {e}")
                continue

        logger.info(f"Got ESPN stats for {len(teams)} teams")
        return teams

    def _find_merged_key(self, merged: Dict, team_name: str) -> Optional[str]:
        """Find the matching key in merged dict using normalized names."""
        if team_name in merged:
            return team_name
        # Try normalizing the team name
        normalized = normalize_team_name(team_name)
        if normalized in merged:
            return normalized
        # Try matching against normalized versions of existing keys
        for existing_key in merged:
            if normalize_team_name(existing_key) == normalized:
                return existing_key
        return None

    def merge_all_team_data_with_kenpom(self, kenpom: Dict, barttorvik: Dict, espn: Dict, sports_ref: Dict) -> Dict[str, Dict]:
        """
        Merge team data from all sources with KenPom as highest priority.
        Priority: KenPom > BartTorvik > ESPN > Sports-Reference

        Uses normalized team names to match across sources (e.g., ESPN's
        "Nebraska Cornhuskers" matches KenPom's "Nebraska").
        """
        merged = {}

        # 1. Start with KenPom data (gold standard for efficiency metrics)
        for team, data in kenpom.items():
            merged[team] = data.copy()
            merged[team]["data_sources"] = ["kenpom"]

        # 2. Add BartTorvik data (fill gaps or add if KenPom missing)
        for team, data in barttorvik.items():
            match_key = self._find_merged_key(merged, team)
            if match_key is None:
                merged[team] = data.copy()
                merged[team]["data_sources"] = ["barttorvik"]
            else:
                # Add BartTorvik-specific fields that KenPom might not have
                for key in ['torvik_rank', 'barthag', 'efg_o', 'efg_d', 'tov_o', 'tov_d', 'orb', 'drb', 'ftr', 'ftrd']:
                    if data.get(key) is not None and merged[match_key].get(key) is None:
                        merged[match_key][key] = data[key]
                if "barttorvik" not in merged[match_key]["data_sources"]:
                    merged[match_key]["data_sources"].append("barttorvik")

        # 3. Add ESPN data (fill remaining gaps)
        # This is critical: ESPN provides Four Factors (efg_o, tov_o, orb, etc.)
        # that KenPom CSV doesn't include. We must match by normalized names.
        for team, data in espn.items():
            match_key = self._find_merged_key(merged, team)
            if match_key is None:
                # New team not in KenPom/BartTorvik - use ESPN as primary
                merged[team] = data.copy()
                merged[team]["data_sources"] = ["espn"]
            else:
                # Fill gaps in existing KenPom/BartTorvik data with ESPN stats
                for key, value in data.items():
                    if key not in merged[match_key] or merged[match_key][key] is None:
                        merged[match_key][key] = value
                if "espn" not in merged[match_key].get("data_sources", []):
                    merged[match_key]["data_sources"].append("espn")

        # 4. Add Sports-Reference data (supplementary)
        for team, data in sports_ref.items():
            match_key = self._find_merged_key(merged, team)
            if match_key is None:
                merged[team] = {"data_sources": []}
                match_key = team

            for key in ["srs", "sos", "ft_pct", "fg3_pct", "pts_per_game", "opp_pts_per_game", "games", "wins", "losses"]:
                if data.get(key) is not None and merged[match_key].get(key) is None:
                    merged[match_key][key] = data[key]

            if "sports_reference" not in merged[match_key].get("data_sources", []):
                merged[match_key]["data_sources"].append("sports_reference")

        return merged

    def merge_all_team_data(self, barttorvik: Dict, espn: Dict, sports_ref: Dict) -> Dict[str, Dict]:
        """
        Merge team data from all sources.
        Priority: BartTorvik > ESPN > Sports-Reference

        BartTorvik has best efficiency metrics when available.
        ESPN provides good fallback with calculated metrics.
        Sports-Reference adds supplementary data.
        """
        merged = {}

        # Start with BartTorvik (best efficiency metrics)
        for team, data in barttorvik.items():
            merged[team] = data.copy()
            merged[team]["data_sources"] = ["barttorvik"]

        # Add ESPN data (fill in missing teams and supplement existing)
        for team, data in espn.items():
            if team not in merged:
                # New team - use ESPN as primary
                merged[team] = data.copy()
                merged[team]["data_sources"] = ["espn"]
            else:
                # Team exists - add ESPN data as fallback
                for key, value in data.items():
                    if key not in merged[team] or merged[team][key] is None:
                        merged[team][key] = value
                if "espn" not in merged[team]["data_sources"]:
                    merged[team]["data_sources"].append("espn")

        # Add Sports-Reference data (supplementary)
        for team, data in sports_ref.items():
            if team not in merged:
                merged[team] = {"data_sources": []}

            for key in ["srs", "sos", "ft_pct", "fg3_pct", "pts_per_game",
                        "opp_pts_per_game", "games", "wins", "losses"]:
                if data.get(key) is not None and merged[team].get(key) is None:
                    merged[team][key] = data[key]

            if "sports_reference" not in merged[team].get("data_sources", []):
                merged[team]["data_sources"].append("sports_reference")

        return merged

    def attach_odds_to_games(self, games: List[Dict], odds: Dict[str, Dict], line_movement: Dict[str, Dict] = None) -> List[Dict]:
        """Attach odds data and line movement to games"""
        line_movement = line_movement or {}

        for game in games:
            away = game["away"]["name"]
            home = game["home"]["name"]
            game_key = f"{away}@{home}"
            matched_key = None

            if game_key in odds:
                game["odds"] = odds[game_key]
                matched_key = game_key
            else:
                # Try fuzzy matching
                for odds_key, odds_data in odds.items():
                    odds_away, odds_home = odds_key.split("@")
                    if (away.lower() in odds_away.lower() or odds_away.lower() in away.lower()) and \
                       (home.lower() in odds_home.lower() or odds_home.lower() in home.lower()):
                        game["odds"] = odds_data
                        matched_key = odds_key
                        break

            # Attach line movement data
            if matched_key and matched_key in line_movement:
                game["line_movement"] = line_movement[matched_key]
            elif game_key in line_movement:
                game["line_movement"] = line_movement[game_key]

        return games

    # =========================================================================
    # MAIN SCRAPER
    # =========================================================================

    def run(self, date_str: str = None) -> Dict:
        """
        Main scraper function. Collects all data and saves to JSON.
        """
        if date_str is None:
            date_str = self.today_yyyymmdd

        logger.info("=" * 60)
        logger.info(f"NCAA Basketball Data Scraper - {date_str}")
        logger.info("=" * 60)

        # 1. Import KenPom CSV (if available - HIGHEST PRIORITY)
        print("\n[1/6] Checking for KenPom CSV...")
        kenpom_data = self.import_kenpom_csv()

        # 2. Fetch schedule from ESPN
        print("[2/6] Fetching schedule from ESPN...")
        games = self.scrape_espn_schedule(date_str)
        if not games:
            logger.warning("No games found for today")

        # 3. Fetch odds from The Odds API
        print("[3/6] Fetching betting odds...")
        odds = self.scrape_odds_api()
        self._rate_limit()

        # 3b. Update line history and calculate movement
        line_history = {}
        line_movement = {}
        if odds:
            print("    → Updating line history...")
            line_history = self.update_line_history(odds)
            line_movement = self.calculate_line_movement(line_history)

            # Log any sharp action detected
            sharp_games = [k for k, v in line_movement.items() if v.get('has_sharp_action')]
            if sharp_games:
                logger.info(f"SHARP ACTION detected in {len(sharp_games)} games")

        # 4. Attach odds to games (now includes line movement)
        games = self.attach_odds_to_games(games, odds, line_movement)

        # 5. Fetch ESPN team stats for teams in today's games
        print("[4/6] Fetching ESPN team stats...")
        espn_team_stats = self.scrape_espn_teams_from_games(games)

        # 6. Fetch team stats from BartTorvik (may be blocked by Cloudflare)
        print("[5/6] Fetching advanced metrics from BartTorvik...")
        barttorvik_data = self.scrape_barttorvik()
        self._rate_limit()

        # 7. Fetch stats from Sports-Reference (rate limited)
        print("[6/6] Fetching stats from Sports-Reference...")
        sr_data = self.scrape_sports_reference()

        # 8. Merge all team data
        # Priority: KenPom (gold standard) > BartTorvik > ESPN > Sports-Ref
        print("\nMerging data from all sources...")
        teams = self.merge_all_team_data_with_kenpom(kenpom_data, barttorvik_data, espn_team_stats, sr_data)

        # 9. Build final dataset
        sharp_action_games = [k for k, v in line_movement.items() if v.get('has_sharp_action')]

        dataset = {
            "date": self.today,
            "scraped_at": datetime.now().isoformat(),
            "games_count": len(games),
            "teams_count": len(teams),
            "games": games,
            "teams": teams,
            "line_movement_summary": {
                "games_tracked": len(line_movement),
                "snapshots_today": len(line_history.get("snapshots", [])),
                "sharp_action_games": sharp_action_games,
                "sharp_action_count": len(sharp_action_games),
            },
            "metadata": {
                "sources_used": {
                    "kenpom": bool(kenpom_data),
                    "espn_schedule": True,
                    "espn_stats": bool(espn_team_stats),
                    "odds_api": bool(ODDS_API_KEY and odds),
                    "barttorvik": bool(barttorvik_data),
                    "sports_reference": bool(sr_data),
                    "line_tracking": bool(line_movement),
                },
                "odds_api_key_present": bool(ODDS_API_KEY),
                "kenpom_teams": len(kenpom_data) if kenpom_data else 0,
            }
        }

        # 8. Save to file
        filename = DATA_DIR / f"ncaa_data_{date_str}.json"
        with open(filename, 'w') as f:
            json.dump(dataset, f, indent=2, default=str)

        logger.info("=" * 60)
        logger.info(f"Data saved to {filename}")
        logger.info(f"Games: {len(games)}, Teams with data: {len(teams)}")
        logger.info("=" * 60)

        return dataset


def main():
    """Entry point"""
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None

    scraper = NCAADataScraper()
    dataset = scraper.run(date_arg)

    # Print summary
    print("\n" + "=" * 60)
    print("DATA COLLECTION COMPLETE")
    print("=" * 60)
    print(f"Date: {dataset['date']}")
    print(f"Games today: {dataset['games_count']}")
    print(f"Teams with data: {dataset['teams_count']}")

    sources = dataset['metadata']['sources_used']
    kenpom_count = dataset['metadata'].get('kenpom_teams', 0)
    print(f"\nData sources:")
    print(f"  - KenPom CSV: {'✓ (' + str(kenpom_count) + ' teams)' if sources.get('kenpom') else '✗ (no CSV in /kenpom folder)'}")
    print(f"  - ESPN Schedule: {'✓' if sources.get('espn_schedule') else '✗'}")
    print(f"  - ESPN Stats: {'✓' if sources.get('espn_stats') else '✗'}")
    print(f"  - Odds API: {'✓' if sources.get('odds_api') else '✗ (no API key)'}")
    print(f"  - BartTorvik: {'✓' if sources.get('barttorvik') else '✗ (Cloudflare blocked)'}")
    print(f"  - Sports-Reference: {'✓' if sources.get('sports_reference') else '✗'}")

    if dataset['games']:
        print(f"\nToday's Games ({len(dataset['games'])}):")
        for game in dataset['games'][:15]:  # Show first 15
            away = game['away']['name']
            home = game['home']['name']
            away_rank = f"#{game['away']['rank']} " if game['away'].get('rank') else ""
            home_rank = f"#{game['home']['rank']} " if game['home'].get('rank') else ""

            # Get spread if available
            spread_str = ""
            if game.get('odds') and game['odds'].get('consensus', {}).get('spread'):
                spread = game['odds']['consensus']['spread']
                if spread < 0:
                    spread_str = f" ({away} {spread})"
                else:
                    spread_str = f" ({home} {-spread})"
            elif game.get('espn_odds', {}).get('spread_details'):
                spread_str = f" ({game['espn_odds']['spread_details']})"

            print(f"  {away_rank}{away} @ {home_rank}{home}{spread_str}")

        if len(dataset['games']) > 15:
            print(f"  ... and {len(dataset['games']) - 15} more games")

    return 0


if __name__ == "__main__":
    sys.exit(main())
