#!/usr/bin/env python3
"""
NCAA Basketball Analysis Engine - Enhanced Version
Implements Four Factors, efficiency analysis, and pick generation.

Based on:
- KenPom/BartTorvik efficiency metrics
- Dean Oliver's Four Factors (updated weights)
- Situational adjustments
- Upset prediction criteria
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project directory to path
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from config import (
    DATA_DIR, HOME_COURT_ADVANTAGE, MAX_DAILY_UNITS, ELITE_HOME_COURTS,
    STAR_THRESHOLDS, UNITS_BY_STARS, FOUR_FACTORS_WEIGHTS, FOUR_FACTORS_POINTS,
    SITUATIONAL_ADJUSTMENTS, UPSET_CRITERIA, HIGH_ALTITUDE_VENUES,
    ALTITUDE_THRESHOLD, TEAM_TIMEZONES, TIMEZONE_OFFSETS, LINE_MOVEMENT
)
from team_mappings import normalize_team_name, get_conference_multiplier


class NCAAAnalyzer:
    """Enhanced NCAA Basketball Analysis Engine"""

    # Calibrated values based on D1 averages
    AVG_TEMPO = 67.5  # Slightly lower - typical D1 game
    AVG_EFFICIENCY = 100.0
    AVG_TOTAL = 143.5  # Average D1 total for calibration

    # MAJOR FIX: Increase regression significantly - model was WAY off on totals
    # Previous: 0.60 -> Now: 0.75 (regress 75% toward mean)
    TOTAL_REGRESSION = 0.75

    # MAJOR FIX: Reduce efficiency impact - stats are inflated for weak teams
    # Previous: 0.85 -> Now: 0.70
    EFFICIENCY_DEFLATOR = 0.70

    # MAJOR FIX: Reduce tempo impact on totals (was over-predicting)
    # Previous: 0.8 -> Now: 0.4
    TEMPO_TOTAL_FACTOR = 0.4

    # Strength of schedule thresholds
    SOS_ELITE_THRESHOLD = 0.03  # Top ~15% SOS
    SOS_WEAK_THRESHOLD = -0.03  # Bottom ~15% SOS

    # NEW: Team quality thresholds - don't bet on bad teams
    MIN_WIN_PCT_FOR_UNDERDOG_ML = 0.40  # Don't bet ML on teams below .400
    MIN_WIN_PCT_FOR_SPREAD_PICK = 0.30  # Don't recommend spreads for very bad teams

    # NEW: Weak conference list - apply extra regression
    WEAK_CONFERENCES = ['SWAC', 'MEAC', 'Southland', 'Big South', 'A-Sun', 'WAC', 'Summit']
    MID_MAJOR_CONFERENCES = ['Southern', 'Big Sky', 'Horizon', 'CAA', 'Sun Belt', 'MAC', 'OVC', 'MVC']

    def __init__(self, data: Dict):
        self.data = data
        self.teams = data.get('teams', {})
        self.games = data.get('games', [])
        self.date = data.get('date', datetime.now().strftime('%Y-%m-%d'))

    # =========================================================================
    # HELPER FUNCTIONS
    # =========================================================================

    def get_team_data(self, team_name: str) -> Dict:
        """Get team data with fallbacks for missing values"""
        team = self.teams.get(team_name, {})

        if not team or not team.get('record'):
            # Try normalized name
            normalized = normalize_team_name(team_name)
            normalized_team = self.teams.get(normalized, {})
            if normalized_team and normalized_team.get('record'):
                team = normalized_team

        if not team or not team.get('record'):
            # Try stripping mascot suffixes (e.g., "VMI Keydets" -> "VMI")
            # But be careful: "Kansas City Roos" should NOT become "Kansas"
            # Only use first word if it's not a separate major team

            # List of first words that are ALSO separate major teams - don't use as fallback
            AMBIGUOUS_FIRST_WORDS = {
                'kansas', 'florida', 'miami', 'texas', 'ohio', 'georgia',
                'michigan', 'indiana', 'virginia', 'north', 'south', 'west',
                'new', 'san', 'saint', 'st', 'utah', 'oregon', 'washington',
                'arizona', 'colorado', 'kentucky', 'tennessee', 'alabama',
                'mississippi', 'louisiana', 'iowa', 'minnesota', 'wisconsin',
                'illinois', 'central', 'eastern', 'western', 'northern', 'southern'
            }

            # Two-word combinations that are separate teams - don't use as fallback
            AMBIGUOUS_TWO_WORDS = {
                'north carolina', 'south carolina', 'south dakota', 'north dakota',
                'west virginia', 'south florida', 'north texas', 'east carolina',
                'north carolina state', 'san diego', 'san jose', 'saint louis',
                'florida state', 'georgia state', 'texas state', 'ohio state',
                'michigan state', 'arizona state', 'oregon state', 'washington state',
                'penn state', 'iowa state', 'kansas state', 'mississippi state',
                'new mexico', 'new orleans', 'central florida', 'eastern kentucky',
                'western kentucky', 'northern iowa', 'southern illinois'
            }

            words = team_name.split() if team_name else []
            if len(words) >= 2:
                first_word = words[0].lower()

                if first_word not in AMBIGUOUS_FIRST_WORDS:
                    # Safe to try first word as short name
                    short_name = words[0]
                    short_team = self.teams.get(short_name, {})
                    if short_team and short_team.get('record'):
                        # Merge: prefer data with record
                        merged = {**team, **short_team} if team else short_team
                        team = merged
                else:
                    # Try two words instead (e.g., "Kansas City" from "Kansas City Roos")
                    # But check if two words is also a separate team
                    if len(words) >= 3:
                        two_word_name = ' '.join(words[:2])
                        two_word_lower = two_word_name.lower()

                        # Don't use if the two-word name is a separate major team
                        if two_word_lower not in AMBIGUOUS_TWO_WORDS:
                            two_word_team = self.teams.get(two_word_name, {})
                            if two_word_team and two_word_team.get('record'):
                                merged = {**team, **two_word_team} if team else two_word_team
                                team = merged
                        # else: For cases like "North Carolina A&T", we can't safely shorten
                        # The team name should be properly mapped in team_mappings.py

        return team

    def parse_record(self, record_str: str) -> Tuple[int, int, float]:
        """Parse W-L record string"""
        if not record_str:
            return 0, 0, 0.5
        import re
        match = re.match(r'(\d+)-(\d+)', str(record_str))
        if match:
            wins, losses = int(match.group(1)), int(match.group(2))
            total = wins + losses
            win_pct = wins / total if total > 0 else 0.5
            return wins, losses, win_pct
        return 0, 0, 0.5

    def get_home_court_advantage(self, home_team: str, neutral: bool = False) -> float:
        """Get home court advantage, accounting for elite venues"""
        if neutral:
            return 0.0
        return ELITE_HOME_COURTS.get(home_team, HOME_COURT_ADVANTAGE)

    def assess_team_quality(self, team_data: Dict, team_name: str) -> Dict:
        """
        Assess team quality to filter out bad picks.
        Returns quality metrics and flags.
        """
        record = team_data.get('record', '')
        wins, losses, win_pct = self.parse_record(record)
        total_games = wins + losses

        # Get conference
        conference = team_data.get('conference', '')

        # Get ranking/efficiency
        adj_em = team_data.get('adj_em', 0) or 0
        kenpom_rank = team_data.get('kenpom_rank') or team_data.get('torvik_rank') or 999

        # Recent form
        streak = team_data.get('streak', 0)
        last_10_wins = team_data.get('last_10_wins', 5)

        # Quality flags
        is_weak_conference = conference in self.WEAK_CONFERENCES
        is_mid_major = conference in self.MID_MAJOR_CONFERENCES
        is_losing_team = win_pct < 0.40
        is_very_bad = win_pct < 0.30 or adj_em < -10
        is_cold = streak <= -4 or last_10_wins <= 2
        is_good_team = win_pct >= 0.60 and adj_em > 5
        is_elite = kenpom_rank <= 50 and win_pct >= 0.65

        # Calculate quality score (0-100)
        quality_score = 50  # Start at neutral
        quality_score += (win_pct - 0.5) * 50  # Win pct impact
        quality_score += min(max(adj_em, -20), 20) * 1.5  # Efficiency impact (capped)
        quality_score -= 10 if is_weak_conference else 0
        quality_score -= 5 if is_mid_major else 0
        quality_score -= 15 if is_cold else 0
        quality_score = max(0, min(100, quality_score))

        return {
            'win_pct': win_pct,
            'wins': wins,
            'losses': losses,
            'total_games': total_games,
            'adj_em': adj_em,
            'kenpom_rank': kenpom_rank,
            'conference': conference,
            'is_weak_conference': is_weak_conference,
            'is_mid_major': is_mid_major,
            'is_losing_team': is_losing_team,
            'is_very_bad': is_very_bad,
            'is_cold': is_cold,
            'is_good_team': is_good_team,
            'is_elite': is_elite,
            'quality_score': quality_score,
        }

    def get_conference_regression_factor(self, conf1: str, conf2: str) -> float:
        """
        Get additional regression factor based on conference quality.
        Weak conference games need MORE regression toward the mean.
        Power 5 games should trust efficiency more.

        Returns: regression factor (lower = trust efficiency more)
        """
        both_weak = conf1 in self.WEAK_CONFERENCES and conf2 in self.WEAK_CONFERENCES
        one_weak = conf1 in self.WEAK_CONFERENCES or conf2 in self.WEAK_CONFERENCES
        both_mid = conf1 in self.MID_MAJOR_CONFERENCES and conf2 in self.MID_MAJOR_CONFERENCES

        # Power 5 conferences - trust efficiency more
        power_5 = ['SEC', 'Big Ten', 'Big 12', 'ACC', 'Pac-12', 'Big East']
        both_power5 = conf1 in power_5 and conf2 in power_5
        one_power5 = conf1 in power_5 or conf2 in power_5

        if both_weak:
            return 0.80  # Regress 80% to mean for SWAC/MEAC type games
        elif one_weak:
            return 0.75
        elif both_mid:
            return 0.70
        elif both_power5:
            return 0.55  # Trust Power 5 efficiency more
        elif one_power5:
            return 0.60
        else:
            return 0.65  # Default regression

    # =========================================================================
    # CORE CALCULATIONS
    # =========================================================================

    def calculate_expected_score(self, away_name: str, home_name: str,
                                  neutral: bool = False) -> Optional[Dict]:
        """
        Calculate expected score using efficiency metrics.

        Formula:
        Team PPP = (Team AdjO × Opponent AdjD) / 100
        Expected Score = PPP × Expected Tempo

        Includes regression to mean for totals to avoid over-prediction bias.
        """
        away = self.get_team_data(away_name)
        home = self.get_team_data(home_name)

        if not away and not home:
            return None

        # Get efficiency ratings (prefer BartTorvik, fall back to ESPN, then SR)
        away_adj_oe = away.get('adj_oe') or away.get('sr_off_rtg') or self.AVG_EFFICIENCY
        away_adj_de = away.get('adj_de') or away.get('sr_def_rtg') or self.AVG_EFFICIENCY
        home_adj_oe = home.get('adj_oe') or home.get('sr_off_rtg') or self.AVG_EFFICIENCY
        home_adj_de = home.get('adj_de') or home.get('sr_def_rtg') or self.AVG_EFFICIENCY

        # CRITICAL: If defensive efficiency looks like a placeholder (exactly 100.0),
        # estimate from points allowed per game if available
        if away_adj_de == 100.0 and away.get('pts_allowed_per_game'):
            ppg_allowed = away.get('pts_allowed_per_game', 70)
            tempo = away.get('adj_tempo') or self.AVG_TEMPO
            away_adj_de = round((ppg_allowed / tempo) * 100, 1)

        if home_adj_de == 100.0 and home.get('pts_allowed_per_game'):
            ppg_allowed = home.get('pts_allowed_per_game', 70)
            tempo = home.get('adj_tempo') or self.AVG_TEMPO
            home_adj_de = round((ppg_allowed / tempo) * 100, 1)

        # Get tempo - use lower of two teams (slower team controls pace)
        away_tempo = away.get('adj_tempo') or away.get('sr_pace') or self.AVG_TEMPO
        home_tempo = home.get('adj_tempo') or home.get('sr_pace') or self.AVG_TEMPO

        # Expected tempo is average, but regress toward mean
        raw_tempo = (away_tempo + home_tempo) / 2.0
        expected_tempo = raw_tempo * 0.9 + self.AVG_TEMPO * 0.1  # 10% regression to mean

        # Calculate expected efficiency using ADDITIVE formula
        # This avoids the inflation problem of multiplicative approach
        # Expected PPP = Team AdjOE + (Opp AdjDE - 100)
        # This adds the opponent's defensive weakness/strength to team's offense
        away_ppp = away_adj_oe + (home_adj_de - self.AVG_EFFICIENCY)
        home_ppp = home_adj_oe + (away_adj_de - self.AVG_EFFICIENCY)

        # Apply efficiency deflator (efficiency metrics inflate actual scoring)
        away_ppp = self.AVG_EFFICIENCY + (away_ppp - self.AVG_EFFICIENCY) * self.EFFICIENCY_DEFLATOR
        home_ppp = self.AVG_EFFICIENCY + (home_ppp - self.AVG_EFFICIENCY) * self.EFFICIENCY_DEFLATOR

        # Calculate expected scores (per-game)
        away_score = away_ppp * expected_tempo / 100.0
        home_score = home_ppp * expected_tempo / 100.0

        # Calculate efficiency gap for HCA scaling
        efficiency_gap = abs(away_adj_oe - home_adj_oe) + abs(away_adj_de - home_adj_de)
        # Approximate AdjEM gap (offense + defense differences)
        adj_em_gap = abs((away_adj_oe - away_adj_de) - (home_adj_oe - home_adj_de))

        # Home court advantage - scaled down for large mismatches
        base_hca = self.get_home_court_advantage(home_name, neutral)

        # When talent gap > 15 AdjEM, home court matters less
        if adj_em_gap > 25:
            hca_scale = 0.50
        elif adj_em_gap > 20:
            hca_scale = 0.67
        elif adj_em_gap > 15:
            hca_scale = 0.80
        else:
            hca_scale = 1.0

        hca = base_hca * hca_scale
        home_score += hca / 2
        away_score -= hca / 2

        # Predicted spread (from away's perspective: positive = underdog)
        predicted_spread = home_score - away_score

        # Raw predicted total
        raw_total = away_score + home_score

        # TEMPO ADJUSTMENT: Fast-paced games should have higher totals
        # Calculate how many possessions above/below average this game should have
        tempo_deviation = expected_tempo - self.AVG_TEMPO
        tempo_total_adj = tempo_deviation * self.TEMPO_TOTAL_FACTOR * 2  # *2 for both teams

        # CONFERENCE-ADJUSTED REGRESSION: Weak conferences need MORE regression
        # Their efficiency stats are inflated from playing weak opponents
        away_conf = away.get('conference', '')
        home_conf = home.get('conference', '')
        regression_factor = self.get_conference_regression_factor(away_conf, home_conf)

        # TOTAL REGRESSION: Regress toward league average to avoid over bias
        # Use conference-adjusted regression factor instead of fixed value
        regressed_total = raw_total * (1 - regression_factor) + self.AVG_TOTAL * regression_factor

        # Apply tempo adjustment after regression (reduced impact)
        predicted_total = regressed_total + tempo_total_adj

        # Adjust individual scores proportionally to match regressed total
        total_scale = predicted_total / raw_total if raw_total > 0 else 1.0
        away_score_adj = away_score * total_scale
        home_score_adj = home_score * total_scale

        return {
            'away_score': round(away_score_adj, 1),
            'home_score': round(home_score_adj, 1),
            'predicted_spread': round(predicted_spread, 1),  # Keep original spread
            'predicted_total': round(predicted_total, 1),
            'raw_total': round(raw_total, 1),  # For debugging
            'expected_tempo': round(expected_tempo, 1),
            'tempo_total_adj': round(tempo_total_adj, 1),  # Tempo impact on total
            'away_ppp': round(away_ppp, 3),
            'home_ppp': round(home_ppp, 3),
            'home_court_adj': hca,
            'away_adj_oe': away_adj_oe,
            'away_adj_de': away_adj_de,
            'home_adj_oe': home_adj_oe,
            'home_adj_de': home_adj_de,
            'away_tempo': away_tempo,
            'home_tempo': home_tempo,
        }

    def calculate_four_factors_edge(self, away_name: str, home_name: str) -> Optional[Dict]:
        """
        Calculate Four Factors differential.

        Updated weights from research:
        - eFG%: 45% (shooting efficiency most important)
        - TOV%: 30% (turnovers very costly)
        - ORB%: 15% (second chances)
        - FTR: 10% (free throws)
        """
        away = self.get_team_data(away_name)
        home = self.get_team_data(home_name)

        if not away and not home:
            return None

        # Get Four Factors (prefer BartTorvik, fall back to SR)
        away_efg_o = away.get('efg_o') or away.get('sr_efg_pct') or 50.0
        away_efg_d = away.get('efg_d') or away.get('sr_opp_efg') or 50.0
        home_efg_o = home.get('efg_o') or home.get('sr_efg_pct') or 50.0
        home_efg_d = home.get('efg_d') or home.get('sr_opp_efg') or 50.0

        away_tov_o = away.get('tov_o') or away.get('sr_tov_pct') or 18.0
        away_tov_d = away.get('tov_d') or away.get('sr_opp_tov') or 18.0
        home_tov_o = home.get('tov_o') or home.get('sr_tov_pct') or 18.0
        home_tov_d = home.get('tov_d') or home.get('sr_opp_tov') or 18.0

        away_orb = away.get('orb') or away.get('sr_orb_pct') or 30.0
        away_drb = away.get('drb') or away.get('sr_drb_pct') or 70.0
        home_orb = home.get('orb') or home.get('sr_orb_pct') or 30.0
        home_drb = home.get('drb') or home.get('sr_drb_pct') or 70.0

        away_ftr = away.get('ftr') or away.get('sr_ft_rate') or 30.0
        away_ftrd = away.get('ftrd') or away.get('sr_opp_ftr') or 30.0
        home_ftr = home.get('ftr') or home.get('sr_ft_rate') or 30.0
        home_ftrd = home.get('ftrd') or home.get('sr_opp_ftr') or 30.0

        # 1. eFG% edge (offense vs opponent's defense)
        away_efg_edge = away_efg_o - home_efg_d
        home_efg_edge = home_efg_o - away_efg_d
        efg_diff = away_efg_edge - home_efg_edge

        # 2. TOV% edge (lower is better for offense)
        away_tov_edge = home_tov_d - away_tov_o  # Positive = away protects ball
        home_tov_edge = away_tov_d - home_tov_o
        tov_diff = away_tov_edge - home_tov_edge

        # 3. ORB% edge
        away_orb_edge = away_orb - (100 - home_drb)
        home_orb_edge = home_orb - (100 - away_drb)
        orb_diff = away_orb_edge - home_orb_edge

        # 4. FTR edge
        away_ftr_edge = away_ftr - home_ftrd
        home_ftr_edge = home_ftr - away_ftrd
        ftr_diff = away_ftr_edge - home_ftr_edge

        # Convert to points using research-based conversions
        efg_points = efg_diff * FOUR_FACTORS_POINTS['efg']
        tov_points = tov_diff * FOUR_FACTORS_POINTS['tov']
        orb_points = orb_diff * FOUR_FACTORS_POINTS['orb']
        ftr_points = ftr_diff * FOUR_FACTORS_POINTS['ftr']

        total_edge = efg_points + tov_points + orb_points + ftr_points

        return {
            'total_edge': round(total_edge, 1),
            'efg_diff': round(efg_diff, 1),
            'efg_points': round(efg_points, 2),
            'tov_diff': round(tov_diff, 1),
            'tov_points': round(tov_points, 2),
            'orb_diff': round(orb_diff, 1),
            'orb_points': round(orb_points, 2),
            'ftr_diff': round(ftr_diff, 1),
            'ftr_points': round(ftr_points, 2),
            # Raw values for reference
            'away_efg_o': away_efg_o,
            'away_efg_d': away_efg_d,
            'home_efg_o': home_efg_o,
            'home_efg_d': home_efg_d,
        }

    def calculate_situational_adjustments(self, away_name: str, home_name: str,
                                           game: Dict) -> Dict:
        """
        Apply comprehensive situational adjustments based on context.
        Includes: rest, travel, form, injuries, altitude, line movement.

        IMPORTANT: When efficiency gap > 15 points, situational factors matter
        less because talent gap is too large to overcome. We scale down adjustments.
        """
        away = self.get_team_data(away_name)
        home = self.get_team_data(home_name)

        # Calculate efficiency gap to determine adjustment scaling
        away_adj_em = away.get('adj_em') or 0
        home_adj_em = home.get('adj_em') or 0
        efficiency_gap = abs(away_adj_em - home_adj_em)

        # Scale down situational adjustments when talent gap is large
        # Gap > 15: reduce to 50%, Gap > 20: reduce to 33%, Gap > 25: reduce to 25%
        if efficiency_gap > 25:
            situational_scale = 0.25
        elif efficiency_gap > 20:
            situational_scale = 0.33
        elif efficiency_gap > 15:
            situational_scale = 0.50
        else:
            situational_scale = 1.0

        adjustments = []
        total_adj = 0.0  # Positive = favors away

        # =====================================================================
        # 1. REST & FATIGUE (HIGH IMPACT)
        # =====================================================================
        away_rest = away.get('rest_days')
        home_rest = home.get('rest_days')
        away_b2b = away.get('is_back_to_back', False)
        home_b2b = home.get('is_back_to_back', False)
        away_fatigue = away.get('fatigue_adjustment', 0)
        home_fatigue = home.get('fatigue_adjustment', 0)

        # Back-to-back adjustments
        if away_b2b:
            adj = SITUATIONAL_ADJUSTMENTS.get('back_to_back_road', -3.5)
            total_adj += adj
            adjustments.append(f"{away_name} on B2B road ({adj:+.1f})")
        if home_b2b:
            adj = SITUATIONAL_ADJUSTMENTS.get('back_to_back', -2.5)
            total_adj -= adj  # Negative for home = subtract from away advantage
            adjustments.append(f"{home_name} on B2B ({-adj:+.1f})")

        # Rest advantage
        if away_rest and home_rest:
            rest_diff = away_rest - home_rest
            if rest_diff >= 5:
                adj = SITUATIONAL_ADJUSTMENTS.get('rest_advantage_5plus', 2.5)
                total_adj += adj
                adjustments.append(f"{away_name} {rest_diff}+ days more rest ({adj:+.1f})")
            elif rest_diff >= 3:
                adj = SITUATIONAL_ADJUSTMENTS.get('rest_advantage_3plus', 1.5)
                total_adj += adj
                adjustments.append(f"{away_name} {rest_diff} days more rest ({adj:+.1f})")
            elif rest_diff <= -5:
                adj = SITUATIONAL_ADJUSTMENTS.get('rest_advantage_5plus', 2.5)
                total_adj -= adj
                adjustments.append(f"{home_name} {-rest_diff}+ days more rest ({-adj:+.1f})")
            elif rest_diff <= -3:
                adj = SITUATIONAL_ADJUSTMENTS.get('rest_advantage_3plus', 1.5)
                total_adj -= adj
                adjustments.append(f"{home_name} {-rest_diff} days more rest ({-adj:+.1f})")

        # Fatigue from heavy schedule
        if away_fatigue != 0:
            total_adj += away_fatigue
            adjustments.append(f"{away_name} schedule fatigue ({away_fatigue:+.1f})")
        if home_fatigue != 0:
            total_adj -= home_fatigue
            adjustments.append(f"{home_name} schedule fatigue ({-home_fatigue:+.1f})")

        # =====================================================================
        # 2. RECENT FORM / MOMENTUM (MEDIUM-HIGH IMPACT)
        # Adjusted by strength of schedule - winning vs bad teams means less
        # =====================================================================
        away_form = away.get('form_adjustment', 0)
        home_form = home.get('form_adjustment', 0)
        away_streak = away.get('streak', 0)
        home_streak = home.get('streak', 0)
        away_l10 = away.get('last_10_record', '')
        home_l10 = home.get('last_10_record', '')

        # Get strength of schedule (BartTorvik/KenPom SOS)
        away_sos = away.get('sos') or away.get('sos_rank', 0) or 0
        home_sos = home.get('sos') or home.get('sos_rank', 0) or 0

        # SOS multiplier: teams with tough schedules get more credit for form
        # Elite SOS (>0.03): 1.3x, Weak SOS (<-0.03): 0.7x
        def sos_multiplier(sos_value):
            if isinstance(sos_value, (int, float)):
                if sos_value > self.SOS_ELITE_THRESHOLD:
                    return 1.3  # Tough schedule - form means more
                elif sos_value < self.SOS_WEAK_THRESHOLD:
                    return 0.7  # Weak schedule - form means less
            return 1.0

        away_sos_mult = sos_multiplier(away_sos)
        home_sos_mult = sos_multiplier(home_sos)

        if away_form != 0:
            adj_form = away_form * away_sos_mult
            total_adj += adj_form
            streak_str = f"W{away_streak}" if away_streak > 0 else f"L{-away_streak}" if away_streak < 0 else ""
            sos_note = " (tough SOS)" if away_sos_mult > 1 else " (weak SOS)" if away_sos_mult < 1 else ""
            adjustments.append(f"{away_name} {away_l10} L10 {streak_str}{sos_note} ({adj_form:+.1f})")
        if home_form != 0:
            adj_form = home_form * home_sos_mult
            total_adj -= adj_form
            streak_str = f"W{home_streak}" if home_streak > 0 else f"L{-home_streak}" if home_streak < 0 else ""
            sos_note = " (tough SOS)" if home_sos_mult > 1 else " (weak SOS)" if home_sos_mult < 1 else ""
            adjustments.append(f"{home_name} {home_l10} L10 {streak_str}{sos_note} ({-adj_form:+.1f})")

        # =====================================================================
        # 3. INJURIES (HIGH IMPACT) - Weight by player PPG/usage
        # =====================================================================
        away_injuries = away.get('injuries', [])
        home_injuries = home.get('injuries', [])

        def calculate_injury_impact(inj: Dict, team_ppg: float = 70.0) -> float:
            """Calculate injury impact based on player stats and position"""
            if inj.get('status') not in ['Out', 'Doubtful']:
                return 0.0

            # Get player PPG if available (default to role-based estimate)
            player_ppg = inj.get('ppg', 0)
            position = inj.get('position', '')

            if player_ppg >= 15:  # Star player (15+ PPG)
                base_adj = -4.0
            elif player_ppg >= 10:  # Key starter (10-15 PPG)
                base_adj = -2.5
            elif player_ppg >= 5:  # Rotation player
                base_adj = -1.5
            else:  # Role-based fallback
                if 'G' in position:
                    base_adj = -2.5  # Guards more impactful
                elif 'F' in position or 'C' in position:
                    base_adj = -2.0
                else:
                    base_adj = -1.5

            # Point guard multiplier (ball handling/playmaking)
            if 'PG' in position or position == 'G':
                base_adj *= 1.2

            return base_adj

        away_team_ppg = away.get('ppg', 70)
        home_team_ppg = home.get('ppg', 70)

        for inj in away_injuries:
            adj = calculate_injury_impact(inj, away_team_ppg)
            if adj != 0:
                total_adj += adj
                ppg_str = f" ({inj.get('ppg', '?')} PPG)" if inj.get('ppg') else ""
                adjustments.append(f"{away_name} {inj['player']}{ppg_str} {inj['status']} ({adj:+.1f})")

        for inj in home_injuries:
            adj = calculate_injury_impact(inj, home_team_ppg)
            if adj != 0:
                total_adj -= adj
                ppg_str = f" ({inj.get('ppg', '?')} PPG)" if inj.get('ppg') else ""
                adjustments.append(f"{home_name} {inj['player']}{ppg_str} {inj['status']} ({-adj:+.1f})")

        # =====================================================================
        # 4. ALTITUDE (LOW-MEDIUM IMPACT)
        # =====================================================================
        home_altitude = HIGH_ALTITUDE_VENUES.get(home_name, 0)
        away_altitude = HIGH_ALTITUDE_VENUES.get(away_name, 0)

        if home_altitude >= ALTITUDE_THRESHOLD and away_altitude < 2000:
            adj = SITUATIONAL_ADJUSTMENTS.get('altitude_adjustment', -1.5)
            total_adj += adj
            adjustments.append(f"{away_name} playing at altitude ({adj:+.1f})")

        # =====================================================================
        # 5. TIMEZONE / TRAVEL (LOW-MEDIUM IMPACT)
        # =====================================================================
        away_tz = TEAM_TIMEZONES.get(away_name, 'ET')
        home_tz = TEAM_TIMEZONES.get(home_name, 'ET')
        tz_diff = abs(TIMEZONE_OFFSETS.get(away_tz, 0) - TIMEZONE_OFFSETS.get(home_tz, 0))

        if tz_diff >= 3:
            adj = SITUATIONAL_ADJUSTMENTS.get('three_timezone_travel', -2.0)
            total_adj += adj
            adjustments.append(f"{away_name} cross-country travel ({adj:+.1f})")
        elif tz_diff >= 2:
            adj = SITUATIONAL_ADJUSTMENTS.get('cross_country_flight', -1.5)
            total_adj += adj
            adjustments.append(f"{away_name} 2+ timezone travel ({adj:+.1f})")

        # =====================================================================
        # 6. LINE MOVEMENT (MEDIUM IMPACT - informational)
        # =====================================================================
        odds = game.get('odds', {})
        if odds:
            # Check for reverse line movement or sharp money indicators
            # This would require opening line data which we can add
            pass

        # =====================================================================
        # 7. CONFERENCE GAME DETECTION & STRENGTH
        # Conference games are typically tighter (teams know each other)
        # =====================================================================
        away_conf = away.get('conference', '')
        home_conf = home.get('conference', '')
        away_mult = get_conference_multiplier(away_conf)
        home_mult = get_conference_multiplier(home_conf)

        # Check if this is a conference game
        is_conference_game = away_conf and home_conf and away_conf == home_conf

        if is_conference_game:
            # Conference games tend to be closer - reduce spread slightly toward favorite
            # But this is informational for now, handled in spread value calculation
            adjustments.append(f"Conference game ({away_conf}) - expect tighter margin")

        if abs(away_mult - home_mult) > 0.2:
            conf_adj = (away_mult - home_mult) * 1.5
            total_adj += conf_adj
            stronger = away_name if away_mult > home_mult else home_name
            adjustments.append(f"{stronger} conference strength ({conf_adj:+.1f})")

        # Pace mismatch
        away_tempo = away.get('adj_tempo') or self.AVG_TEMPO
        home_tempo = home.get('adj_tempo') or self.AVG_TEMPO
        tempo_diff = abs(away_tempo - home_tempo)

        if tempo_diff > 5:
            slower = away_name if away_tempo < home_tempo else home_name
            pace_adj = 0.5 if slower == away_name else -0.5
            total_adj += pace_adj
            adjustments.append(f"{slower} controls pace ({pace_adj:+.1f})")

        # =====================================================================
        # 8. LUCK REGRESSION (from KenPom/BartTorvik)
        # =====================================================================
        away_luck = away.get('luck', 0) or 0
        home_luck = home.get('luck', 0) or 0

        # Teams with high luck (>0.05) tend to regress
        if away_luck > 0.05:
            luck_adj = -away_luck * 10  # Negative adjustment for lucky teams
            total_adj += luck_adj
            adjustments.append(f"{away_name} luck regression ({luck_adj:+.1f})")
        if home_luck > 0.05:
            luck_adj = -home_luck * 10
            total_adj -= luck_adj
            adjustments.append(f"{home_name} luck regression ({-luck_adj:+.1f})")

        # Apply efficiency gap scaling - large talent gaps reduce situational impact
        if situational_scale < 1.0:
            original_adj = total_adj
            total_adj = total_adj * situational_scale
            adjustments.append(f"Efficiency gap {efficiency_gap:.0f} pts - situational impact reduced to {situational_scale:.0%}")

        return {
            'total_adjustment': round(total_adj, 1),
            'adjustments': adjustments,
            'efficiency_gap': efficiency_gap,
            'situational_scale': situational_scale,
        }

    def check_upset_potential(self, away_name: str, home_name: str,
                               away_rank: int, home_rank: int,
                               four_factors: Dict) -> Optional[Dict]:
        """Check for upset potential (primarily for tournament)"""
        # Only check when there's a significant seed/rank difference
        if not away_rank or not home_rank:
            return None

        rank_diff = abs(away_rank - home_rank)
        if rank_diff < 5:
            return None

        away = self.get_team_data(away_name)
        home = self.get_team_data(home_name)

        # Determine favorite and underdog
        if away_rank < home_rank:
            favorite, underdog = away_name, home_name
            fav_data, dog_data = away, home
        else:
            favorite, underdog = home_name, away_name
            fav_data, dog_data = home, away

        upset_flags = []

        # 1. eFG% differential small
        efg_gap = abs(four_factors.get('efg_diff', 10))
        if efg_gap < UPSET_CRITERIA['efg_differential_max']:
            upset_flags.append(f"eFG% gap only {efg_gap:.1f}%")

        # 2. Underdog has strong defense
        dog_rank = dog_data.get('torvik_rank', 999)
        if dog_rank <= UPSET_CRITERIA['underdog_defense_rank']:
            upset_flags.append(f"Underdog ranked #{dog_rank}")

        # 3. Favorite has poor FT%
        fav_ft = fav_data.get('ft_pct', 75) or 75
        if fav_ft < UPSET_CRITERIA['favorite_ft_pct_max']:
            upset_flags.append(f"Favorite FT% only {fav_ft:.1f}%")

        # 4. Underdog forces turnovers
        dog_tov_d = dog_data.get('tov_d', 15) or 15
        if dog_tov_d >= UPSET_CRITERIA['underdog_tov_forced_min']:
            upset_flags.append(f"Underdog forces {dog_tov_d:.1f}% turnovers")

        if len(upset_flags) >= 2:
            return {
                'alert': True,
                'favorite': favorite,
                'underdog': underdog,
                'flags': upset_flags,
                'flags_count': len(upset_flags),
            }

        return None

    def calculate_spread_value(self, predicted_spread: float, actual_spread: float,
                                four_factors_edge: float, situational_adj: float) -> Dict:
        """Calculate betting value on spread"""
        # Final predicted spread (always calculate for display)
        final_predicted = predicted_spread + four_factors_edge + situational_adj

        if actual_spread is None:
            return {
                'pick_team': 'NO_LINE',
                'confidence_stars': 0,
                'value_points': 0,
                'final_predicted': round(final_predicted, 1),
                'actual_spread': None,
            }

        # Final predicted spread
        final_predicted = predicted_spread + four_factors_edge + situational_adj

        # Value calculation (positive = away covers, negative = home covers)
        value = actual_spread - final_predicted

        # MAJOR FIX: Higher threshold for spread picks
        # Previous: 2.0 points
        # New: 3.0 points - need more cushion
        if value >= 3.0:
            pick_team = 'AWAY'
        elif value <= -3.0:
            pick_team = 'HOME'
        else:
            pick_team = 'PASS'

        # MAJOR FIX: More conservative star ratings
        # Previous: 4 pts = 5 stars
        # New: 6 pts = 5 stars
        abs_value = abs(value)
        if abs_value >= 6.0:
            stars = 5
        elif abs_value >= 5.0:
            stars = 4
        elif abs_value >= 4.0:
            stars = 3
        elif abs_value >= 3.5:
            stars = 2
        elif abs_value >= 3.0:
            stars = 1
        else:
            stars = 0

        return {
            'final_predicted': round(final_predicted, 1),
            'actual_spread': actual_spread,
            'value_points': round(value, 1),
            'pick_team': pick_team,
            'confidence_stars': stars if pick_team != 'PASS' else 0,
        }

    def calculate_moneyline_value(self, predicted_spread: float, odds: Dict) -> Dict:
        """
        Calculate moneyline betting value based on implied vs model probability.

        Positive value = potential +EV bet
        """
        if not odds or not odds.get('best_odds'):
            return {'ml_pick': 'NO_LINE', 'ml_value': 0, 'ml_stars': 0}

        best = odds.get('best_odds', {})
        away_ml = best.get('away_ml', {}).get('price') if best.get('away_ml') else None
        home_ml = best.get('home_ml', {}).get('price') if best.get('home_ml') else None

        if away_ml is None or home_ml is None:
            return {'ml_pick': 'NO_LINE', 'ml_value': 0, 'ml_stars': 0}

        def ml_to_implied_prob(ml):
            """Convert American odds to implied probability"""
            if ml > 0:
                return 100 / (ml + 100)
            else:
                return abs(ml) / (abs(ml) + 100)

        def spread_to_win_prob(spread):
            """
            Convert spread to win probability using normal distribution.
            Standard deviation of college basketball scoring margin is ~11 points.
            """
            import math
            # Spread is from away perspective (positive = away is underdog)
            # So away win prob decreases as spread increases
            std_dev = 11.0
            z_score = -spread / std_dev
            # Approximate normal CDF
            win_prob = 0.5 * (1 + math.erf(z_score / math.sqrt(2)))
            return win_prob

        # Calculate implied probabilities from odds
        away_implied = ml_to_implied_prob(away_ml)
        home_implied = ml_to_implied_prob(home_ml)

        # Calculate model win probabilities from spread
        away_model_prob = spread_to_win_prob(predicted_spread)
        home_model_prob = 1 - away_model_prob

        # Calculate edge (model prob - implied prob)
        away_edge = away_model_prob - away_implied
        home_edge = home_model_prob - home_implied

        # Determine best ML bet
        ml_pick = 'PASS'
        ml_value = 0
        ml_stars = 0
        best_book = ''
        best_price = 0

        # MAJOR FIX: Much higher thresholds for ML bets
        # Favorites: Need 8% edge (was 5%)
        # Underdogs: Need 12% edge (was 5%) - underdogs are HARD to pick
        favorite_threshold = 0.08
        underdog_threshold = 0.12

        # Determine if away is underdog based on ML odds
        away_is_underdog = away_ml > 0 if away_ml else False
        home_is_underdog = home_ml > 0 if home_ml else False

        # Apply appropriate threshold
        away_threshold = underdog_threshold if away_is_underdog else favorite_threshold
        home_threshold = underdog_threshold if home_is_underdog else favorite_threshold

        if away_edge >= away_threshold:
            ml_pick = 'AWAY_ML'
            ml_value = away_edge * 100  # Convert to percentage
            best_book = best.get('away_ml', {}).get('book', '')
            best_price = away_ml
        elif home_edge >= home_threshold:
            ml_pick = 'HOME_ML'
            ml_value = home_edge * 100
            best_book = best.get('home_ml', {}).get('book', '')
            best_price = home_ml

        # MAJOR FIX: Much higher thresholds for star ratings
        # Previous: 5% = 1 star, 15% = 5 stars
        # New: 10% = 1 star, 25% = 5 stars (for underdogs)
        is_underdog_pick = (ml_pick == 'AWAY_ML' and away_is_underdog) or (ml_pick == 'HOME_ML' and home_is_underdog)

        if is_underdog_pick:
            # Very conservative star ratings for underdogs
            if ml_value >= 25:
                ml_stars = 5
            elif ml_value >= 20:
                ml_stars = 4
            elif ml_value >= 16:
                ml_stars = 3
            elif ml_value >= 14:
                ml_stars = 2
            elif ml_value >= 12:
                ml_stars = 1
        else:
            # Standard star ratings for favorites
            if ml_value >= 18:
                ml_stars = 5
            elif ml_value >= 14:
                ml_stars = 4
            elif ml_value >= 11:
                ml_stars = 3
            elif ml_value >= 9:
                ml_stars = 2
            elif ml_value >= 8:
                ml_stars = 1

        return {
            'ml_pick': ml_pick,
            'ml_value': round(ml_value, 1),
            'ml_stars': ml_stars,
            'away_ml': away_ml,
            'home_ml': home_ml,
            'away_implied_prob': round(away_implied * 100, 1),
            'home_implied_prob': round(home_implied * 100, 1),
            'away_model_prob': round(away_model_prob * 100, 1),
            'home_model_prob': round(home_model_prob * 100, 1),
            'best_book': best_book,
            'best_price': best_price,
        }

    def calculate_total_value(self, predicted_total: float, actual_total: float) -> Dict:
        """
        Calculate betting value on total.

        MAJOR FIX: Vegas is VERY good at totals - our model was off by 20-30 pts.
        Require MUCH larger deviation before recommending a totals bet.
        """
        if actual_total is None:
            return {
                'pick': 'NO_LINE',
                'confidence_stars': 0,
                'value_points': 0,
            }

        value = predicted_total - actual_total

        # MAJOR FIX: Much higher thresholds for totals
        # Previous: 5+ points
        # New: 8+ points required - Vegas is almost always right on totals
        if value >= 8.0:
            pick = 'OVER'
        elif value <= -8.0:
            pick = 'UNDER'
        else:
            pick = 'PASS'

        abs_value = abs(value)

        # MAJOR FIX: Very conservative star ratings for totals
        # Previous: 8 = 5 stars
        # New: 12+ = 5 stars (almost never happens if we're calibrated right)
        if abs_value >= 12.0:
            stars = 5
        elif abs_value >= 10.0:
            stars = 4
        elif abs_value >= 9.0:
            stars = 3
        elif abs_value >= 8.0:
            stars = 2
        else:
            stars = 0

        return {
            'predicted_total': round(predicted_total, 1),
            'actual_total': actual_total,
            'value_points': round(value, 1),
            'pick': pick,
            'confidence_stars': stars if pick != 'PASS' else 0,
        }

    # =========================================================================
    # MAIN ANALYSIS
    # =========================================================================

    def analyze_game(self, game: Dict) -> Dict:
        """Full analysis for a single game"""
        # Handle both data formats
        if 'away' in game:
            away_name = game['away']['name']
            home_name = game['home']['name']
            away_rank = game['away'].get('rank')
            home_rank = game['home'].get('rank')
            away_record = game['away'].get('record', '')
            home_record = game['home'].get('record', '')
        else:
            away_name = game.get('away_team', '')
            home_name = game.get('home_team', '')
            away_rank = game.get('away_rank')
            home_rank = game.get('home_rank')
            away_record = game.get('away_record', '')
            home_record = game.get('home_record', '')

        neutral = game.get('neutral_site', False)

        # Get odds - handle multiple formats
        actual_spread = None
        actual_total = None
        odds_data = None

        if game.get('odds') and game['odds'].get('consensus'):
            actual_spread = game['odds']['consensus'].get('spread')
            actual_total = game['odds']['consensus'].get('total')
            odds_data = game['odds']
        elif game.get('odds') and game['odds'].get('best_odds'):
            best = game['odds']['best_odds']
            actual_spread = best.get('away_spread', {}).get('spread') if best.get('away_spread') else None
            actual_total = best.get('over', {}).get('total') if best.get('over') else None
            odds_data = game['odds']

        # Fall back to ESPN odds if no Odds API data
        if actual_spread is None and game.get('espn_odds'):
            espn_odds = game['espn_odds']
            actual_total = espn_odds.get('total')

            # Parse ESPN spread string like "WOF -8.5" or "HOU -16.5"
            spread_str = espn_odds.get('spread_details', '')
            if spread_str:
                import re
                match = re.search(r'([A-Z]+)\s*([+-]?\d+\.?\d*)', spread_str)
                if match:
                    fav_abbr = match.group(1)
                    spread_val = float(match.group(2))

                    # Get team abbreviations
                    away_abbr = game.get('away', {}).get('abbreviation', '')
                    home_abbr = game.get('home', {}).get('abbreviation', '')

                    # Determine away spread (positive = away is underdog)
                    if fav_abbr == away_abbr:
                        # Away team is favorite, spread is negative for away
                        actual_spread = spread_val
                    elif fav_abbr == home_abbr:
                        # Home team is favorite, spread is positive for away
                        actual_spread = -spread_val
                    else:
                        # Try partial match
                        if fav_abbr in away_abbr or away_abbr in fav_abbr:
                            actual_spread = spread_val
                        else:
                            actual_spread = -spread_val

        # Last resort fallbacks
        if actual_spread is None:
            actual_spread = game.get('away_spread')
        if actual_total is None:
            actual_total = game.get('total')

        # Get team data
        away_data = self.get_team_data(away_name)
        home_data = self.get_team_data(home_name)

        # Calculate all metrics
        expected = self.calculate_expected_score(away_name, home_name, neutral)
        four_factors = self.calculate_four_factors_edge(away_name, home_name)
        situational = self.calculate_situational_adjustments(away_name, home_name, game)

        if not expected or not four_factors:
            return {
                'error': f"Insufficient data for {away_name} vs {home_name}",
                'away_name': away_name,
                'home_name': home_name,
            }

        # Calculate value
        spread_value = self.calculate_spread_value(
            expected['predicted_spread'],
            actual_spread,
            four_factors['total_edge'],
            situational['total_adjustment']
        )

        total_value = self.calculate_total_value(
            expected['predicted_total'],
            actual_total
        )

        # Check upset potential
        upset = self.check_upset_potential(
            away_name, home_name, away_rank, home_rank, four_factors
        )

        # Calculate moneyline value
        ml_value = self.calculate_moneyline_value(
            spread_value.get('final_predicted', 0),
            odds_data
        )

        # NEW: Assess team quality to filter bad picks
        away_quality = self.assess_team_quality(away_data, away_name)
        home_quality = self.assess_team_quality(home_data, home_name)

        return {
            'game_id': game.get('game_id'),
            'away_name': away_name,
            'home_name': home_name,
            'away_rank': away_rank,
            'home_rank': home_rank,
            'away_record': away_record,
            'home_record': home_record,
            'neutral_site': neutral,
            'venue': game.get('venue', ''),
            'game_time': game.get('date', ''),
            'away_data': away_data,
            'home_data': home_data,
            'away_quality': away_quality,
            'home_quality': home_quality,
            'odds': odds_data,
            'actual_spread': actual_spread,
            'actual_total': actual_total,
            'expected': expected,
            'four_factors': four_factors,
            'situational': situational,
            'spread_value': spread_value,
            'total_value': total_value,
            'ml_value': ml_value,
            'upset_alert': upset,
        }

    def analyze_all_games(self) -> List[Dict]:
        """Analyze all games"""
        analyses = []
        for game in self.games:
            analysis = self.analyze_game(game)
            analyses.append(analysis)
        return analyses

    # =========================================================================
    # REPORT GENERATION
    # =========================================================================

    def generate_report(self, analyses: List[Dict]) -> str:
        """Generate clean, organized betting report by bet type"""
        lines = []

        lines.append("=" * 70)
        lines.append(f"NCAA BASKETBALL PICKS - {self.date}")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M ET')}")
        lines.append("=" * 70)
        lines.append("")

        # =================================================================
        # LINE MOVEMENT ALERTS (Sharp Money Detection)
        # =================================================================
        sharp_action_games = []
        for analysis in analyses:
            if analysis.get('error'):
                continue
            game = None
            for g in self.games:
                if g.get('away', {}).get('name') == analysis.get('away_name'):
                    game = g
                    break
            if game and game.get('line_movement', {}).get('has_sharp_action'):
                lm = game['line_movement']
                sharp_action_games.append({
                    'away': analysis['away_name'],
                    'home': analysis['home_name'],
                    'signals': lm.get('signals', []),
                    'spread_move': lm.get('spread_movement'),
                    'total_move': lm.get('total_movement'),
                    'opening_spread': lm.get('opening_spread'),
                    'current_spread': lm.get('current_spread'),
                })

        if sharp_action_games:
            lines.append("⚡ LINE MOVEMENT ALERTS (Sharp Money Detected)")
            lines.append("=" * 70)
            lines.append("")
            for game in sharp_action_games:
                lines.append(f"**{game['away']} @ {game['home']}**")
                for signal in game['signals']:
                    lines.append(f"  → {signal}")
                if game['opening_spread'] is not None and game['current_spread'] is not None:
                    lines.append(f"  Line: {game['opening_spread']:+.1f} → {game['current_spread']:+.1f}")
                lines.append("")
            lines.append("-" * 70)
            lines.append("")

        # =================================================================
        # COLLECT ALL PICKS BY TYPE
        # =================================================================
        moneyline_picks = []
        spread_picks = []
        totals_picks = []
        avoid_games = []

        for analysis in analyses:
            if analysis.get('error'):
                continue

            away = analysis['away_name']
            home = analysis['home_name']
            sv = analysis.get('spread_value', {})
            tv = analysis.get('total_value', {})
            ml_data = analysis.get('ml_value', {})

            predicted_spread = sv.get('final_predicted', 0)
            away_ml = ml_data.get('away_ml')
            home_ml = ml_data.get('home_ml')

            # Determine predicted winner and confidence
            if predicted_spread < -1.5:
                winner, loser = away, home
                margin = abs(predicted_spread)
                winner_ml = away_ml
                confidence = "HIGH" if margin >= 10 else "MEDIUM" if margin >= 5 else "LOW"
            elif predicted_spread > 1.5:
                winner, loser = home, away
                margin = predicted_spread
                winner_ml = home_ml
                confidence = "HIGH" if margin >= 10 else "MEDIUM" if margin >= 5 else "LOW"
            else:
                # Model shows toss-up - still check for spread/total value!
                winner, loser = home, away  # Default to home
                margin = abs(predicted_spread)
                winner_ml = home_ml
                confidence = "TOSS-UP"

            spread_val = abs(sv.get('value_points', 0))

            # Only add to avoid if no spread value
            if confidence == "TOSS-UP" and spread_val < 3:
                avoid_games.append({
                    'game': f"{away} vs {home}",
                    'reason': "Model shows toss-up, no spread value"
                })
            elif confidence == "LOW" and spread_val < 3:
                avoid_games.append({
                    'game': f"{away} vs {home}",
                    'reason': f"Low confidence ({margin:.1f} pts), no spread value"
                })

            # =============================================================
            # MONEYLINE PICKS (who wins) - Include confident picks
            # =============================================================
            ml_stars = ml_data.get('ml_stars', 0)
            ml_edge = ml_data.get('ml_value', 0)
            ml_pick_type = ml_data.get('ml_pick')  # 'AWAY_ML' or 'HOME_ML'

            # Determine which team the ML pick is for
            if ml_pick_type == 'AWAY_ML':
                ml_pick_team = away
                ml_pick_opp = home
                ml_pick_price = ml_data.get('away_ml')
            elif ml_pick_type == 'HOME_ML':
                ml_pick_team = home
                ml_pick_opp = away
                ml_pick_price = ml_data.get('home_ml')
            else:
                ml_pick_team = None
                ml_pick_price = None

            # Add confident winner picks (model says they win AND reasonable odds)
            # QUALITY FILTER: Winner must have decent AdjEM
            winner_adjem = analysis.get('home' if winner == home else 'away', {}).get('adj_em', 0)
            if winner_adjem is None:
                winner_adjem = 0

            if winner_ml is not None and winner_ml > -500 and confidence in ["HIGH", "MEDIUM"]:
                if winner_adjem >= MIN_ADJEM_TO_BET:
                    ml_str = f"+{winner_ml}" if winner_ml > 0 else str(winner_ml)
                    moneyline_picks.append({
                        'pick': f"{winner} ML ({ml_str})",
                        'opponent': loser,
                        'confidence': confidence,
                        'margin': margin,
                        'edge': ml_edge if ml_pick_team == winner else 0,
                        'stars': ml_stars if ml_pick_team == winner else 0,
                        'is_underdog': False,
                        'adj_em': winner_adjem,
                    })

            # =============================================================
            # HIGH-VALUE UNDERDOG ML (3+ stars, positive odds)
            # MAJOR FIX: Filter out bad teams - don't bet underdogs below .400
            # =============================================================
            away_quality = analysis.get('away_quality', {})
            home_quality = analysis.get('home_quality', {})

            if ml_stars >= 3 and ml_pick_team and ml_pick_price is not None:
                if ml_pick_price > 100:  # Underdog with value
                    # QUALITY CHECK: Don't recommend ML underdogs on bad teams
                    pick_quality = away_quality if ml_pick_team == away else home_quality
                    win_pct = pick_quality.get('win_pct', 0.5)
                    is_very_bad = pick_quality.get('is_very_bad', False)
                    is_cold = pick_quality.get('is_cold', False)

                    # QUALITY FILTER: Underdog must have decent AdjEM
                    ml_pick_adjem = analysis.get('away' if ml_pick_team == away else 'home', {}).get('adj_em', 0)
                    if ml_pick_adjem is None:
                        ml_pick_adjem = 0

                    if ml_pick_adjem < MIN_ADJEM_TO_BET:
                        avoid_games.append({
                            'game': f"{away} vs {home}",
                            'reason': f"Model liked {ml_pick_team} ML but AdjEM too low ({ml_pick_adjem:+.1f})"
                        })
                    # Skip if team is below .400 or very bad or on cold streak
                    elif win_pct < 0.40:
                        avoid_games.append({
                            'game': f"{away} vs {home}",
                            'reason': f"Model liked {ml_pick_team} ML but win% too low ({win_pct:.1%})"
                        })
                    elif is_very_bad:
                        avoid_games.append({
                            'game': f"{away} vs {home}",
                            'reason': f"Model liked {ml_pick_team} ML but team quality too low"
                        })
                    elif is_cold and ml_pick_price > 200:
                        # Allow cold teams only if odds are not too long
                        avoid_games.append({
                            'game': f"{away} vs {home}",
                            'reason': f"Model liked {ml_pick_team} ML but team is cold"
                        })
                    else:
                        ml_str = f"+{ml_pick_price}"
                        # Check if not already added as a winner pick
                        already_added = any(ml_pick_team in p['pick'] for p in moneyline_picks)
                        if not already_added:
                            moneyline_picks.append({
                                'pick': f"{ml_pick_team} ML ({ml_str})",
                                'opponent': ml_pick_opp,
                                'confidence': f"VALUE",
                                'margin': 0,
                                'edge': ml_edge,
                                'stars': ml_stars,
                                'is_underdog': True,
                                'win_pct': win_pct,
                            })

            # =============================================================
            # SPREAD PICKS (against the spread)
            # MAJOR FIX: Add quality filter for spread picks too
            # =============================================================
            if sv.get('pick_team') not in ['PASS', 'NO_LINE', None]:
                pick_team = away if sv['pick_team'] == 'AWAY' else home
                opp_team = home if sv['pick_team'] == 'AWAY' else away
                spread = sv['actual_spread'] if sv['pick_team'] == 'AWAY' else -sv['actual_spread']
                edge = abs(sv.get('value_points', 0))
                stars = sv.get('confidence_stars', 0)

                # Import thresholds from config
                from config import (MAX_SPREAD_THRESHOLD, LARGE_SPREAD_THRESHOLD,
                                   LARGE_SPREAD_EXTRA_EDGE, MIN_ADJEM_TO_BET)

                # QUALITY FILTER: Use AdjEM (Adjusted Efficiency Margin) to filter
                # AdjEM > 0 = above average, AdjEM < -5 = poor team
                pick_data = analysis.get('away' if sv['pick_team'] == 'AWAY' else 'home', {})
                pick_adjem = pick_data.get('adj_em', 0)
                if pick_adjem is None:
                    pick_adjem = 0

                # Skip teams with very low AdjEM (bad teams are unpredictable)
                if pick_adjem < MIN_ADJEM_TO_BET:
                    avoid_games.append({
                        'game': f"{away} vs {home}",
                        'reason': f"{pick_team} AdjEM too low ({pick_adjem:+.1f}) - need > {MIN_ADJEM_TO_BET}"
                    })
                    continue

                # RISK MANAGEMENT: Skip very large spreads (blowout risk)
                if abs(spread) > MAX_SPREAD_THRESHOLD:
                    avoid_games.append({
                        'game': f"{away} vs {home}",
                        'reason': f"Spread too large ({spread:+.1f}) - blowout risk"
                    })
                    continue

                # RISK MANAGEMENT: Require extra edge for large spreads
                if abs(spread) > LARGE_SPREAD_THRESHOLD:
                    required_edge = 3.0 + LARGE_SPREAD_EXTRA_EDGE  # Base 3 + extra
                    if edge < required_edge:
                        avoid_games.append({
                            'game': f"{away} vs {home}",
                            'reason': f"Large spread ({spread:+.1f}) needs {required_edge:.1f}+ edge, only has {edge:.1f}"
                        })
                        continue

                # Quality check for spread picks
                pick_quality = away_quality if sv['pick_team'] == 'AWAY' else home_quality
                is_very_bad = pick_quality.get('is_very_bad', False)
                is_losing_team = pick_quality.get('is_losing_team', False)
                is_weak_conf = pick_quality.get('is_weak_conference', False)
                win_pct = pick_quality.get('win_pct', 0.5)

                # MAJOR FIX: Skip spread picks entirely for very bad teams
                if is_very_bad:
                    avoid_games.append({
                        'game': f"{away} vs {home}",
                        'reason': f"Model liked {pick_team} spread but team is very bad ({win_pct:.0%})"
                    })
                    continue  # Skip this pick entirely

                # Reduce stars for losing teams in weak conferences
                adjusted_stars = stars
                quality_note = ""
                if is_losing_team and is_weak_conf:
                    adjusted_stars = max(1, stars - 2)
                    quality_note = " (reduced: losing team, weak conf)"
                elif is_losing_team:
                    adjusted_stars = max(1, stars - 1)
                    quality_note = " (reduced: losing team)"
                elif is_weak_conf and win_pct < 0.45:
                    adjusted_stars = max(1, stars - 1)
                    quality_note = " (reduced: weak conf)"

                if adjusted_stars >= 3:  # Only include 3+ star spread picks after adjustment
                    # Get predicted scores from expected calculation
                    expected = analysis.get('expected', {})
                    away_score = expected.get('away_score', 0)
                    home_score = expected.get('home_score', 0)

                    spread_picks.append({
                        'pick': f"{pick_team} {spread:+.1f}",
                        'team': pick_team,
                        'opponent': opp_team,
                        'edge': edge,
                        'stars': adjusted_stars,
                        'model_spread': sv.get('final_predicted', 0),
                        'actual_line': spread,
                        'away_team': away,
                        'home_team': home,
                        'away_score': away_score,
                        'home_score': home_score,
                        'quality_note': quality_note,
                    })

            # =============================================================
            # TOTALS PICKS (over/under)
            # =============================================================
            if tv.get('pick') not in ['PASS', 'NO_LINE', None]:
                ou = tv.get('pick')
                actual_total = tv.get('actual_total', 0)
                predicted_total = tv.get('predicted_total', 0)
                edge = abs(tv.get('value_points', 0))
                stars = tv.get('confidence_stars', 0)

                # QUALITY FILTER: At least one team should be decent for totals
                from config import MIN_ADJEM_FOR_TOTALS
                home_adjem = analysis.get('home', {}).get('adj_em', 0) or 0
                away_adjem = analysis.get('away', {}).get('adj_em', 0) or 0

                best_adjem = max(home_adjem, away_adjem)
                if best_adjem < MIN_ADJEM_FOR_TOTALS:
                    continue  # Skip totals for low-quality matchups

                if stars >= 3:  # Only include 3+ star totals picks
                    totals_picks.append({
                        'pick': f"{ou} {actual_total}",
                        'game': f"{away} vs {home}",
                        'predicted': predicted_total,
                        'edge': edge,
                        'stars': stars,
                    })

        # =================================================================
        # SECTION 1: MONEYLINE PICKS (Who Wins)
        # =================================================================
        lines.append("MONEYLINE PICKS")
        lines.append("=" * 70)
        lines.append("")

        # Separate by type
        high_conf_ml = [p for p in moneyline_picks if p['confidence'] == 'HIGH']
        med_conf_ml = [p for p in moneyline_picks if p['confidence'] == 'MEDIUM']
        value_underdogs = [p for p in moneyline_picks if p.get('is_underdog') and p.get('confidence') == 'VALUE']

        if high_conf_ml:
            lines.append("**HIGH CONFIDENCE WINNERS** (10+ pt margin)")
            lines.append("")
            for p in high_conf_ml[:5]:
                lines.append(f"  >> {p['pick']} vs {p['opponent']}")
                lines.append(f"     Model margin: {p['margin']:.1f} pts")
            lines.append("")

        if med_conf_ml:
            lines.append("**MEDIUM CONFIDENCE WINNERS** (5-10 pt margin)")
            lines.append("")
            for p in med_conf_ml[:8]:
                lines.append(f"  >> {p['pick']} vs {p['opponent']}")
            lines.append("")

        if value_underdogs:
            lines.append("**HIGH-VALUE UNDERDOGS** (Line mispriced)")
            lines.append("")
            for p in sorted(value_underdogs, key=lambda x: -x['stars'])[:6]:
                stars = "⭐" * p['stars']
                lines.append(f"  >> {p['pick']} vs {p['opponent']} {stars}")
                lines.append(f"     Edge: {p['edge']:.1f}%")
            lines.append("")

        if not high_conf_ml and not med_conf_ml and not value_underdogs:
            lines.append("No moneyline picks today.")
            lines.append("")

        # =================================================================
        # SECTION 2: SPREAD PICKS (Against the Spread)
        # =================================================================
        lines.append("")
        lines.append("SPREAD PICKS (Against the Spread)")
        lines.append("=" * 70)
        lines.append("")

        # Sort by stars then edge
        spread_picks.sort(key=lambda x: (-x['stars'], -x['edge']))

        if spread_picks:
            lines.append("**MODEL PREDICTIONS vs LINES**")
            lines.append("")
            for p in spread_picks[:12]:
                stars = "⭐" * p['stars']
                lines.append(f"  >> {p['pick']} {stars}")
                # Show prediction details
                if p.get('away_score') and p.get('home_score'):
                    lines.append(f"     Predicted: {p['away_team'][:15]} {p['away_score']:.0f} - {p['home_team'][:15]} {p['home_score']:.0f}")
                lines.append(f"     Model spread: {p['model_spread']:+.1f} | Line: {p['actual_line']:+.1f} | Edge: {p['edge']:.1f}")
            lines.append("")
        else:
            lines.append("No predictions with edge today.")
            lines.append("")

        # =================================================================
        # SECTION 3: TOTALS PICKS (Over/Under)
        # =================================================================
        lines.append("")
        lines.append("TOTALS PICKS (Over/Under)")
        lines.append("=" * 70)
        lines.append("")

        # Sort by stars then edge
        totals_picks.sort(key=lambda x: (-x['stars'], -x['edge']))

        overs = [p for p in totals_picks if 'OVER' in p['pick']]
        unders = [p for p in totals_picks if 'UNDER' in p['pick']]

        if overs:
            lines.append("**OVERS**")
            lines.append("")
            for p in overs[:6]:
                stars = "⭐" * p['stars']
                lines.append(f"  >> {p['pick']} ({p['game']}) {stars}")
                lines.append(f"     Model total: {p['predicted']:.1f} | Edge: {p['edge']:.1f} pts")
            lines.append("")

        if unders:
            lines.append("**UNDERS**")
            lines.append("")
            for p in unders[:6]:
                stars = "⭐" * p['stars']
                lines.append(f"  >> {p['pick']} ({p['game']}) {stars}")
                lines.append(f"     Model total: {p['predicted']:.1f} | Edge: {p['edge']:.1f} pts")
            lines.append("")

        if not overs and not unders:
            lines.append("No high-value totals picks today.")
            lines.append("")

        # =================================================================
        # SECTION 4: GAMES TO AVOID
        # =================================================================
        lines.append("")
        lines.append("GAMES TO AVOID")
        lines.append("=" * 70)
        lines.append("")

        if avoid_games[:8]:
            for g in avoid_games[:8]:
                lines.append(f"  -- {g['game']}: {g['reason']}")
            lines.append("")
        else:
            lines.append("No games flagged to avoid.")
            lines.append("")

        # =================================================================
        # SUMMARY
        # =================================================================
        lines.append("")
        lines.append("-" * 70)
        lines.append("TODAY'S SUMMARY")
        lines.append("-" * 70)
        lines.append(f"  Moneyline picks: {len([p for p in moneyline_picks if p['confidence'] in ['HIGH', 'MEDIUM']])}")
        lines.append(f"  Spread picks: {len(spread_picks)}")
        lines.append(f"  Totals picks: {len(totals_picks)}")
        lines.append(f"  Games to avoid: {len(avoid_games)}")
        lines.append("-" * 70)
        lines.append("")

        # =================================================================
        # DETAILED GAME ANALYSIS (Reference Section)
        # =================================================================
        lines.append("")
        lines.append("=" * 70)
        lines.append("DETAILED GAME ANALYSIS (Reference)")
        lines.append("=" * 70)
        lines.append("")

        game_num = 0
        for analysis in analyses:
            if analysis.get('error'):
                continue

            game_num += 1
            away = analysis['away_name']
            home = analysis['home_name']
            away_data = analysis['away_data']
            home_data = analysis['home_data']
            expected = analysis['expected']
            ff = analysis['four_factors']
            sit = analysis['situational']
            sv = analysis['spread_value']
            tv = analysis['total_value']
            odds = analysis.get('odds')

            # Game Header
            away_rank_str = f"#{analysis['away_rank']} " if analysis.get('away_rank') else ""
            home_rank_str = f"#{analysis['home_rank']} " if analysis.get('home_rank') else ""
            lines.append(f"## GAME {game_num}: {away_rank_str}{away} @ {home_rank_str}{home}")

            venue = analysis.get('venue', 'TBD')
            neutral_str = " (NEUTRAL)" if analysis.get('neutral_site') else ""
            lines.append(f"Venue: {venue}{neutral_str}")
            lines.append("")

            # Team Info with Form and Rest
            away_record = analysis.get('away_record', 'N/A')
            home_record = analysis.get('home_record', 'N/A')
            away_adj_em = away_data.get('adj_em', 0) or 0
            home_adj_em = home_data.get('adj_em', 0) or 0

            # Form info
            away_l10 = away_data.get('last_10_record', '')
            home_l10 = home_data.get('last_10_record', '')
            away_streak = away_data.get('streak', 0)
            home_streak = home_data.get('streak', 0)
            away_streak_str = f"{'W' if away_streak > 0 else 'L'}{abs(away_streak)}" if away_streak else ""
            home_streak_str = f"{'W' if home_streak > 0 else 'L'}{abs(home_streak)}" if home_streak else ""

            # Rest info
            away_rest = away_data.get('rest_days')
            home_rest = home_data.get('rest_days')
            away_rest_str = f"{away_rest}d rest" if away_rest else ""
            home_rest_str = f"{home_rest}d rest" if home_rest else ""

            lines.append(f"**{away}:** {away_record} | AdjEM: {away_adj_em:+.1f} | Rank: #{away_data.get('kenpom_rank', 'N/A')}")
            if away_l10 or away_rest_str:
                form_parts = [f"L10: {away_l10}" if away_l10 else "", away_streak_str, away_rest_str]
                lines.append(f"  → {' | '.join([p for p in form_parts if p])}")

            lines.append(f"**{home}:** {home_record} | AdjEM: {home_adj_em:+.1f} | Rank: #{home_data.get('kenpom_rank', 'N/A')}")
            if home_l10 or home_rest_str:
                form_parts = [f"L10: {home_l10}" if home_l10 else "", home_streak_str, home_rest_str]
                lines.append(f"  → {' | '.join([p for p in form_parts if p])}")

            # Injuries
            away_injuries = away_data.get('injuries', [])
            home_injuries = home_data.get('injuries', [])
            if away_injuries or home_injuries:
                lines.append("")
                lines.append("**INJURIES:**")
                for inj in away_injuries:
                    if inj.get('status') in ['Out', 'Doubtful', 'Questionable']:
                        lines.append(f"  ⚠️ {away}: {inj['player']} ({inj['position']}) - {inj['status']}")
                for inj in home_injuries:
                    if inj.get('status') in ['Out', 'Doubtful', 'Questionable']:
                        lines.append(f"  ⚠️ {home}: {inj['player']} ({inj['position']}) - {inj['status']}")

            lines.append("")

            # Odds Info
            actual_spread = analysis.get('actual_spread')
            actual_total = analysis.get('actual_total')

            if actual_spread is not None:
                if actual_spread >= 0:
                    spread_str = f"{away} +{actual_spread}"
                else:
                    spread_str = f"{home} {-actual_spread:+.1f}"
                lines.append(f"**LINE:** {spread_str}")

            if actual_total:
                lines.append(f"**TOTAL:** {actual_total}")

            # Show best odds if available
            if odds and odds.get('best_odds'):
                best = odds['best_odds']
                if best.get('away_spread'):
                    lines.append(f"Best {away} spread: {best['away_spread']['spread']:+.1f} @ {best['away_spread']['book']}")
                if best.get('home_spread'):
                    lines.append(f"Best {home} spread: {best['home_spread']['spread']:+.1f} @ {best['home_spread']['book']}")

            # Show line movement if available
            game_obj = None
            for g in self.games:
                if g.get('away', {}).get('name') == away:
                    game_obj = g
                    break
            if game_obj and game_obj.get('line_movement'):
                lm = game_obj['line_movement']
                if lm.get('spread_movement') or lm.get('total_movement'):
                    lines.append("")
                    lines.append("**LINE MOVEMENT:**")
                    if lm.get('opening_spread') is not None:
                        lines.append(f"- Spread: {lm['opening_spread']:+.1f} (open) → {lm.get('current_spread', 'N/A')} (current) | Move: {lm.get('spread_movement', 0):+.1f}")
                    if lm.get('opening_total') is not None:
                        lines.append(f"- Total: {lm['opening_total']} (open) → {lm.get('current_total', 'N/A')} (current) | Move: {lm.get('total_movement', 0):+.1f}")
                    if lm.get('signals'):
                        for signal in lm['signals']:
                            lines.append(f"  ⚡ {signal}")

            lines.append("")

            # Key Metrics Table
            lines.append("**EFFICIENCY MATCHUP:**")
            lines.append(f"| Metric | {away[:15]} | {home[:15]} | Edge |")
            lines.append("|--------|-------------|-------------|------|")

            # AdjO
            away_o = expected.get('away_adj_oe', 100)
            home_o = expected.get('home_adj_oe', 100)
            o_edge = away_o - home_o
            o_edge_str = f"{away[:3]}+{o_edge:.1f}" if o_edge > 2 else (f"{home[:3]}+{-o_edge:.1f}" if o_edge < -2 else "Even")
            lines.append(f"| AdjO | {away_o:.1f} | {home_o:.1f} | {o_edge_str} |")

            # AdjD
            away_d = expected.get('away_adj_de', 100)
            home_d = expected.get('home_adj_de', 100)
            d_edge = home_d - away_d  # Lower is better for defense
            d_edge_str = f"{away[:3]}+{d_edge:.1f}" if d_edge > 2 else (f"{home[:3]}+{-d_edge:.1f}" if d_edge < -2 else "Even")
            lines.append(f"| AdjD | {away_d:.1f} | {home_d:.1f} | {d_edge_str} |")

            # eFG%
            lines.append(f"| eFG%O | {ff.get('away_efg_o', 50):.1f}% | {ff.get('home_efg_o', 50):.1f}% | |")
            lines.append(f"| eFG%D | {ff.get('away_efg_d', 50):.1f}% | {ff.get('home_efg_d', 50):.1f}% | |")

            lines.append("")

            # Four Factors Analysis
            lines.append("**FOUR FACTORS EDGE:**")
            lines.append(f"- eFG% edge: {ff['efg_diff']:+.1f}% → {ff['efg_points']:+.2f} pts")
            lines.append(f"- TOV% edge: {ff['tov_diff']:+.1f}% → {ff['tov_points']:+.2f} pts")
            lines.append(f"- ORB% edge: {ff['orb_diff']:+.1f}% → {ff['orb_points']:+.2f} pts")
            lines.append(f"- FTR edge: {ff['ftr_diff']:+.1f} → {ff['ftr_points']:+.2f} pts")
            edge_team = away if ff['total_edge'] > 0 else home
            lines.append(f"**Total: {ff['total_edge']:+.1f} pts to {edge_team}**")
            lines.append("")

            # Expected Score
            lines.append("**EXPECTED SCORE:**")
            lines.append(f"- {away}: {expected['away_score']:.1f}")
            lines.append(f"- {home}: {expected['home_score']:.1f}")
            lines.append(f"- Predicted spread: {expected['predicted_spread']:+.1f} (from {away} perspective)")
            lines.append(f"- Predicted total: {expected['predicted_total']:.1f}")
            if expected.get('home_court_adj'):
                lines.append(f"- Home court: {expected['home_court_adj']:.1f} pts to {home}")
            lines.append("")

            # Situational
            if sit['adjustments']:
                lines.append("**SITUATIONAL FACTORS:**")
                for adj in sit['adjustments']:
                    lines.append(f"- {adj}")
                lines.append(f"**Net adjustment: {sit['total_adjustment']:+.1f} pts**")
                lines.append("")

            # Upset Alert
            if analysis.get('upset_alert'):
                upset = analysis['upset_alert']
                lines.append("**⚠️ UPSET ALERT:**")
                lines.append(f"Underdog: {upset['underdog']} vs Favorite: {upset['favorite']}")
                for flag in upset['flags']:
                    lines.append(f"  - {flag}")
                lines.append("")

            # VALUE ANALYSIS
            lines.append("**VALUE ANALYSIS:**")
            lines.append(f"- Model spread: {sv['final_predicted']:+.1f}")
            if sv.get('actual_spread') is not None:
                lines.append(f"- Actual line: {sv['actual_spread']:+.1f}")
                lines.append(f"- **VALUE: {sv['value_points']:+.1f} points**")
            lines.append("")

            # THE PICK
            stars = "⭐" * sv['confidence_stars']
            if sv['pick_team'] not in ['PASS', 'NO_LINE']:
                pick_team = away if sv['pick_team'] == 'AWAY' else home
                pick_spread = sv['actual_spread'] if sv['pick_team'] == 'AWAY' else -sv['actual_spread']
                lines.append(f"### SPREAD: {pick_team} {pick_spread:+.1f} {stars}")
            else:
                lines.append("### SPREAD: PASS (insufficient edge)")
            lines.append("")

            # Total pick
            if tv['pick'] not in ['PASS', 'NO_LINE']:
                total_stars = "⭐" * tv['confidence_stars']
                lines.append(f"### TOTAL: {tv['pick']} {tv['actual_total']} {total_stars}")
                lines.append(f"Model: {tv['predicted_total']:.1f} | Value: {tv['value_points']:+.1f}")

            # Moneyline pick
            ml = analysis.get('ml_value', {})
            if ml.get('ml_pick') not in ['PASS', 'NO_LINE', None]:
                ml_stars = "⭐" * ml.get('ml_stars', 0)
                ml_team = away if ml['ml_pick'] == 'AWAY_ML' else home
                ml_price = ml.get('best_price', 0)
                ml_price_str = f"+{ml_price}" if ml_price > 0 else str(ml_price)
                lines.append(f"### MONEYLINE: {ml_team} ({ml_price_str}) {ml_stars}")
                lines.append(f"Model: {ml.get('away_model_prob' if ml['ml_pick'] == 'AWAY_ML' else 'home_model_prob', 0):.0f}% | Implied: {ml.get('away_implied_prob' if ml['ml_pick'] == 'AWAY_ML' else 'home_implied_prob', 0):.0f}% | Edge: {ml['ml_value']:.1f}%")

            lines.append("")
            lines.append("-" * 70)
            lines.append("")

        # Footer
        lines.append("=" * 70)
        lines.append("Sources: ESPN, BartTorvik, Sports-Reference, The Odds API")
        lines.append("Methodology: Efficiency Metrics + Four Factors + Situational Adjustments")
        lines.append("=" * 70)

        return "\n".join(lines)


def main():
    """Entry point"""
    # Find the most recent data file
    data_files = sorted(DATA_DIR.glob("ncaa_data_*.json"), reverse=True)

    if not data_files:
        print("Error: No data files found. Run scraper first:")
        print("  python scrape_ncaa_data.py")
        return 1

    data_file = data_files[0]
    print(f"Loading data from: {data_file}")

    with open(data_file) as f:
        data = json.load(f)

    if not data.get('games'):
        print("No games found in data file.")
        return 1

    print(f"Analyzing {len(data['games'])} games...")
    print(f"Team data available: {len(data.get('teams', {}))}")

    # Run analysis
    analyzer = NCAAAnalyzer(data)
    analyses = analyzer.analyze_all_games()

    # Generate report
    report = analyzer.generate_report(analyses)

    # Save report
    output_file = DATA_DIR / f"analysis_{datetime.now().strftime('%Y%m%d')}.md"
    with open(output_file, 'w') as f:
        f.write(report)

    print(f"\nAnalysis saved to: {output_file}")

    # Print summary
    print("\n" + "=" * 50)
    print("ANALYSIS COMPLETE")
    print("=" * 50)

    # Count picks
    spread_picks = [a for a in analyses if a.get('spread_value', {}).get('pick_team') not in ['PASS', 'NO_LINE', None]]
    strong_picks = [a for a in spread_picks if a['spread_value']['confidence_stars'] >= 3]

    print(f"Games analyzed: {len(analyses)}")
    print(f"Spread picks: {len(spread_picks)}")
    print(f"Strong picks (3+ stars): {len(strong_picks)}")

    if strong_picks:
        print("\nTOP PICKS:")
        for a in sorted(strong_picks, key=lambda x: -x['spread_value']['confidence_stars'])[:5]:
            sv = a['spread_value']
            pick_team = a['away_name'] if sv['pick_team'] == 'AWAY' else a['home_name']
            spread = sv['actual_spread'] if sv['pick_team'] == 'AWAY' else -sv['actual_spread']
            stars = "⭐" * sv['confidence_stars']
            print(f"  {stars} {pick_team} {spread:+.1f} ({a['away_name']}@{a['home_name']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
