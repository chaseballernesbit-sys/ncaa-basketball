"""
NBA Basketball Prediction System - Configuration
"""
import os
from pathlib import Path

# Project paths
PROJECT_DIR = Path(__file__).parent.parent
NBA_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
LOGS_DIR = PROJECT_DIR / "logs"
NBA_LINE_HISTORY_DIR = DATA_DIR / "nba_line_history"

DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
NBA_LINE_HISTORY_DIR.mkdir(exist_ok=True)

# API Keys (reuse from NCAA)
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")

# Email configuration
EMAIL_RECIPIENT = os.environ.get("NCAA_EMAIL_TO", "")
EMAIL_SENDER = os.environ.get("NCAA_EMAIL_FROM", "")

# Scraping settings
REQUEST_DELAY = 1.0
NBA_API_DELAY = 0.6  # nba.com rate limits
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# =============================================================================
# HOME COURT ADVANTAGE
# =============================================================================

HOME_COURT_ADVANTAGE = 2.0  # NBA average (~2.5 pts, much less than NCAA 3.75)

ELITE_HOME_COURTS = {
    "Denver Nuggets": 3.5,
    "Utah Jazz": 3.0,
    "Miami Heat": 2.5,
    "Golden State Warriors": 2.5,
    "Boston Celtics": 2.5,
    "New York Knicks": 2.5,
    "Philadelphia 76ers": 2.5,
    "Milwaukee Bucks": 2.5,
    "Phoenix Suns": 3.0,
    "Memphis Grizzlies": 3.0,
    "Oklahoma City Thunder": 3.0,
    "Cleveland Cavaliers": 3.0,
}

# =============================================================================
# TEAM QUALITY TIERS (replaces NCAA conference tiers)
# =============================================================================

TIER_LABELS = {1: "Elite", 2: "Playoff", 3: "Play-in", 4: "Lottery"}
TIER_CONFIDENCE = {1: 1.0, 2: 0.85, 3: 0.70, 4: 0.55}

SPREAD_EDGE_BY_TIER = {1: 1.5, 2: 2.0, 3: 2.5, 4: 3.5}
TOTAL_EDGE_BY_TIER = {1: 4.0, 2: 5.0, 3: 6.0, 4: 7.0}

# Star rating thresholds
STAR_THRESHOLDS = {5: 5.0, 4: 4.0, 3: 3.0, 2: 2.0, 1: 1.5}

# =============================================================================
# ODDS FILTERING
# =============================================================================

MAX_FAVORITE_ODDS = -400
MAX_UNDERDOG_ODDS = 350

# =============================================================================
# UNIT ALLOCATION
# =============================================================================

UNITS_BY_STARS = {5: 3.0, 4: 2.0, 3: 1.5, 2: 1.0, 1: 0.5}
MAX_DAILY_UNITS = 10.0

# =============================================================================
# NBA AVERAGES (for regression/calibration)
# =============================================================================

AVG_PACE = 100.2
AVG_EFFICIENCY = 114.6
AVG_TOTAL = 229.5

# =============================================================================
# ROLLING WINDOW SETTINGS
# =============================================================================

ROLLING_WINDOW_SHORT = 10
ROLLING_WINDOW_LONG = 20
ROLLING_WEIGHT_SHORT = 0.60
ROLLING_WEIGHT_LONG = 0.40

# =============================================================================
# BLENDED STATS WEIGHTS
# =============================================================================

SEASON_WEIGHT = 0.40
ROLLING_10_WEIGHT = 0.35
ROLLING_20_WEIGHT = 0.25
LOCATION_BLEND_WEIGHT = 0.40  # how much weight location splits get in final blend

# =============================================================================
# BENCH DEPTH / INJURY DEPTH AWARENESS
# =============================================================================

LEAGUE_AVG_BENCH_RATIO = 0.32
DEPTH_FACTOR_MAX = 0.30  # max reduction in injury impact for deep teams

# =============================================================================
# LINE MOVEMENT SIGNAL
# =============================================================================

LINE_MOVEMENT_CONFIRMATION = 0.5  # bonus when line moves with model pick
LINE_MOVEMENT_CAUTION = 0.5       # penalty when line moves against model pick
LINE_MOVEMENT_CONFIRM_THRESHOLD = 1.0  # min pts of movement to trigger confirmation
LINE_MOVEMENT_CAUTION_THRESHOLD = 1.5  # min pts of movement to trigger caution

# =============================================================================
# CONTEXT / MOTIVATION FACTORS
# =============================================================================

ALL_STAR_BREAK_END = "2026-02-19"
POST_ALL_STAR_RUST_GAMES = 2    # games after break with rust penalty
POST_ALL_STAR_TOTAL_ADJ = -2.0  # points off predicted total

