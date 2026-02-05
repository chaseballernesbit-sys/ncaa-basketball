"""
NCAA Basketball Prediction System - Configuration
"""
import os
from pathlib import Path

# Project paths
PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
LOGS_DIR = PROJECT_DIR / "logs"
LINE_HISTORY_DIR = DATA_DIR / "line_history"

# Create directories if they don't exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
LINE_HISTORY_DIR.mkdir(exist_ok=True)

# API Keys (set via environment variables for security)
# Get free key at: https://the-odds-api.com/
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")

# Email configuration (optional - for daily reports)
EMAIL_RECIPIENT = os.environ.get("NCAA_EMAIL", "")
EMAIL_SENDER = os.environ.get("NCAA_EMAIL_SENDER", "")

# Scraping settings
REQUEST_DELAY = 1.5  # Seconds between requests (respect rate limits)
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Analysis settings
HOME_COURT_ADVANTAGE = 3.75  # Points (standard)
MAX_DAILY_UNITS = 10.0

# Elite home courts (add more as needed)
ELITE_HOME_COURTS = {
    "Duke": 6.0,
    "Kansas": 5.5,
    "Kentucky": 5.0,
    "North Carolina": 5.0,
    "Indiana": 5.0,
    "Syracuse": 5.0,
    "Michigan State": 4.5,
    "Gonzaga": 4.5,
    "Louisville": 4.5,
    "Arizona": 4.5,
}

# Confidence star thresholds (points of value)
STAR_THRESHOLDS = {
    5: 4.0,    # 4+ points of value
    4: 3.0,    # 3-3.9 points
    3: 2.5,    # 2.5-2.9 points
    2: 2.0,    # 2-2.4 points
    1: 1.5,    # 1.5-1.9 points
}

# Unit allocation by star rating
UNITS_BY_STARS = {
    5: 3.0,
    4: 2.0,
    3: 1.5,
    2: 1.0,
    1: 0.5,
}

# Four Factors weights (updated from research)
FOUR_FACTORS_WEIGHTS = {
    "efg": 0.45,   # Effective FG% (most important)
    "tov": 0.30,   # Turnover rate
    "orb": 0.15,   # Offensive rebound rate
    "ftr": 0.10,   # Free throw rate
}

# Points per percentage for Four Factors edges
# REDUCED: Four Factors were adding too much noise, especially for mid-majors
FOUR_FACTORS_POINTS = {
    "efg": 0.20,   # Each 1% eFG edge = 0.20 points (was 0.30)
    "tov": 0.12,   # Each 1% TOV edge = 0.12 points (was 0.20)
    "orb": 0.06,   # Each 1% ORB edge = 0.06 points (was 0.10)
    "ftr": 0.03,   # Each 1 FTR edge = 0.03 points (was 0.05)
}

# =============================================================================
# SITUATIONAL ADJUSTMENTS (points, applied to spread prediction)
# Positive = favors away team, Negative = favors home team
# =============================================================================

SITUATIONAL_ADJUSTMENTS = {
    # REST & FATIGUE (HIGH IMPACT: 2-4 points)
    "back_to_back": -2.5,              # Team played yesterday
    "back_to_back_road": -3.5,         # B2B AND on the road
    "three_in_five_days": -2.0,        # 3 games in 5 days
    "four_in_seven_days": -3.0,        # 4 games in 7 days (conf tourney)
    "rest_advantage_3plus": 1.5,       # 3+ more days rest than opponent
    "rest_advantage_5plus": 2.5,       # 5+ more days rest (long break)

    # TRAVEL FATIGUE (MEDIUM IMPACT: 1-2 points)
    "cross_country_flight": -1.5,      # 2+ timezone travel
    "three_timezone_travel": -2.0,     # 3 timezone travel (coast to coast)
    "altitude_adjustment": -1.5,       # Playing at 5000+ ft elevation
    "quick_turnaround_travel": -2.0,   # Travel + play within 24 hours

    # RECENT FORM / MOMENTUM (MEDIUM-HIGH IMPACT: 1.5-3 points)
    "hot_streak_7plus": 2.0,           # Won 7+ of last 10
    "hot_streak_9plus": 3.0,           # Won 9+ of last 10
    "cold_streak_3plus": -1.5,         # Lost 3+ of last 5
    "cold_streak_5plus": -2.5,         # Lost 5+ of last 7
    "ats_hot_streak": 1.0,             # Covered 6+ of last 8 ATS
    "ats_cold_streak": -1.0,           # Failed to cover 6+ of last 8

    # INJURIES (HIGH IMPACT: 2-5 points depending on player)
    "star_player_out": -4.0,           # Top scorer/player out
    "starting_pg_out": -3.0,           # Starting point guard out
    "key_rotation_player_out": -1.5,   # Key bench player out
    "multiple_starters_out": -5.0,     # 2+ starters out

    # REVENGE / MOTIVATION (LOW-MEDIUM IMPACT: 1-2 points)
    "revenge_blowout": 2.0,            # Lost by 15+ in last meeting
    "revenge_close": 1.0,              # Lost by <5 in last meeting
    "rivalry_game": 0.5,               # Traditional rivalry

    # SCHEDULING SPOTS (MEDIUM IMPACT: 1.5-3 points)
    "lookahead_spot": -2.0,            # Big game coming in 2-3 days
    "letdown_spot": -2.5,              # Coming off emotional win
    "trap_game": -1.5,                 # Good team vs bad team before rival
    "must_win_bubble": 1.5,            # NCAA tournament bubble team

    # CONFERENCE TOURNAMENT (MEDIUM IMPACT: 1-2 points)
    "conf_tourney_day2": -1.0,         # 2nd game in conf tourney
    "conf_tourney_day3": -2.0,         # 3rd game in conf tourney
    "conf_tourney_final": -1.5,        # Championship game fatigue

    # LINE MOVEMENT (MEDIUM IMPACT: informational + 0.5-1 point)
    "sharp_money_detected": 1.0,       # Line moved against public
    "reverse_line_movement": 1.5,      # Heavy public on one side, line moves other way
}

