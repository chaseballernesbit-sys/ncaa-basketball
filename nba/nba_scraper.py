#!/usr/bin/env python3
"""
NBA Basketball - Data Scraper
Collects data from ESPN API, nba_api, The Odds API, and injury reports.
"""

import json
import time
import re
import sys
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from nba.nba_config import (
    DATA_DIR, ODDS_API_KEY, REQUEST_DELAY, NBA_API_DELAY, USER_AGENT,
    NBA_LINE_HISTORY_DIR
)
from nba.nba_team_mappings import (
    normalize_team_name, get_espn_id, get_nba_api_id,
    ESPN_TEAM_IDS, NBA_API_TEAM_IDS, TEAM_ALIASES
)


class NBADataScraper:
    ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
    ODDS_API_BASE = "https://api.the-odds-api.com/v4/sports/basketball_nba"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.teams = {}
        self.games = []
        self.date_str = datetime.now().strftime("%Y-%m-%d")
        self.date_compact = datetime.now().strftime("%Y%m%d")

    # =========================================================================
    # ESPN SCHEDULE
    # =========================================================================
    def scrape_espn_schedule(self) -> List[Dict]:
        """Get today's NBA games from ESPN scoreboard."""
        url = f"{self.ESPN_BASE}/scoreboard"
        params = {"dates": self.date_compact}
        print(f"  Fetching ESPN schedule for {self.date_str}...")

        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  ERROR fetching ESPN schedule: {e}")
            return []

        games = []
        for event in data.get("events", []):
            competition = event.get("competitions", [{}])[0]
            competitors = competition.get("competitors", [])
            if len(competitors) < 2:
                continue

            home_comp = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
            away_comp = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

            home_team_data = home_comp.get("team", {})
            away_team_data = away_comp.get("team", {})

            # Extract odds if available
            espn_odds = {}
            odds_list = competition.get("odds", [])
            if odds_list:
                o = odds_list[0]
                espn_odds = {
                    "spread_details": o.get("details", ""),
                    "total": o.get("overUnder"),
                    "provider": o.get("provider", {}).get("name", ""),
                }

            game = {
                "game_id": event.get("id", ""),
                "name": event.get("name", ""),
                "date": event.get("date", ""),
                "status": event.get("status", {}).get("type", {}).get("name", ""),
                "venue": competition.get("venue", {}).get("fullName", ""),
                "neutral_site": competition.get("neutralSite", False),
                "away": {
                    "name": normalize_team_name(away_team_data.get("displayName", "")),
                    "abbreviation": away_team_data.get("abbreviation", ""),
                    "espn_id": away_team_data.get("id", ""),
                    "record": away_comp.get("records", [{}])[0].get("summary", "") if away_comp.get("records") else "",
                    "score": away_comp.get("score", None),
                },
                "home": {
                    "name": normalize_team_name(home_team_data.get("displayName", "")),
                    "abbreviation": home_team_data.get("abbreviation", ""),
                    "espn_id": home_team_data.get("id", ""),
                    "record": home_comp.get("records", [{}])[0].get("summary", "") if home_comp.get("records") else "",
                    "score": home_comp.get("score", None),
                },
                "espn_odds": espn_odds,
                "odds": {},
                "line_movement": {},
            }
            games.append(game)

        print(f"  Found {len(games)} NBA games for today")
        self.games = games
        return games

    # =========================================================================
    # ESPN TEAM STATS
    # =========================================================================
    def scrape_espn_team_stats(self) -> Dict:
        """Fetch team stats from ESPN for all 30 NBA teams."""
        print(f"  Fetching ESPN team stats...")
        stats_fetched = 0

        for team_name, team_id in ESPN_TEAM_IDS.items():
            url = f"{self.ESPN_BASE}/teams/{team_id}/statistics"
            try:
                resp = self.session.get(url, timeout=10)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                time.sleep(REQUEST_DELAY)
            except Exception:
                continue

            stats = self._parse_espn_stats(data)
            if stats:
                if team_name not in self.teams:
                    self.teams[team_name] = {}
                self.teams[team_name].update(stats)
                self.teams[team_name]["data_sources"] = self.teams[team_name].get("data_sources", [])
                if "espn" not in self.teams[team_name]["data_sources"]:
                    self.teams[team_name]["data_sources"].append("espn")
                stats_fetched += 1

        print(f"  ESPN stats: {stats_fetched} teams")
        return self.teams

    def _parse_espn_stats(self, data: Dict) -> Optional[Dict]:
        """Parse ESPN team stats response into our format."""
        try:
            splits = data.get("results", {}).get("stats", {}).get("categories", [])
            if not splits:
                # Try alternative structure
                splits = data.get("statistics", {}).get("splits", {}).get("categories", [])
            if not splits:
                return None

            raw = {}
            for category in splits:
                for stat in category.get("stats", []):
                    raw[stat.get("name", "")] = stat.get("value", 0)

            # Calculate efficiency metrics
            fga = raw.get("fieldGoalsAttempted", 0) or raw.get("avgFieldGoalsAttempted", 0)
            fgm = raw.get("fieldGoalsMade", 0) or raw.get("avgFieldGoalsMade", 0)
            fta = raw.get("freeThrowsAttempted", 0) or raw.get("avgFreeThrowsAttempted", 0)
            ftm = raw.get("freeThrowsMade", 0) or raw.get("avgFreeThrowsMade", 0)
            tov = raw.get("turnovers", 0) or raw.get("avgTurnovers", 0)
            orb = raw.get("offensiveRebounds", 0) or raw.get("avgOffensiveRebounds", 0)
            drb = raw.get("defensiveRebounds", 0) or raw.get("avgDefensiveRebounds", 0)
            tpfga = raw.get("threePointFieldGoalsAttempted", 0) or raw.get("avgThreePointFieldGoalsAttempted", 0)
            tpfgm = raw.get("threePointFieldGoalsMade", 0) or raw.get("avgThreePointFieldGoalsMade", 0)
            pts = raw.get("avgPoints", 0) or raw.get("points", 0)

            # Possessions estimate
            poss = fga + 0.44 * fta - orb + tov
            if poss <= 0:
                poss = 95

            # Efficiency per 100 possessions
            off_eff = (pts / poss * 100) if poss > 0 else 100

            # Four Factors
            efg = ((fgm + 0.5 * tpfgm) / fga * 100) if fga > 0 else 50
            tov_pct = (tov / poss * 100) if poss > 0 else 15
            orb_pct = (orb / (orb + drb) * 100) if (orb + drb) > 0 else 25
            ftr = (fta / fga * 100) if fga > 0 else 25
            fg_pct = (fgm / fga * 100) if fga > 0 else 45
            tp_pct = (tpfgm / tpfga * 100) if tpfga > 0 else 35
            ft_pct = (ftm / fta * 100) if fta > 0 else 75

            result = {
                "espn_stats": raw,
                "espn_off_eff": round(off_eff, 1),
                "espn_poss": round(poss, 1),
                "fg_pct": round(fg_pct, 1),
                "tp_pct": round(tp_pct, 1),
                "ft_pct": round(ft_pct, 1),
            }
            # Only set these if nba_api hasn't already provided them
            if pts > 0:
                result["ppg"] = round(pts, 1)
            if efg != 50:
                result["espn_efg"] = round(efg, 1)
                result["espn_tov_pct"] = round(tov_pct, 1)
                result["espn_orb_pct"] = round(orb_pct, 1)
                result["espn_ftr"] = round(ftr, 1)
            return result
        except Exception as e:
            return None

    # =========================================================================
    # NBA_API ADVANCED STATS
    # =========================================================================
    def scrape_nba_api_stats(self) -> Dict:
        """Fetch advanced stats from NBA.com via nba_api package."""
        print("  Fetching nba_api advanced stats...")

        try:
            from nba_api.stats.endpoints import LeagueDashTeamStats
        except ImportError:
            print("  WARNING: nba_api not installed - skipping advanced stats")
            return self.teams

        # Season-wide team stats
        try:
            stats = LeagueDashTeamStats(
                season="2025-26",
                measure_type_detailed_defense="Base",
                per_mode_detailed="PerGame",
            )
            time.sleep(NBA_API_DELAY)
            df = stats.get_data_frames()[0]
            print(f"  nba_api: Got stats for {len(df)} teams")

            for _, row in df.iterrows():
                team_name = normalize_team_name(row.get("TEAM_NAME", ""))
                if not team_name:
                    continue

                if team_name not in self.teams:
                    self.teams[team_name] = {}

                wins = row.get("W", 0)
                losses = row.get("L", 0)
                total = wins + losses
                win_pct = wins / total if total > 0 else 0.5

                self.teams[team_name].update({
                    "record": f"{wins}-{losses}",
                    "win_pct": round(win_pct, 3),
                    "ppg": round(row.get("PTS", 0), 1),
                    "opp_ppg": round(row.get("OPP_PTS", 0) if "OPP_PTS" in row.index else 0, 1),
                    "fg_pct": round(row.get("FG_PCT", 0) * 100, 1),
                    "tp_pct": round(row.get("FG3_PCT", 0) * 100, 1),
                    "ft_pct": round(row.get("FT_PCT", 0) * 100, 1),
                    "reb": round(row.get("REB", 0), 1),
                    "ast": round(row.get("AST", 0), 1),
                    "stl": round(row.get("STL", 0), 1),
                    "blk": round(row.get("BLK", 0), 1),
                    "tov_pg": round(row.get("TOV", 0), 1),
                })

                ds = self.teams[team_name].get("data_sources", [])
                if "nba_api" not in ds:
                    ds.append("nba_api")
                self.teams[team_name]["data_sources"] = ds

        except Exception as e:
            print(f"  WARNING: nba_api base stats failed: {e}")

        # Advanced stats (OffRtg, DefRtg, Pace, NetRtg)
        try:
            from nba_api.stats.endpoints import LeagueDashTeamStats as LDTS
            adv = LDTS(
                season="2025-26",
                measure_type_detailed_defense="Advanced",
                per_mode_detailed="PerGame",
            )
            time.sleep(NBA_API_DELAY)
            adf = adv.get_data_frames()[0]
            print(f"  nba_api: Got advanced stats for {len(adf)} teams")

            for _, row in adf.iterrows():
                team_name = normalize_team_name(row.get("TEAM_NAME", ""))
                if not team_name or team_name not in self.teams:
                    continue

                off_rtg = row.get("OFF_RATING", 112)
                def_rtg = row.get("DEF_RATING", 112)
                net_rtg = row.get("NET_RATING", 0)
                pace = row.get("PACE", 99)

                self.teams[team_name].update({
                    "adj_oe": round(off_rtg, 1),
                    "adj_de": round(def_rtg, 1),
                    "adj_em": round(net_rtg, 1),
                    "net_rating": round(net_rtg, 1),
                    "adj_tempo": round(pace, 1),
                })

        except Exception as e:
            print(f"  WARNING: nba_api advanced stats failed: {e}")

        # Four Factors
        try:
            from nba_api.stats.endpoints import LeagueDashTeamStats as LDTS2
            ff = LDTS2(
                season="2025-26",
                measure_type_detailed_defense="Four Factors",
                per_mode_detailed="PerGame",
            )
            time.sleep(NBA_API_DELAY)
            fdf = ff.get_data_frames()[0]
            print(f"  nba_api: Got Four Factors for {len(fdf)} teams")

            for _, row in fdf.iterrows():
                team_name = normalize_team_name(row.get("TEAM_NAME", ""))
                if not team_name or team_name not in self.teams:
                    continue

                self.teams[team_name].update({
                    "efg_o": round(row.get("EFG_PCT", 0.50) * 100, 1),
                    "ftr": round(row.get("FTA_RATE", 0.25) * 100, 1),
                    "tov_o": round(row.get("TM_TOV_PCT", 0.15) * 100, 1),
                    "orb": round(row.get("OREB_PCT", 0.25) * 100, 1),
                })

        except Exception as e:
            print(f"  WARNING: nba_api Four Factors failed: {e}")

        # Opponent stats (defensive Four Factors)
        try:
            from nba_api.stats.endpoints import LeagueDashTeamStats as LDTS3
            opp = LDTS3(
                season="2025-26",
                measure_type_detailed_defense="Opponent",
                per_mode_detailed="PerGame",
            )
            time.sleep(NBA_API_DELAY)
            odf = opp.get_data_frames()[0]

            for _, row in odf.iterrows():
                team_name = normalize_team_name(row.get("TEAM_NAME", ""))
                if not team_name or team_name not in self.teams:
                    continue

                opp_fga = row.get("OPP_FGA", 1)
                opp_fgm = row.get("OPP_FGM", 0)
                opp_fg3m = row.get("OPP_FG3M", 0)
                opp_fta = row.get("OPP_FTA", 1)
                opp_tov = row.get("OPP_TOV", 0)
                opp_orb = row.get("OPP_OREB", 0)
                opp_drb = row.get("OPP_DREB", 0)
                opp_pts = row.get("OPP_PTS", 0)

                efg_d = ((opp_fgm + 0.5 * opp_fg3m) / opp_fga * 100) if opp_fga > 0 else 50
                ftr_d = (opp_fta / opp_fga * 100) if opp_fga > 0 else 25
                drb_pct = (opp_drb / (opp_orb + opp_drb) * 100) if (opp_orb + opp_drb) > 0 else 75

                self.teams[team_name].update({
                    "efg_d": round(efg_d, 1),
                    "ftrd": round(ftr_d, 1),
                    "drb": round(drb_pct, 1),
                    "opp_ppg": round(opp_pts, 1),
                })

        except Exception as e:
            print(f"  WARNING: nba_api opponent stats failed: {e}")

        return self.teams

    # =========================================================================
    # NBA_API ROLLING STATS (Last 10 / Last 20 games)
    # =========================================================================
    def scrape_nba_api_rolling_stats(self) -> Dict:
        """Fetch rolling window stats (last 10 and last 20 games) from nba_api."""
        print("  Fetching nba_api rolling stats...")

        try:
            from nba_api.stats.endpoints import LeagueDashTeamStats
        except ImportError:
            print("  WARNING: nba_api not installed - skipping rolling stats")
            return self.teams

        for window in [10, 20]:
            try:
                stats = LeagueDashTeamStats(
                    season="2025-26",
                    measure_type_detailed_defense="Advanced",
                    per_mode_detailed="PerGame",
                    last_n_games=str(window),
                )
                time.sleep(NBA_API_DELAY)
                df = stats.get_data_frames()[0]
                prefix = f"rolling_{window}"

                for _, row in df.iterrows():
                    team_name = normalize_team_name(row.get("TEAM_NAME", ""))
                    if not team_name:
                        continue
                    if team_name not in self.teams:
                        self.teams[team_name] = {}

                    self.teams[team_name].update({
                        f"{prefix}_oe": round(row.get("OFF_RATING", 112), 1),
                        f"{prefix}_de": round(row.get("DEF_RATING", 112), 1),
                        f"{prefix}_pace": round(row.get("PACE", 99), 1),
                    })

                print(f"  Rolling L{window}: Got stats for {len(df)} teams")

            except Exception as e:
                print(f"  WARNING: nba_api rolling L{window} stats failed: {e}")

        return self.teams

    # =========================================================================
    # NBA_API HOME/AWAY SPLITS
    # =========================================================================
    def scrape_nba_api_location_splits(self) -> Dict:
        """Fetch home/away efficiency splits from nba_api."""
        print("  Fetching nba_api location splits...")

        try:
            from nba_api.stats.endpoints import LeagueDashTeamStats
        except ImportError:
            print("  WARNING: nba_api not installed - skipping location splits")
            return self.teams

        for location, prefix in [("Home", "home"), ("Road", "away")]:
            try:
                stats = LeagueDashTeamStats(
                    season="2025-26",
                    measure_type_detailed_defense="Advanced",
                    per_mode_detailed="PerGame",
                    location_nullable=location,
                )
                time.sleep(NBA_API_DELAY)
                df = stats.get_data_frames()[0]

                for _, row in df.iterrows():
                    team_name = normalize_team_name(row.get("TEAM_NAME", ""))
                    if not team_name:
                        continue
                    if team_name not in self.teams:
                        self.teams[team_name] = {}

                    self.teams[team_name].update({
                        f"{prefix}_oe": round(row.get("OFF_RATING", 112), 1),
                        f"{prefix}_de": round(row.get("DEF_RATING", 112), 1),
                    })

                print(f"  {location} splits: Got stats for {len(df)} teams")

            except Exception as e:
                print(f"  WARNING: nba_api {location} splits failed: {e}")

        return self.teams

    # =========================================================================
    # NBA_API BENCH DEPTH STATS
    # =========================================================================
    def scrape_nba_api_depth_stats(self) -> Dict:
        """Fetch starters vs bench scoring splits from nba_api."""
        print("  Fetching nba_api depth stats...")

        try:
            from nba_api.stats.endpoints import LeagueDashTeamStats
        except ImportError:
            print("  WARNING: nba_api not installed - skipping depth stats")
            return self.teams

        for group, key in [("Starters", "starters_ppg"), ("Bench", "bench_ppg")]:
            try:
                stats = LeagueDashTeamStats(
                    season="2025-26",
                    measure_type_detailed_defense="Base",
                    per_mode_detailed="PerGame",
                    starter_bench_nullable=group,
                )
                time.sleep(NBA_API_DELAY)
                df = stats.get_data_frames()[0]

                for _, row in df.iterrows():
                    team_name = normalize_team_name(row.get("TEAM_NAME", ""))
                    if not team_name:
                        continue
                    if team_name not in self.teams:
                        self.teams[team_name] = {}

                    self.teams[team_name][key] = round(row.get("PTS", 0), 1)

                print(f"  {group} stats: Got stats for {len(df)} teams")

            except Exception as e:
                print(f"  WARNING: nba_api {group} stats failed: {e}")

        return self.teams

    # =========================================================================
    # ODDS API
    # =========================================================================
    def scrape_odds(self) -> List[Dict]:
        """Fetch odds from The Odds API."""
        if not ODDS_API_KEY:
            print("  WARNING: No ODDS_API_KEY set - skipping odds")
            return []

        print("  Fetching odds from The Odds API...")
        url = f"{self.ODDS_API_BASE}/odds/"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": "spreads,totals,h2h",
            "oddsFormat": "american",
            "bookmakers": "draftkings,fanduel,betmgm,caesars,pointsbetus,betrivers",
        }

        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            odds_data = resp.json()
            remaining = resp.headers.get("x-requests-remaining", "?")
            print(f"  Odds API: {len(odds_data)} games, {remaining} requests remaining")
        except Exception as e:
            print(f"  ERROR fetching odds: {e}")
            return []

        # Match odds to games
        for odds_game in odds_data:
            away_name = normalize_team_name(odds_game.get("away_team", ""))
            home_name = normalize_team_name(odds_game.get("home_team", ""))

            consensus = {"spread": None, "total": None, "away_ml": None, "home_ml": None,
                         "away_spread_odds": None, "home_spread_odds": None}
            all_spreads = []
            all_totals = []
            all_away_ml = []
            all_home_ml = []
            all_away_spread_odds = []
            all_home_spread_odds = []

            for book in odds_game.get("bookmakers", []):
                for market in book.get("markets", []):
                    outcomes = market.get("outcomes", [])
                    if market["key"] == "spreads":
                        for o in outcomes:
                            name = normalize_team_name(o.get("name", ""))
                            if name == away_name:
                                all_spreads.append(o.get("point", 0))
                                if o.get("price") is not None:
                                    all_away_spread_odds.append(o["price"])
                            elif name == home_name:
                                if o.get("price") is not None:
                                    all_home_spread_odds.append(o["price"])
                    elif market["key"] == "totals":
                        for o in outcomes:
                            if o.get("name") == "Over":
                                all_totals.append(o.get("point", 0))
                    elif market["key"] == "h2h":
                        for o in outcomes:
                            name = normalize_team_name(o.get("name", ""))
                            if name == away_name:
                                all_away_ml.append(o.get("price", 0))
                            elif name == home_name:
                                all_home_ml.append(o.get("price", 0))

            if all_spreads:
                consensus["spread"] = round(sum(all_spreads) / len(all_spreads), 1)
            if all_totals:
                consensus["total"] = round(sum(all_totals) / len(all_totals), 1)
            if all_away_ml:
                consensus["away_ml"] = round(sum(all_away_ml) / len(all_away_ml))
            if all_home_ml:
                consensus["home_ml"] = round(sum(all_home_ml) / len(all_home_ml))
            if all_away_spread_odds:
                consensus["away_spread_odds"] = round(sum(all_away_spread_odds) / len(all_away_spread_odds))
            if all_home_spread_odds:
                consensus["home_spread_odds"] = round(sum(all_home_spread_odds) / len(all_home_spread_odds))

            # Match to our game list
            for game in self.games:
                g_away = game["away"]["name"]
                g_home = game["home"]["name"]
                if g_away == away_name and g_home == home_name:
                    game["odds"] = {"consensus": consensus}
                    break

        matched = sum(1 for g in self.games if g.get("odds", {}).get("consensus"))
        print(f"  Matched odds to {matched}/{len(self.games)} games")
        return odds_data

    # =========================================================================
    # INJURIES
    # =========================================================================
    def scrape_injuries(self) -> Dict:
        """Fetch injury reports from ESPN."""
        print("  Fetching injury reports...")
        injuries_by_team = {}

        # Try ESPN injuries endpoint
        url = f"{self.ESPN_BASE}/injuries"
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for team_entry in data.get("injuries", []):
                # Team info is directly on team_entry, not nested under "team"
                team_name = normalize_team_name(team_entry.get("displayName", ""))
                if not team_name:
                    continue

                team_injuries = []
                for item in team_entry.get("injuries", []):
                    athlete = item.get("athlete", {})
                    status_text = item.get("status", "")
                    # Map ESPN status to our categories
                    if "out" in status_text.lower():
                        status = "Out"
                    elif "doubtful" in status_text.lower():
                        status = "Doubtful"
                    elif "questionable" in status_text.lower() or "day-to-day" in status_text.lower():
                        status = "Questionable"
                    elif "probable" in status_text.lower():
                        status = "Probable"
                    else:
                        status = status_text

                    injury = {
                        "player": athlete.get("displayName", "Unknown"),
                        "position": athlete.get("position", {}).get("abbreviation", ""),
                        "status": status,
                        "description": item.get("shortComment", "") or item.get("longComment", ""),
                        "injury_type": item.get("details", {}).get("type", ""),
                        "return_date": item.get("details", {}).get("returnDate", ""),
                    }
                    team_injuries.append(injury)

                if team_injuries:
                    injuries_by_team[team_name] = team_injuries

        except Exception as e:
            print(f"  WARNING: ESPN injuries failed: {e}")

        # Try to get player stats for injured players (PPG, minutes)
        self._enrich_injury_data(injuries_by_team)

        # Attach to team data
        for team_name, injuries in injuries_by_team.items():
            if team_name in self.teams:
                self.teams[team_name]["injuries"] = injuries

        total_injured = sum(len(v) for v in injuries_by_team.values())
        out_count = sum(1 for inj_list in injuries_by_team.values()
                        for inj in inj_list if inj["status"] in ("Out", "Doubtful"))
        print(f"  Injuries: {total_injured} players ({out_count} Out/Doubtful) across {len(injuries_by_team)} teams")
        return injuries_by_team

    def _enrich_injury_data(self, injuries_by_team: Dict):
        """Get PPG/minutes/usage for injured players via nba_api.

        Only uses current season stats. Players not found (e.g. out all
        season) default to PPG=0 — their absence is already baked into
        the team's efficiency ratings, so no adjustment is needed.
        """
        try:
            from nba_api.stats.endpoints import LeagueDashPlayerStats

            # Base stats (PPG, minutes, games)
            player_stats = LeagueDashPlayerStats(
                season="2025-26",
                per_mode_detailed="PerGame",
            )
            time.sleep(NBA_API_DELAY)
            pdf = player_stats.get_data_frames()[0]

            # Build lookup by player name
            player_lookup = {}
            for _, row in pdf.iterrows():
                pname = row.get("PLAYER_NAME", "")
                player_lookup[pname.lower()] = {
                    "ppg": round(row.get("PTS", 0), 1),
                    "minutes": round(row.get("MIN", 0), 1),
                    "games_played": row.get("GP", 0),
                }

            # Advanced stats (usage rate)
            try:
                adv_stats = LeagueDashPlayerStats(
                    season="2025-26",
                    measure_type_detailed_defense="Advanced",
                    per_mode_detailed="PerGame",
                )
                time.sleep(NBA_API_DELAY)
                adf = adv_stats.get_data_frames()[0]

                for _, row in adf.iterrows():
                    pname = row.get("PLAYER_NAME", "").lower()
                    if pname in player_lookup:
                        player_lookup[pname]["usage_rate"] = round(row.get("USG_PCT", 0.15), 3)
            except Exception:
                pass  # Usage rate is nice-to-have, not critical

            # Enrich injury data
            enriched = 0
            for team_name, injuries in injuries_by_team.items():
                for inj in injuries:
                    player_name = inj.get("player", "").lower()
                    if player_name in player_lookup:
                        inj.update(player_lookup[player_name])
                        enriched += 1
                    else:
                        # Not in current season stats — their absence is
                        # already reflected in the team's baseline ratings
                        inj["ppg"] = 0
                        inj["minutes"] = 0
                        inj["usage_rate"] = 0.10

            print(f"  Enriched {enriched} injured players with stats")

        except Exception as e:
            print(f"  WARNING: Could not enrich injury data: {e}")

    # =========================================================================
    # TRADE LOG
    # =========================================================================
    def load_trade_log(self) -> Dict:
        """Load recent trades from manually maintained trade_log.json."""
        trade_file = Path(__file__).parent / "trade_log.json"
        if not trade_file.exists():
            return {}

        try:
            with open(trade_file) as f:
                data = json.load(f)

            trades = data.get("trades", [])
            active_trades = {}
            for trade in trades:
                team = normalize_team_name(trade.get("team", ""))
                games_since = trade.get("games_since", 999)
                if games_since <= 15 and team:
                    active_trades[team] = {
                        "games_since": games_since,
                        "impact": trade.get("impact", "minor"),
                        "players_added": trade.get("players_added", []),
                        "players_lost": trade.get("players_lost", []),
                    }
                    if team in self.teams:
                        self.teams[team]["recent_trade"] = active_trades[team]

            if active_trades:
                print(f"  Trade log: {len(active_trades)} teams with recent trades")
            return active_trades

        except Exception as e:
            print(f"  WARNING: Could not load trade log: {e}")
            return {}

    # =========================================================================
    # REST / BACK-TO-BACK / RECENT FORM
    # =========================================================================
    def calculate_rest_and_form(self):
        """Calculate rest days, B2B status, and recent form for each team playing today."""
        print("  Calculating rest days and recent form...")

        teams_in_games = set()
        for game in self.games:
            teams_in_games.add(game["away"]["name"])
            teams_in_games.add(game["home"]["name"])

        for team_name in teams_in_games:
            espn_id = get_espn_id(team_name)
            if not espn_id:
                continue

            # Fetch recent schedule
            url = f"{self.ESPN_BASE}/teams/{espn_id}/schedule"
            try:
                resp = self.session.get(url, timeout=10)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                time.sleep(REQUEST_DELAY * 0.5)
            except Exception:
                continue

            events = data.get("events", [])
            if not events:
                continue

            today = datetime.strptime(self.date_str, "%Y-%m-%d")
            past_games = []
            for ev in events:
                try:
                    game_date_str = ev.get("date", "")
                    game_date = datetime.fromisoformat(game_date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    status = ev.get("status", {}).get("type", {}).get("name", "")
                    if game_date.date() < today.date() and status == "STATUS_FINAL":
                        # Determine win/loss
                        comps = ev.get("competitions", [{}])[0].get("competitors", [])
                        team_comp = None
                        for c in comps:
                            if c.get("team", {}).get("id") == espn_id:
                                team_comp = c
                                break
                        won = team_comp.get("winner", False) if team_comp else False
                        was_home = team_comp.get("homeAway") == "home" if team_comp else False

                        past_games.append({
                            "date": game_date,
                            "won": won,
                            "home": was_home,
                        })
                except Exception:
                    continue

            past_games.sort(key=lambda x: x["date"], reverse=True)

            # Rest days
            rest_days = 3  # default
            is_b2b = False
            if past_games:
                last_game_date = past_games[0]["date"]
                rest_days = (today - last_game_date).days - 1
                is_b2b = rest_days == 0

            # Recent form (last 10)
            last_10 = past_games[:10]
            wins_10 = sum(1 for g in last_10 if g["won"])
            record_10 = f"{wins_10}-{len(last_10) - wins_10}"

            # Streak
            streak = 0
            if past_games:
                streak_win = past_games[0]["won"]
                for g in past_games:
                    if g["won"] == streak_win:
                        streak += 1
                    else:
                        break
                if not streak_win:
                    streak = -streak

            # B2B road check
            is_second_road_b2b = False
            if is_b2b and len(past_games) >= 1 and not past_games[0].get("home", True):
                is_second_road_b2b = True

            if team_name not in self.teams:
                self.teams[team_name] = {}

            self.teams[team_name].update({
                "rest_days": rest_days,
                "is_back_to_back": is_b2b,
                "is_second_road_b2b": is_second_road_b2b,
                "last_10_record": record_10,
                "streak": streak,
                "wins_last_10": wins_10,
            })

        print(f"  Rest/form data for {len(teams_in_games)} teams")

    # =========================================================================
    # LINE MOVEMENT TRACKING
    # =========================================================================
    def load_nba_line_history(self) -> Dict:
        """Load previously saved line snapshots for today."""
        history_file = NBA_LINE_HISTORY_DIR / f"nba_lines_{self.date_compact}.json"
        if history_file.exists():
            try:
                with open(history_file) as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_nba_line_history(self, snapshot: Dict):
        """Save current odds as a timestamped snapshot."""
        history_file = NBA_LINE_HISTORY_DIR / f"nba_lines_{self.date_compact}.json"
        existing = self.load_nba_line_history()

        timestamp = datetime.now().strftime("%H:%M")
        existing[timestamp] = snapshot

        with open(history_file, "w") as f:
            json.dump(existing, f, indent=2, default=str)

    def update_nba_line_history(self):
        """Snapshot current odds and save to line history."""
        snapshot = {}
        for game in self.games:
            odds = game.get("odds", {}).get("consensus", {})
            if not odds:
                continue
            key = f"{game['away']['name']} @ {game['home']['name']}"
            snapshot[key] = {
                "spread": odds.get("spread"),
                "total": odds.get("total"),
                "away_ml": odds.get("away_ml"),
                "home_ml": odds.get("home_ml"),
            }

        if snapshot:
            self.save_nba_line_history(snapshot)
            print(f"  Line history snapshot saved ({len(snapshot)} games)")

    def calculate_nba_line_movement(self):
        """Calculate line movement by comparing earliest snapshot to current odds."""
        history = self.load_nba_line_history()
        if len(history) < 2:
            return  # Need at least 2 snapshots to measure movement

        timestamps = sorted(history.keys())
        opening = history[timestamps[0]]
        current = history[timestamps[-1]]

        for game in self.games:
            key = f"{game['away']['name']} @ {game['home']['name']}"
            open_odds = opening.get(key, {})
            curr_odds = current.get(key, {})

            if not open_odds or not curr_odds:
                continue

            open_spread = open_odds.get("spread")
            curr_spread = curr_odds.get("spread")
            open_total = open_odds.get("total")
            curr_total = curr_odds.get("total")

            movement = {}
            if open_spread is not None and curr_spread is not None:
                movement["spread_open"] = open_spread
                movement["spread_current"] = curr_spread
                movement["spread_movement"] = round(curr_spread - open_spread, 1)

            if open_total is not None and curr_total is not None:
                movement["total_open"] = open_total
                movement["total_current"] = curr_total
                movement["total_movement"] = round(curr_total - open_total, 1)

            if movement:
                game["line_movement"] = movement

        moved = sum(1 for g in self.games if g.get("line_movement"))
        if moved:
            print(f"  Line movement calculated for {moved} games")

    # =========================================================================
    # TEAM TIERS
    # =========================================================================
    def assign_team_tiers(self):
        """Assign quality tiers to all teams based on net rating + win%."""
        from nba.nba_team_mappings import get_team_tier

        for team_name, data in self.teams.items():
            net_rtg = data.get("net_rating", data.get("adj_em", 0)) or 0
            record = data.get("record", "0-0")
            try:
                parts = record.split("-")
                w, l = int(parts[0]), int(parts[1])
                win_pct = w / (w + l) if (w + l) > 0 else 0.5
            except (ValueError, IndexError):
                win_pct = data.get("win_pct", 0.5)

            data["tier"] = get_team_tier(net_rtg, win_pct)
            data["win_pct"] = round(win_pct, 3)

    # =========================================================================
    # MAIN RUN
    # =========================================================================
    def run(self, date_str: str = None) -> Dict:
        """Full scraping pipeline."""
        if date_str:
            self.date_str = date_str
            self.date_compact = date_str.replace("-", "")

        print(f"\n{'='*60}")
        print(f"NBA DATA SCRAPER - {self.date_str}")
        print(f"{'='*60}\n")

        # 1. Schedule
        self.scrape_espn_schedule()
        if not self.games:
            print("  No games found for today")

        # 2. ESPN team stats (fallback/supplement - runs first)
        self.scrape_espn_team_stats()

        # 3. nba_api advanced stats (primary source - overwrites ESPN)
        self.scrape_nba_api_stats()

        # 3b. Rolling stats (L10, L20)
        self.scrape_nba_api_rolling_stats()

        # 3c. Home/Away splits
        self.scrape_nba_api_location_splits()

        # 3d. Bench depth stats
        self.scrape_nba_api_depth_stats()

        # 4. Odds
        self.scrape_odds()

        # 4b. Line movement tracking
        self.update_nba_line_history()
        self.calculate_nba_line_movement()

        # 5. Injuries
        self.scrape_injuries()

        # 6. Trade log
        self.load_trade_log()

        # 7. Rest / B2B / form
        self.calculate_rest_and_form()

        # 8. Assign tiers
        self.assign_team_tiers()

        # Build output
        output = {
            "date": self.date_str,
            "scraped_at": datetime.now().isoformat(),
            "games_count": len(self.games),
            "teams_count": len(self.teams),
            "games": self.games,
            "teams": self.teams,
            "metadata": {
                "sources_used": {
                    "espn_schedule": len(self.games) > 0,
                    "espn_stats": any("espn" in t.get("data_sources", []) for t in self.teams.values()),
                    "nba_api": any("nba_api" in t.get("data_sources", []) for t in self.teams.values()),
                    "odds_api": any(g.get("odds", {}).get("consensus") for g in self.games),
                    "injuries": any(t.get("injuries") for t in self.teams.values()),
                },
            },
        }

        # Save
        outfile = DATA_DIR / f"nba_data_{self.date_compact}.json"
        with open(outfile, "w") as f:
            json.dump(output, f, indent=2, default=str)

        print(f"\n  Data saved to: {outfile}")
        print(f"  Games: {len(self.games)} | Teams: {len(self.teams)}")

        return output


def main():
    scraper = NBADataScraper()
    scraper.run()


if __name__ == "__main__":
    main()
