#!/usr/bin/env python3
"""
NBA Basketball - Game Analyzer & Prediction Engine
Efficiency-based model with NBA-specific tuning for injuries, B2B, trades.
"""

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).parent.parent))

from nba.nba_config import (
    DATA_DIR, HOME_COURT_ADVANTAGE, ELITE_HOME_COURTS,
    TIER_LABELS, TIER_CONFIDENCE, SPREAD_EDGE_BY_TIER, TOTAL_EDGE_BY_TIER,
    STAR_THRESHOLDS, MAX_FAVORITE_ODDS, MAX_UNDERDOG_ODDS,
    MAX_SPREAD_THRESHOLD, LARGE_SPREAD_THRESHOLD, LARGE_SPREAD_EXTRA_EDGE,
    FOUR_FACTORS_POINTS, SITUATIONAL_ADJUSTMENTS, INJURY_TIERS,
    AVG_PACE, AVG_EFFICIENCY, AVG_TOTAL, UNITS_BY_STARS,
    ROLLING_WEIGHT_SHORT, ROLLING_WEIGHT_LONG,
    HIGH_ALTITUDE_VENUES, ALTITUDE_THRESHOLD,
    TEAM_TIMEZONES, TIMEZONE_OFFSETS,
    SEASON_WEIGHT, ROLLING_10_WEIGHT, ROLLING_20_WEIGHT, LOCATION_BLEND_WEIGHT,
    LEAGUE_AVG_BENCH_RATIO, DEPTH_FACTOR_MAX,
    LINE_MOVEMENT_CONFIRMATION, LINE_MOVEMENT_CAUTION,
    LINE_MOVEMENT_CONFIRM_THRESHOLD, LINE_MOVEMENT_CAUTION_THRESHOLD,
    ALL_STAR_BREAK_END, POST_ALL_STAR_RUST_GAMES, POST_ALL_STAR_TOTAL_ADJ,
    DEFENSIVE_MATCHUP_MAX,
)
from nba.nba_team_mappings import (
    normalize_team_name, get_team_tier, get_conference, same_division,
)