# =============================================================================
# INJURY IMPACT WEIGHTS (by position and usage)
# =============================================================================

INJURY_WEIGHTS = {
    # By role
    "star": 4.0,           # Team's best player (20+ PPG or top usage)
    "starter": 2.0,        # Regular starter
    "sixth_man": 1.5,      # Key rotation player
    "rotation": 0.75,      # Regular rotation player
    "bench": 0.25,         # Deep bench

    # By position importance (multiplier)
    "pg_multiplier": 1.3,  # Point guards more impactful
    "big_multiplier": 1.1, # Rim protection matters
}

# =============================================================================
# ALTITUDE VENUES (elevation in feet)
# =============================================================================

HIGH_ALTITUDE_VENUES = {
    "Colorado": 5430,
    "Air Force": 7258,
    "Utah": 4657,
    "BYU": 4551,
    "Utah State": 4534,
    "Wyoming": 7220,
    "New Mexico": 5312,
    "UNLV": 2001,  # Not that high but desert
    "Colorado State": 5003,
    "Denver": 5280,
}

# Altitude adjustment applies when visiting team is from <2000 ft
ALTITUDE_THRESHOLD = 5000  # Minimum elevation for adjustment

# =============================================================================
# TIMEZONE MAPPING (for travel fatigue)
# =============================================================================

TEAM_TIMEZONES = {
    # Eastern (-5)
    "Duke": "ET", "North Carolina": "ET", "Kentucky": "ET", "Syracuse": "ET",
    "Louisville": "ET", "Indiana": "ET", "Michigan": "ET", "Ohio State": "ET",
    "Florida": "ET", "Miami": "ET", "Georgia": "ET", "Tennessee": "ET",
    "Villanova": "ET", "UConn": "ET", "Virginia": "ET", "Pittsburgh": "ET",

    # Central (-6)
    "Kansas": "CT", "Baylor": "CT", "Texas": "CT", "Texas Tech": "CT",
    "Houston": "CT", "Alabama": "CT", "Auburn": "CT", "LSU": "CT",
    "Arkansas": "CT", "Illinois": "CT", "Wisconsin": "CT", "Iowa": "CT",
    "Marquette": "CT", "Creighton": "CT", "Minnesota": "CT", "Iowa State": "CT",

    # Mountain (-7)
    "Arizona": "MT", "Colorado": "MT", "Utah": "MT", "BYU": "MT",
    "Arizona State": "MT", "New Mexico": "MT", "UNLV": "MT",

    # Pacific (-8)
    "UCLA": "PT", "USC": "PT", "Oregon": "PT", "Washington": "PT",
    "Stanford": "PT", "California": "PT", "San Diego State": "PT", "Gonzaga": "PT",
}

TIMEZONE_OFFSETS = {"ET": 0, "CT": 1, "MT": 2, "PT": 3}

# =============================================================================
# RECENT FORM THRESHOLDS
# =============================================================================

FORM_THRESHOLDS = {
    "hot_streak_games": 10,       # Look at last N games
    "hot_threshold": 7,           # Wins for "hot" (7/10)
    "very_hot_threshold": 9,      # Wins for "very hot" (9/10)
    "cold_games": 5,              # Look at last N for cold
    "cold_threshold": 3,          # Losses for "cold" (3/5)
    "very_cold_games": 7,
    "very_cold_threshold": 5,     # Losses for "very cold" (5/7)
}

# =============================================================================
# LINE MOVEMENT THRESHOLDS
# =============================================================================

LINE_MOVEMENT = {
    "significant_move": 1.5,      # 1.5+ point move is significant
    "sharp_move": 2.0,            # 2+ point move indicates sharp money
    "reverse_threshold": 1.0,     # RLM threshold
}

# =============================================================================
# UPSET CRITERIA (for tournament)
# =============================================================================

UPSET_CRITERIA = {
    "efg_differential_max": 3.0,    # eFG% gap must be < 3%
    "underdog_defense_rank": 50,    # Top-50 defense
    "favorite_orb_rank_min": 100,   # Favorite has poor ORB
    "underdog_tov_forced_min": 15,  # Underdog forces 15+ TOV/game
    "favorite_ft_pct_max": 68,      # Favorite shoots < 68% FT
}