# =============================================================================
# SPREAD / TOTAL THRESHOLDS
# =============================================================================

MAX_SPREAD_THRESHOLD = 15.0
LARGE_SPREAD_THRESHOLD = 10.0
LARGE_SPREAD_EXTRA_EDGE = 2.0

# =============================================================================
# FOUR FACTORS WEIGHTS (tuned for NBA)
# =============================================================================

FOUR_FACTORS_WEIGHTS = {
    "efg": 0.40,
    "tov": 0.25,
    "orb": 0.15,
    "ftr": 0.20,  # FT rate matters more in NBA
}

FOUR_FACTORS_POINTS = {
    "efg": 0.22,
    "tov": 0.15,
    "orb": 0.08,
    "ftr": 0.05,
}

# =============================================================================
# SITUATIONAL ADJUSTMENTS
# =============================================================================

SITUATIONAL_ADJUSTMENTS = {
    # BACK-TO-BACK (the #1 NBA situational factor)
    "b2b_home": -3.0,
    "b2b_road": -4.5,
    "b2b_second_road": -5.5,
    "both_b2b_cancel": 1.5,

    # REST ADVANTAGE
    "rest_advantage_2plus": 1.5,
    "rest_advantage_3plus": 2.5,

    # SCHEDULE DENSITY
    "four_in_six": -2.0,
    "five_in_seven": -3.0,

    # TRAVEL
    "cross_country_flight": -1.0,
    "three_timezone": -1.5,

    # RECENT FORM
    "hot_streak_7plus": 1.5,
    "hot_streak_9plus": 2.5,
    "cold_streak_3plus": -1.5,
    "cold_streak_5plus": -2.5,

    # INJURIES (applied per-player, see INJURY_TIERS)
    "multiple_starters_out": -1.0,  # Additional penalty on top of per-player

    # TRADE INTEGRATION
    "major_trade_within_5_games": -2.0,
    "major_trade_within_15_games": -1.0,

    # STAR REST RETURN
    "star_rest_return": 1.5,

    # CONTEXT / MOTIVATION
    "playoff_race_fighting": 1.0,
    "tanking": -0.5,
    "division_rivalry": 0.5,
}

# =============================================================================
# INJURY IMPACT TIERS
# =============================================================================

INJURY_TIERS = {
    "superstar": {"ppg_min": 26, "usage_min": 0.30, "impact": -3.5},
    "allstar": {"ppg_min": 20, "usage_min": 0.25, "impact": -2.5},
    "quality_starter": {"ppg_min": 15, "usage_min": 0.20, "impact": -1.5},
    "starter": {"ppg_min": 10, "usage_min": 0.15, "impact": -0.75},
    "rotation": {"ppg_min": 5, "usage_min": 0.10, "impact": -0.4},
    "bench": {"ppg_min": 0, "usage_min": 0, "impact": -0.1},
}

# =============================================================================
# ALTITUDE VENUES
# =============================================================================

HIGH_ALTITUDE_VENUES = {
    "Denver Nuggets": 5280,
    "Utah Jazz": 4226,
}
ALTITUDE_THRESHOLD = 4000

# =============================================================================
# TIMEZONE MAPPING
# =============================================================================

TEAM_TIMEZONES = {
    "Atlanta Hawks": "ET", "Boston Celtics": "ET", "Brooklyn Nets": "ET",
    "Charlotte Hornets": "ET", "Chicago Bulls": "CT", "Cleveland Cavaliers": "ET",
    "Dallas Mavericks": "CT", "Denver Nuggets": "MT", "Detroit Pistons": "ET",
    "Golden State Warriors": "PT", "Houston Rockets": "CT", "Indiana Pacers": "ET",
    "LA Clippers": "PT", "Los Angeles Lakers": "PT", "Memphis Grizzlies": "CT",
    "Miami Heat": "ET", "Milwaukee Bucks": "CT", "Minnesota Timberwolves": "CT",
    "New Orleans Pelicans": "CT", "New York Knicks": "ET",
    "Oklahoma City Thunder": "CT", "Orlando Magic": "ET",
    "Philadelphia 76ers": "ET", "Phoenix Suns": "MT",
    "Portland Trail Blazers": "PT", "Sacramento Kings": "PT",
    "San Antonio Spurs": "CT", "Toronto Raptors": "ET",
    "Utah Jazz": "MT", "Washington Wizards": "ET",
}

TIMEZONE_OFFSETS = {"ET": 0, "CT": 1, "MT": 2, "PT": 3}

# =============================================================================
# DEFENSIVE MATCHUP SIGNAL
# =============================================================================

DEFENSIVE_MATCHUP_MAX = 0.3  # max pts from shooting matchup signal
