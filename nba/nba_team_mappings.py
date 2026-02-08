"""
NBA Team Name Mappings and Normalization
Maps various name formats across ESPN, nba_api, The Odds API to canonical names.
"""

# Canonical name -> list of aliases
TEAM_ALIASES = {
    "Atlanta Hawks": ["ATL", "Hawks", "Atlanta"],
    "Boston Celtics": ["BOS", "Celtics", "Boston"],
    "Brooklyn Nets": ["BKN", "BRK", "Nets", "Brooklyn"],
    "Charlotte Hornets": ["CHA", "CHO", "Hornets", "Charlotte"],
    "Chicago Bulls": ["CHI", "Bulls", "Chicago"],
    "Cleveland Cavaliers": ["CLE", "Cavaliers", "Cavs", "Cleveland"],
    "Dallas Mavericks": ["DAL", "Mavericks", "Mavs", "Dallas"],
    "Denver Nuggets": ["DEN", "Nuggets", "Denver"],
    "Detroit Pistons": ["DET", "Pistons", "Detroit"],
    "Golden State Warriors": ["GSW", "GS", "Warriors", "Golden State"],
    "Houston Rockets": ["HOU", "Rockets", "Houston"],
    "Indiana Pacers": ["IND", "Pacers", "Indiana"],
    "LA Clippers": ["LAC", "Clippers", "Los Angeles Clippers", "L.A. Clippers"],
    "Los Angeles Lakers": ["LAL", "Lakers", "LA Lakers", "L.A. Lakers"],
    "Memphis Grizzlies": ["MEM", "Grizzlies", "Memphis"],
    "Miami Heat": ["MIA", "Heat", "Miami"],
    "Milwaukee Bucks": ["MIL", "Bucks", "Milwaukee"],
    "Minnesota Timberwolves": ["MIN", "Timberwolves", "Wolves", "Minnesota"],
    "New Orleans Pelicans": ["NOP", "NO", "Pelicans", "New Orleans"],
    "New York Knicks": ["NYK", "NY", "Knicks", "New York"],
    "Oklahoma City Thunder": ["OKC", "Thunder", "Oklahoma City"],
    "Orlando Magic": ["ORL", "Magic", "Orlando"],
    "Philadelphia 76ers": ["PHI", "76ers", "Sixers", "Philadelphia"],
    "Phoenix Suns": ["PHX", "PHO", "Suns", "Phoenix"],
    "Portland Trail Blazers": ["POR", "Blazers", "Trail Blazers", "Portland"],
    "Sacramento Kings": ["SAC", "Kings", "Sacramento"],
    "San Antonio Spurs": ["SAS", "SA", "Spurs", "San Antonio"],
    "Toronto Raptors": ["TOR", "Raptors", "Toronto"],
    "Utah Jazz": ["UTA", "Jazz", "Utah"],
    "Washington Wizards": ["WAS", "WSH", "Wizards", "Washington"],
}

# ESPN team ID mapping
ESPN_TEAM_IDS = {
    "Atlanta Hawks": "1", "Boston Celtics": "2", "Brooklyn Nets": "17",
    "Charlotte Hornets": "30", "Chicago Bulls": "4", "Cleveland Cavaliers": "5",
    "Dallas Mavericks": "6", "Denver Nuggets": "7", "Detroit Pistons": "8",
    "Golden State Warriors": "9", "Houston Rockets": "10", "Indiana Pacers": "11",
    "LA Clippers": "12", "Los Angeles Lakers": "13", "Memphis Grizzlies": "29",
    "Miami Heat": "14", "Milwaukee Bucks": "15", "Minnesota Timberwolves": "16",
    "New Orleans Pelicans": "3", "New York Knicks": "18", "Oklahoma City Thunder": "25",
    "Orlando Magic": "19", "Philadelphia 76ers": "20", "Phoenix Suns": "21",
    "Portland Trail Blazers": "22", "Sacramento Kings": "23", "San Antonio Spurs": "24",
    "Toronto Raptors": "28", "Utah Jazz": "26", "Washington Wizards": "27",
}

# nba_api team IDs
NBA_API_TEAM_IDS = {
    "Atlanta Hawks": 1610612737, "Boston Celtics": 1610612738,
    "Brooklyn Nets": 1610612751, "Charlotte Hornets": 1610612766,
    "Chicago Bulls": 1610612741, "Cleveland Cavaliers": 1610612739,
    "Dallas Mavericks": 1610612742, "Denver Nuggets": 1610612743,
    "Detroit Pistons": 1610612765, "Golden State Warriors": 1610612744,
    "Houston Rockets": 1610612745, "Indiana Pacers": 1610612754,
    "LA Clippers": 1610612746, "Los Angeles Lakers": 1610612747,
    "Memphis Grizzlies": 1610612763, "Miami Heat": 1610612748,
    "Milwaukee Bucks": 1610612749, "Minnesota Timberwolves": 1610612750,
    "New Orleans Pelicans": 1610612740, "New York Knicks": 1610612752,
    "Oklahoma City Thunder": 1610612760, "Orlando Magic": 1610612753,
    "Philadelphia 76ers": 1610612755, "Phoenix Suns": 1610612756,
    "Portland Trail Blazers": 1610612757, "Sacramento Kings": 1610612758,
    "San Antonio Spurs": 1610612759, "Toronto Raptors": 1610612761,
    "Utah Jazz": 1610612762, "Washington Wizards": 1610612764,
}