class NBAAnalyzer:
    # Model parameters
    TOTAL_REGRESSION = 0.15      # Light regression toward league average total
    EFFICIENCY_DEFLATOR = 0.82   # Regress more to reduce extreme predictions
    TEMPO_TOTAL_FACTOR = 0.5     # Pace adjustment factor
    SPREAD_STD_DEV = 10.5        # Tighter than NCAA (11.0)

    def __init__(self, data: Dict):
        self.data = data
        self.teams = data.get("teams", {})
        self.games = data.get("games", [])
        self.date = data.get("date", datetime.now().strftime("%Y-%m-%d"))

    # =========================================================================
    # HELPERS
    # =========================================================================
    def get_team_data(self, team_name: str) -> Dict:
        """Get team data with fallback for name variants."""
        team = self.teams.get(team_name, {})
        if team:
            return team
        canonical = normalize_team_name(team_name)
        return self.teams.get(canonical, {})

    def get_home_court_advantage(self, home_team: str, neutral: bool = False) -> float:
        if neutral:
            return 0.0
        return ELITE_HOME_COURTS.get(home_team, HOME_COURT_ADVANTAGE)

    def parse_record(self, record_str: str) -> Tuple[int, int, float]:
        if not record_str:
            return 0, 0, 0.5
        import re
        match = re.match(r'(\d+)-(\d+)', str(record_str))
        if match:
            w, l = int(match.group(1)), int(match.group(2))
            total = w + l
            return w, l, w / total if total > 0 else 0.5
        return 0, 0, 0.5

    def get_game_tier(self, away_data: Dict, home_data: Dict) -> int:
        """Get game quality tier (worst of the two teams)."""
        t1 = away_data.get("tier", 4)
        t2 = home_data.get("tier", 4)
        return max(t1, t2)

    def spread_to_win_prob(self, spread: float) -> float:
        """Convert predicted spread (away - home) to away team win probability."""
        return norm.cdf(spread / self.SPREAD_STD_DEV)

    def grade_pick(self, hit_pct: float) -> str:
        """Map hit percentage to letter grade."""
        if hit_pct >= 70: return "A+"
        if hit_pct >= 65: return "A"
        if hit_pct >= 62: return "A-"
        if hit_pct >= 59: return "B+"
        if hit_pct >= 56: return "B"
        if hit_pct >= 54: return "B-"
        if hit_pct >= 52: return "C+"
        if hit_pct >= 50: return "C"
        return "D"

    # =========================================================================
    # BLENDED EFFICIENCY HELPER
    # =========================================================================
    def _blend_efficiency(self, team_data: Dict, base_key: str,
                          location: str, avg: float) -> float:
        """Blend season + rolling + location efficiency into one value.

        Args:
            team_data: team dict
            base_key: 'adj_oe' or 'adj_de'
            location: 'home' or 'away' (for location splits)
            avg: league average to fall back on
        Returns:
            Blended efficiency rating
        """
        season_val = team_data.get(base_key, avg)
        if season_val is None:
            season_val = avg

        # Rolling stats
        r10_key = base_key.replace("adj_", "rolling_10_")
        r20_key = base_key.replace("adj_", "rolling_20_")
        r10 = team_data.get(r10_key)
        r20 = team_data.get(r20_key)

        # Blend season + rolling
        if r10 is not None and r20 is not None:
            blended = (season_val * SEASON_WEIGHT +
                       r10 * ROLLING_10_WEIGHT +
                       r20 * ROLLING_20_WEIGHT)
        elif r10 is not None:
            blended = season_val * 0.55 + r10 * 0.45
        elif r20 is not None:
            blended = season_val * 0.60 + r20 * 0.40
        else:
            blended = season_val

        # Location blend
        loc_key = f"{location}_{base_key.split('_')[-1]}"  # home_oe / away_de etc.
        loc_val = team_data.get(loc_key)
        if loc_val is not None:
            blended = blended * (1 - LOCATION_BLEND_WEIGHT) + loc_val * LOCATION_BLEND_WEIGHT

        return blended

    # =========================================================================
    # EXPECTED SCORE CALCULATION
    # =========================================================================
    def calculate_expected_score(self, away_name: str, home_name: str,
                                 neutral: bool = False) -> Dict:
        """Project final score using efficiency model with blended stats."""
        away = self.get_team_data(away_name)
        home = self.get_team_data(home_name)

        # Get blended efficiency ratings
        away_oe = self._blend_efficiency(away, "adj_oe", "away", AVG_EFFICIENCY)
        away_de = self._blend_efficiency(away, "adj_de", "away", AVG_EFFICIENCY)
        home_oe = self._blend_efficiency(home, "adj_oe", "home", AVG_EFFICIENCY)
        home_de = self._blend_efficiency(home, "adj_de", "home", AVG_EFFICIENCY)

        # Tempo (blend season + rolling)
        away_tempo = away.get("adj_tempo", AVG_PACE) or AVG_PACE
        home_tempo = home.get("adj_tempo", AVG_PACE) or AVG_PACE

        # Blend rolling pace if available
        for team, tempo_ref in [(away, "away_tempo"), (home, "home_tempo")]:
            r10_pace = team.get("rolling_10_pace")
            r20_pace = team.get("rolling_20_pace")
            base_tempo = away_tempo if tempo_ref == "away_tempo" else home_tempo
            if r10_pace is not None and r20_pace is not None:
                blended_tempo = (base_tempo * SEASON_WEIGHT +
                                 r10_pace * ROLLING_10_WEIGHT +
                                 r20_pace * ROLLING_20_WEIGHT)
            elif r10_pace is not None:
                blended_tempo = base_tempo * 0.55 + r10_pace * 0.45
            else:
                blended_tempo = base_tempo
            if tempo_ref == "away_tempo":
                away_tempo = blended_tempo
            else:
                home_tempo = blended_tempo

        expected_tempo = (away_tempo + home_tempo) / 2
        # Regress tempo 10% toward mean
        expected_tempo = expected_tempo * 0.9 + AVG_PACE * 0.1

        # Regress base ratings toward mean BEFORE matchup calculation
        d = self.EFFICIENCY_DEFLATOR
        away_oe_r = away_oe * d + AVG_EFFICIENCY * (1 - d)
        away_de_r = away_de * d + AVG_EFFICIENCY * (1 - d)
        home_oe_r = home_oe * d + AVG_EFFICIENCY * (1 - d)
        home_de_r = home_de * d + AVG_EFFICIENCY * (1 - d)

        # Additive efficiency: Team PPP = TeamOE + (OppDE - AVG)
        away_ppp = away_oe_r + (home_de_r - AVG_EFFICIENCY)
        home_ppp = home_oe_r + (away_de_r - AVG_EFFICIENCY)

        # Convert to game scores
        away_score = away_ppp * expected_tempo / 100
        home_score = home_ppp * expected_tempo / 100

        # Home court advantage
        hca = self.get_home_court_advantage(home_name, neutral)
        home_score += hca / 2
        away_score -= hca / 2

        # Predicted spread (negative = away favored)
        predicted_spread = away_score - home_score

        # Totals
        raw_total = away_score + home_score
        tempo_dev = expected_tempo - AVG_PACE
        tempo_adj = tempo_dev * self.TEMPO_TOTAL_FACTOR * 2
        regressed_total = raw_total * (1 - self.TOTAL_REGRESSION) + AVG_TOTAL * self.TOTAL_REGRESSION
        predicted_total = regressed_total + tempo_adj

        return {
            "away_score": round(away_score, 1),
            "home_score": round(home_score, 1),
            "predicted_spread": round(predicted_spread, 1),
            "predicted_total": round(predicted_total, 1),
            "expected_tempo": round(expected_tempo, 1),
            "away_ppp": round(away_ppp, 1),
            "home_ppp": round(home_ppp, 1),
            "hca": round(hca, 1),
        }

    # =========================================================================
    # FOUR FACTORS EDGE
    # =========================================================================
    def calculate_four_factors_edge(self, away_name: str, home_name: str) -> Optional[Dict]:
        """Compare Four Factors matchups (offense vs opposing defense)."""
        away = self.get_team_data(away_name)
        home = self.get_team_data(home_name)

        factors = {}
        total_edge = 0.0
        has_data = False

        # eFG%: Each team's shooting vs opponent's defensive eFG allowed
        away_efg_o = away.get("efg_o")
        home_efg_o = home.get("efg_o")
        away_efg_d = away.get("efg_d")  # opponents shoot this % vs away's defense
        home_efg_d = home.get("efg_d")  # opponents shoot this % vs home's defense

        if away_efg_o and home_efg_o and away_efg_o != 50:
            has_data = True
            # Away offense vs home defense: how much away exceeds what home allows
            away_matchup = away_efg_o - (home_efg_d or 50)
            # Home offense vs away defense: how much home exceeds what away allows
            home_matchup = home_efg_o - (away_efg_d or 50)
            # Positive diff = away has better shooting matchup
            efg_diff = away_matchup - home_matchup
            efg_pts = efg_diff * FOUR_FACTORS_POINTS["efg"]
            factors["efg"] = {"away_o": away_efg_o, "home_o": home_efg_o,
                              "diff": round(efg_diff, 1), "pts": round(efg_pts, 2)}
            total_edge += efg_pts

        # TOV%: Lower is better for offense. Compare each team's turnover rate
        away_tov = away.get("tov_o", 15)
        home_tov = home.get("tov_o", 15)
        if away_tov is not None and home_tov is not None:
            # Positive diff = away turns it over LESS (advantage away)
            tov_diff = home_tov - away_tov
            tov_pts = tov_diff * FOUR_FACTORS_POINTS["tov"]
            factors["tov"] = {"away": away_tov, "home": home_tov,
                              "diff": round(tov_diff, 1), "pts": round(tov_pts, 2)}
            total_edge += tov_pts

        # ORB%: Away offensive rebounding vs home defensive rebounding
        away_orb = away.get("orb", 25)
        home_orb = home.get("orb", 25)
        home_drb = home.get("drb", 75)
        away_drb = away.get("drb", 75)
        if away_orb is not None and home_orb is not None:
            # away_orb vs home's ability to prevent ORB (home_drb)
            # home_orb vs away's ability to prevent ORB (away_drb)
            away_orb_matchup = away_orb - (100 - (home_drb or 75))
            home_orb_matchup = home_orb - (100 - (away_drb or 75))
            orb_diff = away_orb_matchup - home_orb_matchup
            orb_pts = orb_diff * FOUR_FACTORS_POINTS["orb"]
            factors["orb"] = {"away": away_orb, "home": home_orb,
                              "diff": round(orb_diff, 1), "pts": round(orb_pts, 2)}
            total_edge += orb_pts

        # FTR: Away team's FT rate vs home team's opponent FT rate allowed
        away_ftr = away.get("ftr", 25)
        home_ftr = home.get("ftr", 25)
        home_ftrd = home.get("ftrd", 25)  # what home allows opponents
        away_ftrd = away.get("ftrd", 25)  # what away allows opponents
        if away_ftr is not None and home_ftr is not None:
            away_ftr_matchup = away_ftr - (home_ftrd or 25)
            home_ftr_matchup = home_ftr - (away_ftrd or 25)
            ftr_diff = away_ftr_matchup - home_ftr_matchup
            ftr_pts = ftr_diff * FOUR_FACTORS_POINTS["ftr"]
            factors["ftr"] = {"away": away_ftr, "home": home_ftr,
                              "diff": round(ftr_diff, 1), "pts": round(ftr_pts, 2)}
            total_edge += ftr_pts

        if not has_data:
            return None

        return {
            "factors": factors,
            "total_edge": round(total_edge, 2),
            "favors": "AWAY" if total_edge > 0 else "HOME" if total_edge < 0 else "EVEN",
        }

    # =========================================================================
    # INJURY IMPACT
    # =========================================================================
    def calculate_injury_impact(self, team_name: str) -> Tuple[float, List[str]]:
        """Calculate point impact of injuries for a team."""
        team = self.get_team_data(team_name)
        injuries = team.get("injuries", [])
        if not injuries:
            return 0.0, []

        total_impact = 0.0
        details = []
        starters_out = 0

        for inj in injuries:
            status = inj.get("status", "")
            ppg = inj.get("ppg", 0) or 0
            usage = inj.get("usage_rate", 0.10) or 0.10
            minutes = inj.get("minutes", 0) or 0
            player_name = inj.get("player", "Unknown")

            # Scale impact by status probability
            if status == "Out":
                status_factor = 1.0
            elif status == "Doubtful":
                status_factor = 0.8
            elif status == "Questionable":
                status_factor = 0.4  # ~40% chance of missing
            elif status == "Probable":
                status_factor = 0.1
            else:
                continue

            # Determine tier: use BOTH ppg AND usage (require both thresholds)
            # Walk from highest tier down, pick the best match
            impact = INJURY_TIERS["bench"]["impact"]
            tier_name = "bench"

            for tier in ["superstar", "allstar", "quality_starter", "starter", "rotation", "bench"]:
                criteria = INJURY_TIERS[tier]
                if ppg >= criteria["ppg_min"] and usage >= criteria["usage_min"]:
                    impact = criteria["impact"]
                    tier_name = tier
                    break

            # Apply status probability
            adjusted_impact = impact * status_factor

            if adjusted_impact != 0 and (ppg >= 5 or minutes >= 15):
                total_impact += adjusted_impact
                if ppg >= 10:
                    starters_out += 1
                if status_factor < 1.0:
                    details.append(f"{player_name} ({ppg:.1f} PPG, {tier_name}, {status}) -> {adjusted_impact:+.1f} pts")
                else:
                    details.append(f"{player_name} ({ppg:.1f} PPG, {tier_name}) -> {adjusted_impact:+.1f} pts")

        # Additional penalty for multiple starters out (scales with count)
        if starters_out >= 2:
            extra = SITUATIONAL_ADJUSTMENTS.get("multiple_starters_out", -2.0)
            if starters_out >= 3:
                extra *= 1.25  # -1.25 for 3+ starters
            total_impact += extra
            details.append(f"Multiple starters out ({starters_out}) -> {extra:+.1f} pts")

        # Depth-aware adjustment: deep benches absorb injuries better
        bench_ppg = team.get("bench_ppg")
        starters_ppg = team.get("starters_ppg")
        if bench_ppg and starters_ppg and (bench_ppg + starters_ppg) > 0:
            depth_ratio = bench_ppg / (bench_ppg + starters_ppg)
            # Teams with deeper benches get up to DEPTH_FACTOR_MAX reduction
            depth_advantage = max(0, depth_ratio - LEAGUE_AVG_BENCH_RATIO)
            reduction = min(depth_advantage / LEAGUE_AVG_BENCH_RATIO, 1.0) * DEPTH_FACTOR_MAX
            if reduction > 0 and total_impact < 0:
                old_impact = total_impact
                total_impact *= (1 - reduction)
                details.append(f"Bench depth (ratio {depth_ratio:.2f}) absorbs {reduction*100:.0f}%: {old_impact:+.1f} -> {total_impact:+.1f}")

        # Cap total injury impact at -6 (prevent runaway adjustments)
        total_impact = max(total_impact, -6.0)

        return round(total_impact, 1), details

    # =========================================================================
    # SITUATIONAL ADJUSTMENTS
    # =========================================================================
    def calculate_situational_adjustments(self, away_name: str, home_name: str,
                                          game: Dict) -> Dict:
        """Calculate all situational adjustments."""
        away = self.get_team_data(away_name)
        home = self.get_team_data(home_name)

        total_adj = 0.0
        adjustments = []

        # --- BACK-TO-BACK (the big one in NBA) ---
        away_b2b = away.get("is_back_to_back", False)
        home_b2b = home.get("is_back_to_back", False)

        if away_b2b and home_b2b:
            # Cancel out mostly
            adj = SITUATIONAL_ADJUSTMENTS["both_b2b_cancel"]
            adjustments.append(f"Both teams B2B (mostly cancels): {adj:+.1f}")
        else:
            if away_b2b:
                if away.get("is_second_road_b2b"):
                    adj = SITUATIONAL_ADJUSTMENTS["b2b_second_road"]
                else:
                    adj = SITUATIONAL_ADJUSTMENTS["b2b_road"]
                total_adj += adj  # Negative = hurts away = helps home spread
                adjustments.append(f"Away ({away_name}) on B2B road: {adj:+.1f}")
            if home_b2b:
                adj = SITUATIONAL_ADJUSTMENTS["b2b_home"]
                total_adj -= adj  # Flip sign: home B2B hurts home = away gets boost
                adjustments.append(f"Home ({home_name}) on B2B: {-adj:+.1f} (helps away)")

        # --- REST ADVANTAGE ---
        # Convention: total_adj += X means HELPS AWAY, total_adj -= X means HURTS AWAY
        away_rest = away.get("rest_days", 2)
        home_rest = home.get("rest_days", 2)
        rest_diff = away_rest - home_rest
        if rest_diff >= 3:
            adj = SITUATIONAL_ADJUSTMENTS["rest_advantage_3plus"]
            total_adj += adj  # Away rested = helps away
            adjustments.append(f"Away rest advantage ({rest_diff} days): +{adj:.1f}")
        elif rest_diff >= 2:
            adj = SITUATIONAL_ADJUSTMENTS["rest_advantage_2plus"]
            total_adj += adj
            adjustments.append(f"Away rest advantage ({rest_diff} days): +{adj:.1f}")
        elif rest_diff <= -3:
            adj = SITUATIONAL_ADJUSTMENTS["rest_advantage_3plus"]
            total_adj -= adj  # Home rested = hurts away
            adjustments.append(f"Home rest advantage ({-rest_diff} days): -{adj:.1f}")
        elif rest_diff <= -2:
            adj = SITUATIONAL_ADJUSTMENTS["rest_advantage_2plus"]
            total_adj -= adj
            adjustments.append(f"Home rest advantage ({-rest_diff} days): -{adj:.1f}")

        # --- INJURIES ---
        away_inj_impact, away_inj_details = self.calculate_injury_impact(away_name)
        home_inj_impact, home_inj_details = self.calculate_injury_impact(home_name)

        if away_inj_impact:
            # Away injuries hurt away -> spread goes down (more negative/toward home)
            total_adj += away_inj_impact  # inj_impact is negative, so spread decreases
            adjustments.append(f"Away injuries ({away_name}): {away_inj_impact:+.1f}")
        if home_inj_impact:
            # Home injuries hurt home -> spread goes up (more positive/toward away)
            total_adj -= home_inj_impact  # inj_impact is negative, so -(-X) = +X
            adjustments.append(f"Home injuries ({home_name}): {-home_inj_impact:+.1f} (helps away)")

        # --- TRADE INTEGRATION ---
        away_trade = away.get("recent_trade")
        home_trade = home.get("recent_trade")
        if away_trade and away_trade.get("impact") == "major":
            games_since = away_trade.get("games_since", 999)
            if games_since <= 5:
                adj = SITUATIONAL_ADJUSTMENTS["major_trade_within_5_games"]  # -2.0
                total_adj += adj  # Negative adj hurts away
                adjustments.append(f"Away trade integration ({games_since}g): {adj:+.1f}")
            elif games_since <= 15:
                adj = SITUATIONAL_ADJUSTMENTS["major_trade_within_15_games"]  # -1.0
                total_adj += adj
                adjustments.append(f"Away trade settling ({games_since}g): {adj:+.1f}")

        if home_trade and home_trade.get("impact") == "major":
            games_since = home_trade.get("games_since", 999)
            if games_since <= 5:
                adj = SITUATIONAL_ADJUSTMENTS["major_trade_within_5_games"]  # -2.0
                total_adj -= adj  # -(-2.0) = +2.0, helps away
                adjustments.append(f"Home trade integration ({games_since}g): {-adj:+.1f} (helps away)")
            elif games_since <= 15:
                adj = SITUATIONAL_ADJUSTMENTS["major_trade_within_15_games"]  # -1.0
                total_adj -= adj
                adjustments.append(f"Home trade settling ({games_since}g): {-adj:+.1f} (helps away)")

        # --- RECENT FORM ---
        away_wins10 = away.get("wins_last_10", 5)
        home_wins10 = home.get("wins_last_10", 5)

        if away_wins10 >= 9:
            adj = SITUATIONAL_ADJUSTMENTS["hot_streak_9plus"]  # +2.5
            total_adj += adj  # Hot away = helps away
            adjustments.append(f"Away hot streak ({away_wins10}/10): +{adj:.1f}")
        elif away_wins10 >= 7:
            adj = SITUATIONAL_ADJUSTMENTS["hot_streak_7plus"]  # +1.5
            total_adj += adj
            adjustments.append(f"Away hot ({away_wins10}/10): +{adj:.1f}")

        if home_wins10 >= 9:
            adj = SITUATIONAL_ADJUSTMENTS["hot_streak_9plus"]  # +2.5
            total_adj -= adj  # Hot home = hurts away
            adjustments.append(f"Home hot streak ({home_wins10}/10): -{adj:.1f}")
        elif home_wins10 >= 7:
            adj = SITUATIONAL_ADJUSTMENTS["hot_streak_7plus"]  # +1.5
            total_adj -= adj
            adjustments.append(f"Home hot ({home_wins10}/10): -{adj:.1f}")

        # Cold streaks
        away_streak = away.get("streak", 0)
        home_streak = home.get("streak", 0)
        if away_streak <= -5:
            adj = SITUATIONAL_ADJUSTMENTS["cold_streak_5plus"]  # -2.5
            total_adj += adj  # Negative adj hurts away
            adjustments.append(f"Away cold streak ({away_streak}): {adj:+.1f}")
        elif away_streak <= -3:
            adj = SITUATIONAL_ADJUSTMENTS["cold_streak_3plus"]  # -1.5
            total_adj += adj
            adjustments.append(f"Away cold ({away_streak}): {adj:+.1f}")

        if home_streak <= -5:
            adj = SITUATIONAL_ADJUSTMENTS["cold_streak_5plus"]  # -2.5
            total_adj -= adj  # -(-2.5) = +2.5, helps away
            adjustments.append(f"Home cold streak ({home_streak}): {-adj:+.1f} (helps away)")
        elif home_streak <= -3:
            adj = SITUATIONAL_ADJUSTMENTS["cold_streak_3plus"]  # -1.5
            total_adj -= adj
            adjustments.append(f"Home cold ({home_streak}): {-adj:+.1f} (helps away)")

        # --- ALTITUDE ---
        home_alt = HIGH_ALTITUDE_VENUES.get(home_name, 0)
        away_alt = HIGH_ALTITUDE_VENUES.get(away_name, 0)
        if home_alt >= ALTITUDE_THRESHOLD and away_alt < ALTITUDE_THRESHOLD:
            total_adj -= 1.5  # Altitude hurts visiting (away) team
            adjustments.append(f"Altitude disadvantage for {away_name} ({home_alt} ft): -1.5")

        # --- TRAVEL / TIMEZONE ---
        away_tz = TEAM_TIMEZONES.get(away_name, "ET")
        home_tz = TEAM_TIMEZONES.get(home_name, "ET")
        tz_diff = abs(TIMEZONE_OFFSETS.get(away_tz, 0) - TIMEZONE_OFFSETS.get(home_tz, 0))
        if tz_diff >= 3:
            adj = SITUATIONAL_ADJUSTMENTS["three_timezone"]  # -1.5
            total_adj += adj  # Negative adj hurts away
            adjustments.append(f"Away cross-country travel ({tz_diff} TZ): {adj:+.1f}")
        elif tz_diff >= 2:
            adj = SITUATIONAL_ADJUSTMENTS["cross_country_flight"]
            total_adj -= adj
            adjustments.append(f"Away travel ({tz_diff} TZ): {-adj:+.1f}")

        # --- PLAYOFF RACE / TANKING ---
        away_conf = get_conference(away_name)
        home_conf = get_conference(home_name)
        # Sort all teams in each conference by win%
        for team_name_ctx, team_data_ctx, label in [
            (away_name, away, "Away"), (home_name, home, "Home")
        ]:
            team_conf = get_conference(team_name_ctx)
            team_win_pct = team_data_ctx.get("win_pct", 0.5)
            team_tier = team_data_ctx.get("tier", 3)

            # Find approximate 8th seed win% in conference
            conf_win_pcts = []
            for t_name, t_data in self.teams.items():
                if get_conference(t_name) == team_conf:
                    conf_win_pcts.append(t_data.get("win_pct", 0.5))
            conf_win_pcts.sort(reverse=True)
            eighth_seed_pct = conf_win_pcts[7] if len(conf_win_pcts) >= 8 else 0.5

            # Games behind = rough estimate from win% gap * 82
            games_behind = (eighth_seed_pct - team_win_pct) * 82

            if -3 <= games_behind <= 3 and team_win_pct >= 0.40:
                # Team is fighting for playoff spot
                adj = SITUATIONAL_ADJUSTMENTS["playoff_race_fighting"]
                if label == "Away":
                    total_adj += adj
                else:
                    total_adj -= adj  # fighting home team = hurts away
                adjustments.append(f"{label} ({team_name_ctx}) in playoff race: {adj:+.1f}")
            elif games_behind > 10 and team_tier >= 4:
                # Tanking
                adj = SITUATIONAL_ADJUSTMENTS["tanking"]
                if label == "Away":
                    total_adj += adj  # negative = hurts away
                else:
                    total_adj -= adj  # tanking home = helps away
                adjustments.append(f"{label} ({team_name_ctx}) tanking signal: {adj:+.1f}")

        # --- DIVISION RIVALRY ---
        if same_division(away_name, home_name):
            adj = SITUATIONAL_ADJUSTMENTS["division_rivalry"]
            total_adj += adj  # positive = helps away (tighter games favor underdog road team)
            adjustments.append(f"Division rivalry: +{adj:.1f} (tighter game)")

        return {
            "total_adjustment": round(total_adj, 1),
            "adjustments": adjustments,
            "away_injury_impact": away_inj_impact,
            "home_injury_impact": home_inj_impact,
            "away_injury_details": away_inj_details,
            "home_injury_details": home_inj_details,
        }

    # =========================================================================
    # DEFENSIVE MATCHUP SIGNALS
    # =========================================================================
    def calculate_defensive_matchup_signals(self, away_name: str, home_name: str) -> Dict:
        """Compare shooting efficiency vs defensive efficiency for matchup signal."""
        away = self.get_team_data(away_name)
        home = self.get_team_data(home_name)

        signal = 0.0
        details = []

        # 3PT shooting matchup: team's 3PT% vs opponent's defensive eFG%
        away_3pt = away.get("tp_pct")
        home_3pt = home.get("tp_pct")
        away_efg_d = away.get("efg_d")
        home_efg_d = home.get("efg_d")

        if away_3pt and home_efg_d:
            # Away shooting vs home defense
            away_3pt_edge = away_3pt - (home_efg_d * 0.6)  # rough 3pt component
            home_3pt_edge = 0
            if home_3pt and away_efg_d:
                home_3pt_edge = home_3pt - (away_efg_d * 0.6)

            shooting_diff = (away_3pt_edge - home_3pt_edge) * 0.02
            shooting_diff = max(-DEFENSIVE_MATCHUP_MAX, min(DEFENSIVE_MATCHUP_MAX, shooting_diff))
            signal += shooting_diff
            if abs(shooting_diff) >= 0.1:
                favors = "away" if shooting_diff > 0 else "home"
                details.append(f"Shooting matchup favors {favors}: {shooting_diff:+.2f}")

        return {
            "signal": round(signal, 2),
            "details": details,
        }

    # =========================================================================
    # PICK CONFIDENCE
    # =========================================================================
    def calculate_pick_confidence(self, analysis: Dict) -> float:
        """Score 0-100 for how confident we are in this projection."""
        away_data = analysis.get("away_data", {})
        home_data = analysis.get("home_data", {})
        ff = analysis.get("four_factors", {})
        expected = analysis.get("expected", {})

        score = 50.0

        # 1. Team quality tier
        away_tier = away_data.get("tier", 4)
        home_tier = home_data.get("tier", 4)
        best_tier = min(away_tier, home_tier)
        tier_mult = TIER_CONFIDENCE.get(best_tier, 0.55)
        score += (tier_mult - 0.5) * 40

        # 2. Data quality
        away_sources = away_data.get("data_sources", [])
        home_sources = home_data.get("data_sources", [])
        if "nba_api" in away_sources and "nba_api" in home_sources:
            score += 10
        elif "espn" in away_sources and "espn" in home_sources:
            score += 5

        # 3. Net rating gap (bigger gap = more predictable)
        away_em = away_data.get("adj_em", 0) or 0
        home_em = home_data.get("adj_em", 0) or 0
        gap = abs(away_em - home_em)
        if gap >= 12:
            score += 8
        elif gap >= 8:
            score += 5
        elif gap >= 4:
            score += 2
        elif gap < 2:
            score -= 5

        # 4. Four Factors alignment
        if ff:
            ff_edge = ff.get("total_edge", 0)
            spread = expected.get("predicted_spread", 0)
            if (ff_edge < 0 and spread < 0) or (ff_edge > 0 and spread > 0):
                score += 5  # Four factors agree with efficiency model
            elif abs(ff_edge) > 2 and ((ff_edge < 0 and spread > 0) or (ff_edge > 0 and spread < 0)):
                score -= 5  # Strong disagreement

        # 5. Both teams have reasonable records (not early season)
        away_w, away_l, _ = self.parse_record(away_data.get("record", ""))
        home_w, home_l, _ = self.parse_record(home_data.get("record", ""))
        total_games = away_w + away_l + home_w + home_l
        if total_games < 40:
            score -= 5  # Early season

        return max(0, min(100, round(score, 1)))

    # =========================================================================
    # SPREAD & TOTAL VALUE
    # =========================================================================
    def calculate_spread_value(self, predicted_spread: float, actual_spread: float) -> Dict:
        """Compare model spread to market spread."""
        if actual_spread is None:
            return {"pick_team": "NO_LINE", "value_points": 0, "confidence_stars": 0}

        # edge = predicted spread + away team's line
        # positive = away covers, negative = home covers
        edge = predicted_spread + actual_spread
        abs_edge = abs(edge)

        # Determine pick
        if edge > 1.0:  # Model says away team covers their spread
            pick_team = "AWAY"
        elif edge < -1.0:  # Model says home team covers their spread
            pick_team = "HOME"
        else:
            pick_team = "PASS"

        # Star rating
        stars = 0
        for s, threshold in sorted(STAR_THRESHOLDS.items(), reverse=True):
            if abs_edge >= threshold:
                stars = s
                break

        # Hit probability: probability that edge covers
        hit_pct = round(norm.cdf(abs_edge / self.SPREAD_STD_DEV) * 100, 1)
        grade = self.grade_pick(hit_pct)

        return {
            "pick_team": pick_team,
            "value_points": round(edge, 1),
            "confidence_stars": stars,
            "final_predicted": round(predicted_spread, 1),
            "actual_spread": actual_spread,
            "hit_pct": hit_pct,
            "grade": grade,
        }

    def calculate_total_value(self, predicted_total: float, actual_total: float) -> Dict:
        """Compare model total to market total."""
        if actual_total is None:
            return {"pick": "NO_LINE", "value_points": 0, "confidence_stars": 0}

        edge = predicted_total - actual_total
        abs_edge = abs(edge)

        if edge > 4.0:
            pick = "OVER"
        elif edge < -4.0:
            pick = "UNDER"
        else:
            pick = "PASS"

        stars = 0
        for s, threshold in sorted(STAR_THRESHOLDS.items(), reverse=True):
            if abs_edge >= threshold:
                stars = s
                break

        return {
            "pick": pick,
            "value_points": round(edge, 1),
            "confidence_stars": stars,
            "predicted_total": round(predicted_total, 1),
            "actual_total": actual_total,
        }

    def calculate_moneyline_value(self, predicted_spread: float,
                                    away_ml: int, home_ml: int) -> Dict:
        """Calculate moneyline value."""
        result = {"ml_pick": None, "ml_value": 0, "ml_stars": 0,
                  "away_ml": away_ml, "home_ml": home_ml}

        if away_ml is None or home_ml is None:
            return result

        model_away_prob = self.spread_to_win_prob(predicted_spread)
        model_home_prob = 1 - model_away_prob

        def implied_prob(odds):
            if odds < 0:
                return abs(odds) / (abs(odds) + 100)
            return 100 / (odds + 100)

        away_implied = implied_prob(away_ml)
        home_implied = implied_prob(home_ml)

        away_edge = model_away_prob - away_implied
        home_edge = model_home_prob - home_implied

        if away_edge > home_edge and away_edge > 0.06:
            result["ml_pick"] = "AWAY_ML"
            result["ml_value"] = round(away_edge * 100, 1)
            result["ml_stars"] = min(5, max(1, int(away_edge * 25)))
            result["hit_pct"] = round(model_away_prob * 100, 1)
            result["grade"] = self.grade_pick(result["hit_pct"])
        elif home_edge > 0.06:
            result["ml_pick"] = "HOME_ML"
            result["ml_value"] = round(home_edge * 100, 1)
            result["ml_stars"] = min(5, max(1, int(home_edge * 25)))
            result["hit_pct"] = round(model_home_prob * 100, 1)
            result["grade"] = self.grade_pick(result["hit_pct"])

        # Always include winner ML grade
        winner_prob = max(model_away_prob, model_home_prob) * 100
        result["winner_hit_pct"] = round(winner_prob, 1)
        result["winner_grade"] = self.grade_pick(winner_prob)

        return result

    # =========================================================================
    # FULL GAME ANALYSIS
    # =========================================================================
    def analyze_game(self, game: Dict) -> Dict:
        """Complete analysis for a single game."""
        away_name = game["away"]["name"]
        home_name = game["home"]["name"]
        neutral = game.get("neutral_site", False)

        # Get odds
        odds = game.get("odds", {}).get("consensus", {})
        actual_spread = odds.get("spread")
        actual_total = odds.get("total")
        away_ml = odds.get("away_ml")
        home_ml = odds.get("home_ml")
        away_spread_odds = odds.get("away_spread_odds")
        home_spread_odds = odds.get("home_spread_odds")

        # Core projections
        expected = self.calculate_expected_score(away_name, home_name, neutral)
        four_factors = self.calculate_four_factors_edge(away_name, home_name)
        situational = self.calculate_situational_adjustments(away_name, home_name, game)

        # Defensive matchup signals
        def_matchup = self.calculate_defensive_matchup_signals(away_name, home_name)

        # Adjust predictions with situational factors (cap at ±12)
        sit_adj = situational.get("total_adjustment", 0)
        sit_adj = max(-12.0, min(12.0, sit_adj))
        adjusted_spread = expected["predicted_spread"] + sit_adj

        # Four factors fine-tune
        if four_factors:
            ff_adj = four_factors["total_edge"] * 0.15  # 15% weight
            adjusted_spread += ff_adj

        # Defensive matchup fine-tune
        if def_matchup and def_matchup.get("signal", 0) != 0:
            adjusted_spread += def_matchup["signal"]

        # Cap spread at ±16 (largest NBA lines rarely exceed this)
        adjusted_spread = max(-16.0, min(16.0, adjusted_spread))

        # Line movement signal
        line_movement = game.get("line_movement", {})
        lm_adj = 0.0
        lm_detail = ""
        spread_movement = line_movement.get("spread_movement", 0)
        if spread_movement and actual_spread is not None:
            # Determine model pick direction
            model_pick_away = adjusted_spread > 0
            # Line moving toward away (more positive) = sharp money on away
            line_moving_away = spread_movement > 0

            if model_pick_away == line_moving_away and abs(spread_movement) >= LINE_MOVEMENT_CONFIRM_THRESHOLD:
                lm_adj = LINE_MOVEMENT_CONFIRMATION if model_pick_away else -LINE_MOVEMENT_CONFIRMATION
                lm_detail = f"Line confirms model ({spread_movement:+.1f} pts): {lm_adj:+.1f}"
            elif model_pick_away != line_moving_away and abs(spread_movement) >= LINE_MOVEMENT_CAUTION_THRESHOLD:
                lm_adj = -LINE_MOVEMENT_CAUTION if model_pick_away else LINE_MOVEMENT_CAUTION
                lm_detail = f"Line moves against model ({spread_movement:+.1f} pts): {lm_adj:+.1f}"

        adjusted_spread += lm_adj

        adjusted_total = expected["predicted_total"]
        # Injuries affect totals too (injured star = fewer points)
        inj_total_adj = (situational.get("away_injury_impact", 0) +
                         situational.get("home_injury_impact", 0)) * 0.15
        adjusted_total += inj_total_adj

        # Post-All-Star rust adjustment on totals
        try:
            asb_end = datetime.strptime(ALL_STAR_BREAK_END, "%Y-%m-%d")
            game_date = datetime.strptime(self.date, "%Y-%m-%d")
            days_after_asb = (game_date - asb_end).days
            if 0 <= days_after_asb <= POST_ALL_STAR_RUST_GAMES:
                adjusted_total += POST_ALL_STAR_TOTAL_ADJ
        except (ValueError, TypeError):
            pass

        # Value calculations
        spread_value = self.calculate_spread_value(adjusted_spread, actual_spread)
        spread_value["away_spread_odds"] = away_spread_odds
        spread_value["home_spread_odds"] = home_spread_odds
        total_value = self.calculate_total_value(adjusted_total, actual_total)
        ml_value = self.calculate_moneyline_value(adjusted_spread, away_ml, home_ml)

        away_data = self.get_team_data(away_name)
        home_data = self.get_team_data(home_name)

        analysis = {
            "away_team": away_name,
            "home_team": home_name,
            "away_name": away_name,
            "home_name": home_name,
            "venue": game.get("venue", ""),
            "neutral_site": neutral,
            "away_data": away_data,
            "home_data": home_data,
            "expected": {
                "away_score": round(expected["away_score"] + sit_adj / 2, 0),
                "home_score": round(expected["home_score"] - sit_adj / 2, 0),
                "predicted_spread": round(adjusted_spread, 1),
                "predicted_total": round(adjusted_total, 1),
                "tempo": expected["expected_tempo"],
                "hca": expected["hca"],
            },
            "four_factors": four_factors,
            "defensive_matchup": def_matchup,
            "situational": situational,
            "line_movement": line_movement,
            "line_movement_adj": lm_adj,
            "line_movement_detail": lm_detail,
            "spread_value": spread_value,
            "total_value": total_value,
            "ml_value": ml_value,
        }

        return analysis

    # =========================================================================
    # ANALYZE ALL GAMES
    # =========================================================================
    def analyze_all_games(self) -> List[Dict]:
        """Analyze all games for today."""
        analyses = []
        for game in self.games:
            try:
                analysis = self.analyze_game(game)
                analyses.append(analysis)
            except Exception as e:
                print(f"  ERROR analyzing {game.get('name', '?')}: {e}")
                analyses.append({"error": str(e), "game": game.get("name", "")})
        return analyses

    # =========================================================================
    # REPORT GENERATION
    # =========================================================================
    def generate_report(self, analyses: List[Dict]) -> str:
        """Generate the full picks report."""
        lines = []
        lines.append("=" * 70)
        lines.append(f"NBA BASKETBALL PICKS - {self.date}")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} ET")
        lines.append("=" * 70)
        lines.append("")

        # Collect picks
        spread_picks = []
        totals_picks = []
        moneyline_picks = []
        b2b_alerts = []
        injury_alerts = []

        for analysis in analyses:
            if analysis.get("error"):
                continue

            away = analysis["away_name"]
            home = analysis["home_name"]
            sv = analysis.get("spread_value", {})
            tv = analysis.get("total_value", {})
            ml_data = analysis.get("ml_value", {})
            sit = analysis.get("situational", {})
            expected = analysis.get("expected", {})
            away_data = analysis.get("away_data", {})
            home_data = analysis.get("home_data", {})

            predicted_spread = expected.get("predicted_spread", 0)
            pick_confidence = self.calculate_pick_confidence(analysis)
            game_tier = self.get_game_tier(away_data, home_data)

            # B2B alerts
            if away_data.get("is_back_to_back"):
                b2b_alerts.append(f"{away} on B2B (road) -> {SITUATIONAL_ADJUSTMENTS['b2b_road']:+.1f} pts")
            if home_data.get("is_back_to_back"):
                b2b_alerts.append(f"{home} on B2B (home) -> {SITUATIONAL_ADJUSTMENTS['b2b_home']:+.1f} pts")

            # Injury alerts
            for detail in sit.get("away_injury_details", []):
                injury_alerts.append(f"{away}: {detail}")
            for detail in sit.get("home_injury_details", []):
                injury_alerts.append(f"{home}: {detail}")

            # Winner prediction
            away_ml = ml_data.get("away_ml")
            home_ml = ml_data.get("home_ml")

            if predicted_spread > 1.5:
                # Away team projected to win (away_score > home_score)
                winner, loser = away, home
                margin = abs(predicted_spread)
                winner_ml = away_ml
            elif predicted_spread < -1.5:
                # Home team projected to win
                winner, loser = home, away
                margin = abs(predicted_spread)
                winner_ml = home_ml
            else:
                # Toss-up, lean home
                winner, loser = home, away
                margin = abs(predicted_spread)
                winner_ml = home_ml

            # Moneyline picks
            if winner_ml is not None and margin >= 3:
                odds_ok = (winner_ml >= MAX_FAVORITE_ODDS and
                          (winner_ml <= MAX_UNDERDOG_ODDS or winner_ml < 0))
                if odds_ok:
                    ml_str = f"+{winner_ml}" if winner_ml > 0 else str(winner_ml)
                    moneyline_picks.append({
                        "pick": f"{winner} ML ({ml_str})",
                        "opponent": loser,
                        "margin": margin,
                        "is_underdog": winner_ml > 0,
                        "stars": ml_data.get("ml_stars", 0),
                        "edge": ml_data.get("ml_value", 0),
                        "pick_confidence": pick_confidence,
                        "tier": game_tier,
                        "grade": ml_data.get("winner_grade", ""),
                        "hit_pct": ml_data.get("winner_hit_pct", 50),
                    })

            # Upset ML picks
            ml_pick_type = ml_data.get("ml_pick")
            if ml_pick_type:
                pick_team = away if ml_pick_type == "AWAY_ML" else home
                pick_opp = home if ml_pick_type == "AWAY_ML" else away
                pick_price = away_ml if ml_pick_type == "AWAY_ML" else home_ml
                if pick_price and pick_price > 0 and pick_price <= MAX_UNDERDOG_ODDS:
                    moneyline_picks.append({
                        "pick": f"{pick_team} ML (+{pick_price})",
                        "opponent": pick_opp,
                        "margin": margin,
                        "is_underdog": True,
                        "stars": ml_data.get("ml_stars", 0),
                        "edge": ml_data.get("ml_value", 0),
                        "pick_confidence": pick_confidence,
                        "tier": game_tier,
                        "is_upset": True,
                        "grade": ml_data.get("grade", ""),
                        "hit_pct": ml_data.get("hit_pct", 50),
                    })

            # Spread picks
            if sv.get("pick_team") not in ("PASS", "NO_LINE", None):
                pick_team = away if sv["pick_team"] == "AWAY" else home
                spread = sv["actual_spread"] if sv["pick_team"] == "AWAY" else -sv["actual_spread"]
                edge = abs(sv.get("value_points", 0))
                stars = sv.get("confidence_stars", 0)
                min_edge = SPREAD_EDGE_BY_TIER.get(game_tier, 3.5)

                if edge >= min_edge and abs(spread) <= MAX_SPREAD_THRESHOLD:
                    if abs(spread) > LARGE_SPREAD_THRESHOLD and edge < min_edge + LARGE_SPREAD_EXTRA_EDGE:
                        continue
                    spread_picks.append({
                        "pick": f"{pick_team} {spread:+.1f}",
                        "team": pick_team,
                        "edge": edge, "stars": stars,
                        "model_spread": sv.get("final_predicted", 0),
                        "actual_line": spread,
                        "away_team": away, "home_team": home,
                        "away_score": expected.get("away_score", 0),
                        "home_score": expected.get("home_score", 0),
                        "pick_confidence": pick_confidence,
                        "tier": game_tier,
                        "grade": sv.get("grade", ""),
                        "hit_pct": sv.get("hit_pct", 50),
                    })

            # Total picks
            if tv.get("pick") not in ("PASS", "NO_LINE", None):
                edge = abs(tv.get("value_points", 0))
                min_total_edge = TOTAL_EDGE_BY_TIER.get(game_tier, 7.0)
                if edge >= min_total_edge:
                    totals_picks.append({
                        "pick": f"{tv['pick']} {tv['actual_total']}",
                        "game": f"{away} vs {home}",
                        "predicted": tv.get("predicted_total", 0),
                        "edge": edge, "stars": tv.get("confidence_stars", 0),
                        "pick_confidence": pick_confidence,
                        "tier": game_tier,
                    })

        # =================================================================
        # BUILD REPORT
        # =================================================================

        # TOP PICKS
        all_ranked = []
        for p in spread_picks:
            all_ranked.append({
                "type": "SPREAD", "display": p["pick"],
                "detail": f"Model: {p['model_spread']:+.1f} | Line: {p['actual_line']:+.1f}",
                "score_detail": f"{p['away_team'][:22]} {p['away_score']:.0f} - {p['home_team'][:22]} {p['home_score']:.0f}",
                "confidence": p.get("pick_confidence", 50),
                "edge": p["edge"], "stars": p["stars"], "tier": p["tier"],
                "grade": p.get("grade", ""), "hit_pct": p.get("hit_pct", 50),
            })
        for p in moneyline_picks:
            if p.get("is_upset"):
                all_ranked.append({
                    "type": "ML UPSET", "display": p["pick"],
                    "detail": f"vs {p['opponent']} | Model edge: {p['edge']:.1f}%",
                    "score_detail": "",
                    "confidence": p.get("pick_confidence", 50),
                    "edge": p["edge"], "stars": p["stars"], "tier": p["tier"],
                    "grade": p.get("grade", ""), "hit_pct": p.get("hit_pct", 50),
                })
        all_ranked.sort(key=lambda x: (-x["confidence"], x["tier"], -x["edge"]))
        top_picks = all_ranked[:15]

        lines.append("TOP PICKS (Ranked by Projection Confidence)")
        lines.append("=" * 70)
        lines.append("")

        for i, p in enumerate(top_picks, 1):
            tier_str = TIER_LABELS.get(p["tier"], "?")
            stars_str = "\u2b50" * p["stars"]
            grade_str = f"  [{p['grade']} {p['hit_pct']:.0f}%]" if p.get("grade") else ""
            lines.append(f"   {i:>2}. [{p['type']:<9}] {p['display']} {stars_str}{grade_str}  [{tier_str}]")
            if p["score_detail"]:
                lines.append(f"       Projected: {p['score_detail']}")
            lines.append(f"       {p['detail']}")
            lines.append("")

        # B2B & INJURY ALERTS
        if b2b_alerts or injury_alerts:
            lines.append("B2B & INJURY ALERTS")
            lines.append("=" * 70)
            lines.append("")
            for alert in b2b_alerts:
                lines.append(f"  [B2B] {alert}")

            # Group injuries by team, show significant ones (>= 1.0 pt impact)
            from collections import OrderedDict
            team_injuries = OrderedDict()
            for alert in injury_alerts:
                # Format: "Team Name: Player (PPG, tier) -> -X.X pts"
                parts = alert.split(": ", 1)
                if len(parts) == 2:
                    team = parts[0]
                    detail = parts[1]
                else:
                    team = "Unknown"
                    detail = alert
                team_injuries.setdefault(team, []).append(detail)

            for team, details in team_injuries.items():
                # Show players with >= 1.0 pt impact individually
                significant = []
                minor_count = 0
                minor_total = 0.0
                for d in details:
                    try:
                        impact_str = d.split("-> ")[1].replace(" pts", "")
                        impact = float(impact_str)
                    except (IndexError, ValueError):
                        impact = 0
                    if abs(impact) >= 1.0:
                        significant.append(d)
                    else:
                        minor_count += 1
                        minor_total += impact

                if significant or minor_count > 0:
                    lines.append(f"  [{team}]")
                    for s in significant:
                        lines.append(f"    {s}")
                    if minor_count > 0:
                        lines.append(f"    + {minor_count} minor injuries -> {minor_total:+.1f} pts")
            lines.append("")

        # MONEYLINE PICKS
        lines.append("MONEYLINE PICKS")
        lines.append("=" * 70)
        lines.append("")

        confident_ml = [p for p in moneyline_picks if p["margin"] >= 8 and not p.get("is_upset")]
        solid_ml = [p for p in moneyline_picks if 3 <= p["margin"] < 8 and not p.get("is_upset")]
        upset_ml = [p for p in moneyline_picks if p.get("is_upset")]

        if confident_ml:
            lines.append("**CONFIDENT WINNERS** (8+ pt projected margin)")
            lines.append("")
            for p in sorted(confident_ml, key=lambda x: -x["margin"]):
                tier_str = TIER_LABELS.get(p["tier"], "?")
                grade_str = f"  [{p['grade']} {p['hit_pct']:.0f}%]" if p.get("grade") else ""
                lines.append(f"  >> {p['pick']} vs {p['opponent']}{grade_str}  [{tier_str}]")
                lines.append(f"     Projected margin: {p['margin']:.1f} pts")
            lines.append("")

        if solid_ml:
            lines.append("**SOLID WINNERS** (3-8 pt projected margin)")
            lines.append("")
            for p in sorted(solid_ml, key=lambda x: -x["margin"]):
                tier_str = TIER_LABELS.get(p["tier"], "?")
                grade_str = f"  [{p['grade']} {p['hit_pct']:.0f}%]" if p.get("grade") else ""
                lines.append(f"  >> {p['pick']} vs {p['opponent']}{grade_str}  [{tier_str}]")
            lines.append("")

        if upset_ml:
            lines.append("**PROJECTED UPSETS** (Model picks underdog)")
            lines.append("")
            for p in sorted(upset_ml, key=lambda x: -x["edge"]):
                tier_str = TIER_LABELS.get(p["tier"], "?")
                stars_str = "\u2b50" * p["stars"]
                grade_str = f"  [{p['grade']} {p['hit_pct']:.0f}%]" if p.get("grade") else ""
                lines.append(f"  >> {p['pick']} vs {p['opponent']} {stars_str}{grade_str}  [{tier_str}]")
                lines.append(f"     Model win prob edge: {p['edge']:.1f}%")
            lines.append("")

        # SPREAD PICKS
        lines.append("")
        lines.append("SPREAD PICKS (Against the Spread)")
        lines.append("=" * 70)
        lines.append("")
        lines.append("**MODEL PROJECTIONS vs LINES**")
        lines.append("")

        for p in sorted(spread_picks, key=lambda x: (-x["pick_confidence"], -x["edge"])):
            tier_str = TIER_LABELS.get(p["tier"], "?")
            stars_str = "\u2b50" * p["stars"]
            grade_str = f"  [{p['grade']} {p['hit_pct']:.0f}%]" if p.get("grade") else ""
            lines.append(f"  >> {p['pick']} {stars_str}{grade_str}  [{tier_str}]")
            lines.append(f"     Projected: {p['away_team'][:22]} {p['away_score']:.0f} - {p['home_team'][:22]} {p['home_score']:.0f}")
            lines.append(f"     Model: {p['model_spread']:+.1f} | Line: {p['actual_line']:+.1f} | Edge: {p['edge']:.1f}")

        # TOTALS PICKS
        lines.append("")
        lines.append("")
        lines.append("TOTALS PICKS (Over/Under)")
        lines.append("=" * 70)
        lines.append("")

        overs = [p for p in totals_picks if "OVER" in p["pick"]]
        unders = [p for p in totals_picks if "UNDER" in p["pick"]]

        if overs:
            lines.append("**OVERS**")
            lines.append("")
            for p in sorted(overs, key=lambda x: -x["edge"]):
                tier_str = TIER_LABELS.get(p["tier"], "?")
                stars_str = "\u2b50" * p["stars"]
                lines.append(f"  >> {p['pick']} ({p['game']}) {stars_str}  [{tier_str}]")
                lines.append(f"     Model total: {p['predicted']:.1f} | Edge: {p['edge']:.1f} pts")
            lines.append("")

        if unders:
            lines.append("**UNDERS**")
            lines.append("")
            for p in sorted(unders, key=lambda x: -x["edge"]):
                tier_str = TIER_LABELS.get(p["tier"], "?")
                stars_str = "\u2b50" * p["stars"]
                lines.append(f"  >> {p['pick']} ({p['game']}) {stars_str}  [{tier_str}]")
                lines.append(f"     Model total: {p['predicted']:.1f} | Edge: {p['edge']:.1f} pts")
            lines.append("")

        # SUMMARY
        lines.append("")
        lines.append("-" * 70)
        lines.append("TODAY'S SUMMARY")
        lines.append("-" * 70)
        p5_spreads = sum(1 for p in spread_picks if p["tier"] <= 2)
        lines.append(f"  Top picks: {len(top_picks)}")
        lines.append(f"  Spread picks: {len(spread_picks)} ({p5_spreads} Elite/Playoff)")
        lines.append(f"  Moneyline picks: {len(moneyline_picks)}")
        lines.append(f"  Totals picks: {len(totals_picks)}")
        lines.append("-" * 70)
        lines.append("")

        # DETAILED ANALYSIS
        lines.append("")
        lines.append("=" * 70)
        lines.append("DETAILED GAME ANALYSIS (Reference)")
        lines.append("=" * 70)
        lines.append("")

        for i, analysis in enumerate(analyses, 1):
            if analysis.get("error"):
                continue
            away = analysis["away_name"]
            home = analysis["home_name"]
            away_data = analysis.get("away_data", {})
            home_data = analysis.get("home_data", {})
            expected = analysis.get("expected", {})
            sv = analysis.get("spread_value", {})
            tv = analysis.get("total_value", {})
            sit = analysis.get("situational", {})

            away_record = away_data.get("record", "?")
            home_record = home_data.get("record", "?")

            lines.append(f"## GAME {i}: {away} @ {home}")
            lines.append(f"Venue: {analysis.get('venue', '?')}")
            lines.append("")

            # Team stats
            away_oe = away_data.get("adj_oe", "?")
            away_de = away_data.get("adj_de", "?")
            away_em = away_data.get("adj_em", "?")
            home_oe = home_data.get("adj_oe", "?")
            home_de = home_data.get("adj_de", "?")
            home_em = home_data.get("adj_em", "?")

            lines.append(f"**{away}:** {away_record} | OffRtg: {away_oe} | DefRtg: {away_de} | Net: {away_em}")
            lines.append(f"**{home}:** {home_record} | OffRtg: {home_oe} | DefRtg: {home_de} | Net: {home_em}")
            lines.append("")

            # B2B/Rest
            away_b2b = "YES" if away_data.get("is_back_to_back") else "No"
            home_b2b = "YES" if home_data.get("is_back_to_back") else "No"
            lines.append(f"Rest: {away} {away_data.get('rest_days', '?')}d (B2B: {away_b2b}) | {home} {home_data.get('rest_days', '?')}d (B2B: {home_b2b})")

            # Injuries
            away_inj = away_data.get("injuries", [])
            home_inj = home_data.get("injuries", [])
            if away_inj:
                out_players = [f"{i['player']} ({i.get('ppg', '?')} PPG)" for i in away_inj if i["status"] in ("Out", "Doubtful")]
                if out_players:
                    lines.append(f"Injuries {away}: {', '.join(out_players[:3])}")
            if home_inj:
                out_players = [f"{i['player']} ({i.get('ppg', '?')} PPG)" for i in home_inj if i["status"] in ("Out", "Doubtful")]
                if out_players:
                    lines.append(f"Injuries {home}: {', '.join(out_players[:3])}")

            # Projection
            lines.append(f"\nProjection: {away} {expected.get('away_score', '?'):.0f} - {home} {expected.get('home_score', '?'):.0f}")
            lines.append(f"Predicted spread: {expected.get('predicted_spread', '?'):+.1f} | Total: {expected.get('predicted_total', '?'):.1f}")

            # Situational
            if sit.get("adjustments"):
                lines.append(f"Situational adj: {sit['total_adjustment']:+.1f} pts")
                for adj in sit["adjustments"][:5]:
                    lines.append(f"  - {adj}")

            # Value
            if sv.get("pick_team") not in ("PASS", "NO_LINE", None):
                stars = "\u2b50" * sv.get("confidence_stars", 0)
                if sv["pick_team"] == "AWAY":
                    pick_name = away
                    pick_spread = sv.get("actual_spread", 0)
                else:
                    pick_name = home
                    pick_spread = -sv.get("actual_spread", 0)
                lines.append(f"\nSPREAD: {pick_name} {pick_spread:+.1f} {stars} (edge: {abs(sv.get('value_points', 0)):.1f})")
            if tv.get("pick") not in ("PASS", "NO_LINE", None):
                lines.append(f"TOTAL: {tv.get('pick')} {tv.get('actual_total', '?')} (model: {tv.get('predicted_total', '?'):.1f})")

            lines.append("")
            lines.append("-" * 70)
            lines.append("")

        return "\n".join(lines)