# =============================================================================
# CONFERENCE & DIVISION MAPPINGS
# =============================================================================

EASTERN_CONFERENCE = {
    "Atlanta Hawks", "Boston Celtics", "Brooklyn Nets", "Charlotte Hornets",
    "Chicago Bulls", "Cleveland Cavaliers", "Detroit Pistons", "Indiana Pacers",
    "Miami Heat", "Milwaukee Bucks", "New York Knicks", "Orlando Magic",
    "Philadelphia 76ers", "Toronto Raptors", "Washington Wizards",
}

WESTERN_CONFERENCE = {
    "Dallas Mavericks", "Denver Nuggets", "Golden State Warriors",
    "Houston Rockets", "LA Clippers", "Los Angeles Lakers",
    "Memphis Grizzlies", "Minnesota Timberwolves", "New Orleans Pelicans",
    "Oklahoma City Thunder", "Phoenix Suns", "Portland Trail Blazers",
    "Sacramento Kings", "San Antonio Spurs", "Utah Jazz",
}

NBA_DIVISIONS = {
    "Atlantic": {"Boston Celtics", "Brooklyn Nets", "New York Knicks",
                 "Philadelphia 76ers", "Toronto Raptors"},
    "Central": {"Chicago Bulls", "Cleveland Cavaliers", "Detroit Pistons",
                "Indiana Pacers", "Milwaukee Bucks"},
    "Southeast": {"Atlanta Hawks", "Charlotte Hornets", "Miami Heat",
                  "Orlando Magic", "Washington Wizards"},
    "Northwest": {"Denver Nuggets", "Minnesota Timberwolves",
                  "Oklahoma City Thunder", "Portland Trail Blazers", "Utah Jazz"},
    "Pacific": {"Golden State Warriors", "LA Clippers", "Los Angeles Lakers",
                "Phoenix Suns", "Sacramento Kings"},
    "Southwest": {"Dallas Mavericks", "Houston Rockets", "Memphis Grizzlies",
                  "New Orleans Pelicans", "San Antonio Spurs"},
}


def get_conference(team_name: str) -> str:
    """Return 'East' or 'West' for a team."""
    if team_name in EASTERN_CONFERENCE:
        return "East"
    if team_name in WESTERN_CONFERENCE:
        return "West"
    return ""


def get_division(team_name: str) -> str:
    """Return division name for a team."""
    for div, teams in NBA_DIVISIONS.items():
        if team_name in teams:
            return div
    return ""


def same_division(team1: str, team2: str) -> bool:
    """Check if two teams are in the same division."""
    d1 = get_division(team1)
    d2 = get_division(team2)
    return d1 != "" and d1 == d2


def _build_reverse_lookup():
    reverse = {}
    for canonical, aliases in TEAM_ALIASES.items():
        reverse[canonical.lower()] = canonical
        for alias in aliases:
            reverse[alias.lower()] = canonical
    return reverse


ALIAS_TO_CANONICAL = _build_reverse_lookup()


def normalize_team_name(name: str) -> str:
    """Convert any NBA team name format to canonical name."""
    if not name:
        return name
    clean = name.strip()
    lower = clean.lower()
    if lower in ALIAS_TO_CANONICAL:
        return ALIAS_TO_CANONICAL[lower]
    # Try removing "the " prefix
    if lower.startswith("the "):
        test = lower[4:]
        if test in ALIAS_TO_CANONICAL:
            return ALIAS_TO_CANONICAL[test]
    return clean


def get_espn_id(team_name: str) -> str:
    canonical = normalize_team_name(team_name)
    return ESPN_TEAM_IDS.get(canonical, "")


def get_nba_api_id(team_name: str) -> int:
    canonical = normalize_team_name(team_name)
    return NBA_API_TEAM_IDS.get(canonical, 0)


def get_team_tier(net_rating: float, win_pct: float) -> int:
    """
    Assign team quality tier based on net rating and win%.
    Tier 1: Elite contenders
    Tier 2: Playoff teams
    Tier 3: Play-in / bubble
    Tier 4: Lottery
    """
    if net_rating >= 6.0 and win_pct >= 0.58:
        return 1
    elif net_rating >= 2.0 and win_pct >= 0.52:
        return 2
    elif net_rating >= -2.0 and win_pct >= 0.43:
        return 3
    else:
        return 4