def main():
    today = datetime.now().strftime("%Y%m%d")
    data_file = DATA_DIR / f"nba_data_{today}.json"

    if not data_file.exists():
        print(f"Error: No data file found at {data_file}")
        print("Run nba_scraper.py first")
        return 1

    print(f"Loading data from: {data_file}")
    with open(data_file) as f:
        data = json.load(f)

    analyzer = NBAAnalyzer(data)
    print(f"Analyzing {len(analyzer.games)} games...")
    print(f"Team data available: {len(analyzer.teams)}")

    analyses = analyzer.analyze_all_games()
    report = analyzer.generate_report(analyses)

    outfile = DATA_DIR / f"nba_analysis_{today}.md"
    with open(outfile, "w") as f:
        f.write(report)

    print(f"\nAnalysis saved to: {outfile}")
    print(f"\n{'='*50}")
    print("ANALYSIS COMPLETE")
    print(f"{'='*50}")
    print(f"Games analyzed: {len(analyses)}")

    # Print top picks summary
    spread_picks = [a for a in analyses if not a.get("error") and
                    a.get("spread_value", {}).get("pick_team") not in ("PASS", "NO_LINE", None)]
    strong = [a for a in spread_picks if a.get("spread_value", {}).get("confidence_stars", 0) >= 3]
    print(f"Spread picks: {len(spread_picks)}")
    print(f"Strong picks (3+ stars): {len(strong)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
