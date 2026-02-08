#!/usr/bin/env python3
"""
Sports Picks Dashboard Generator
Reads NBA + NHL pick history and generates a self-contained HTML dashboard.
NHL picks are filtered to top picks only (4+ stars on any bet type).
"""

import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
NBA_PICKS_FILE = DATA_DIR / "nba_picks_history.json"
NBA_BACKTEST_FILE = DATA_DIR / "nba_backtest_results.json"
NHL_PICKS_FILE = Path("/Users/mac/nhl-betting-automation/predictions_history.json")
OUTPUT_FILE = PROJECT_DIR / "docs" / "index.html"

NHL_TOP_PICK_THRESHOLD = 4  # Only show bet types with this many stars or more


def load_locked_dates() -> dict:
    """Load locked dates from both sport JSON files."""
    locked = {"nba": [], "nhl": []}
    if NBA_PICKS_FILE.exists():
        with open(NBA_PICKS_FILE) as f:
            data = json.load(f)
        locked["nba"] = data.get("locked_dates", [])
    if NHL_PICKS_FILE.exists():
        with open(NHL_PICKS_FILE) as f:
            data = json.load(f)
        locked["nhl"] = data.get("locked_dates", [])
    return locked


def load_nba_picks() -> list:
    """Load NBA picks from tracker, falling back to backtest data."""
    picks = []

    if NBA_PICKS_FILE.exists():
        with open(NBA_PICKS_FILE) as f:
            data = json.load(f)
        picks = data.get("picks", [])

    # If tracker is empty/new, seed from backtest
    if not picks and NBA_BACKTEST_FILE.exists():
        print("Dashboard: seeding NBA picks from backtest results")
        sys.path.insert(0, str(PROJECT_DIR))
        from nba.nba_pick_tracker import seed_from_backtest
        seed_from_backtest()
        if NBA_PICKS_FILE.exists():
            with open(NBA_PICKS_FILE) as f:
                data = json.load(f)
            picks = data.get("picks", [])

    return picks


def filter_nba_top_picks(picks: list) -> list:
    """Filter NBA picks to only top-play-tagged bets.

    For picks with top_play_* tags, null out non-top bet types so they
    don't count in stats/profit. Backtest picks (no tags) are excluded entirely.
    """
    filtered = []
    for p in picks:
        has_tags = any(k in p for k in ("top_play_spread", "top_play_ml"))
        if not has_tags:
            # Backtest picks have no tags — exclude from stats/profit
            continue

        is_top_spread = p.get("top_play_spread", False)
        is_top_ml = p.get("top_play_ml", False)

        if not (is_top_spread or is_top_ml):
            continue

        pick = dict(p)
        if not is_top_spread:
            pick["spread_pick"] = None
            pick["spread_correct"] = None
        if not is_top_ml:
            pick["ml_pick"] = None
            pick["ml_correct"] = None
        # Always null out totals — not tracked anymore
        pick["total_pick"] = None
        pick["total_correct"] = None

        filtered.append(pick)
    return filtered


def load_nhl_picks() -> list:
    """Load NHL picks from predictions_history.json, filtered to top plays only.

    Uses the top_play_ml/top_play_total/top_play_pl tags set by the NHL pipeline.
    These tags match the curated "TOP PLAYS" table from the email (top 7 per day).
    Falls back to 4+ star threshold if tags aren't present yet.
    """
    if not NHL_PICKS_FILE.exists():
        print(f"Dashboard: NHL picks file not found: {NHL_PICKS_FILE}")
        return []

    with open(NHL_PICKS_FILE) as f:
        data = json.load(f)

    raw = data.get("predictions", [])
    filtered = []

    for p in raw:
        has_tags = any(k in p for k in ("top_play_ml", "top_play_total", "top_play_pl"))

        if has_tags:
            # Use explicit top play tags
            is_top_ml = p.get("top_play_ml", False)
            is_top_total = p.get("top_play_total", False)
            is_top_pl = p.get("top_play_pl", False)

            if not (is_top_ml or is_top_total or is_top_pl):
                continue

            pick = dict(p)
            if not is_top_ml:
                pick["ml_pick"] = None
                pick["ml_confidence"] = 0
                pick["ml_correct"] = None
            if not is_top_total:
                pick["total_pick"] = None
                pick["total_confidence"] = 0
                pick["total_correct"] = None
            if not is_top_pl:
                pick["pl_pick"] = None
                pick["pl_confidence"] = 0
                pick["pl_correct"] = None
        else:
            # Fallback for untagged data: 4+ stars
            ml_conf = p.get("ml_confidence", 0)
            total_conf = p.get("total_confidence", 0)
            pl_conf = p.get("pl_confidence", 0)
            if max(ml_conf, total_conf, pl_conf) < NHL_TOP_PICK_THRESHOLD:
                continue
            pick = dict(p)
            if ml_conf < NHL_TOP_PICK_THRESHOLD:
                pick["ml_pick"] = None
                pick["ml_confidence"] = 0
                pick["ml_correct"] = None
            if total_conf < NHL_TOP_PICK_THRESHOLD:
                pick["total_pick"] = None
                pick["total_confidence"] = 0
                pick["total_correct"] = None
            if pl_conf < NHL_TOP_PICK_THRESHOLD:
                pick["pl_pick"] = None
                pick["pl_confidence"] = 0
                pick["pl_correct"] = None

        filtered.append(pick)

    return filtered


def compute_nba_stats(picks: list) -> dict:
    """Compute W-L records for NBA picks by type."""
    stats = {
        "spread": {"wins": 0, "losses": 0},
        "ml": {"wins": 0, "losses": 0},
    }

    for p in picks:
        if p.get("spread_correct") is True:
            stats["spread"]["wins"] += 1
        elif p.get("spread_correct") is False:
            stats["spread"]["losses"] += 1

        if p.get("ml_correct") is True:
            stats["ml"]["wins"] += 1
        elif p.get("ml_correct") is False:
            stats["ml"]["losses"] += 1

    w = stats["spread"]["wins"] + stats["ml"]["wins"]
    l = stats["spread"]["losses"] + stats["ml"]["losses"]
    stats["overall"] = {"wins": w, "losses": l}

    return stats


def compute_nhl_stats(picks: list) -> dict:
    """Compute W-L records for NHL top picks by type."""
    stats = {
        "ml": {"wins": 0, "losses": 0},
        "total": {"wins": 0, "losses": 0},
        "pl": {"wins": 0, "losses": 0},
    }

    for p in picks:
        if p.get("ml_correct") is True:
            stats["ml"]["wins"] += 1
        elif p.get("ml_correct") is False:
            stats["ml"]["losses"] += 1

        if p.get("total_correct") is True:
            stats["total"]["wins"] += 1
        elif p.get("total_correct") is False:
            stats["total"]["losses"] += 1

        if p.get("pl_correct") is True:
            stats["pl"]["wins"] += 1
        elif p.get("pl_correct") is False:
            stats["pl"]["losses"] += 1

    w = stats["ml"]["wins"] + stats["total"]["wins"] + stats["pl"]["wins"]
    l = stats["ml"]["losses"] + stats["total"]["losses"] + stats["pl"]["losses"]
    stats["overall"] = {"wins": w, "losses": l}

    return stats


def format_record(w, l):
    """Format a W-L record with percentage."""
    total = w + l
    if total == 0:
        return "0-0"
    pct = w / total * 100
    return f"{w}-{l} ({pct:.0f}%)"


def group_by_date(picks: list, date_key: str = "date") -> dict:
    """Group picks by date, most recent first."""
    by_date = defaultdict(list)
    for p in picks:
        by_date[p.get(date_key, "unknown")].append(p)
    return dict(sorted(by_date.items(), reverse=True))


# =============================================================================
# PICK DISPLAY HELPERS
# =============================================================================

def pick_result_icon(correct):
    if correct is True:
        return '<span class="win">&#10003;</span>'
    elif correct is False:
        return '<span class="loss">&#10007;</span>'
    else:
        return '<span class="pending">&#9679;</span>'


def star_display(conf: int) -> str:
    if conf <= 0:
        return ""
    filled = "&#9733;" * conf
    empty = "&#9734;" * (5 - conf)
    return f'<span class="stars">{filled}{empty}</span>'


def grade_css_class(grade: str) -> str:
    """Return CSS class for a grade badge."""
    if not grade:
        return "grade-default"
    g = grade.upper().strip()
    if g in ("A+", "A"):
        return "grade-a"
    elif g == "B+":
        return "grade-b-plus"
    else:
        return "grade-b"


def nba_pick_chip(label: str, detail: str, grade: str, correct) -> str:
    """Render a single NBA bet as a styled chip."""
    icon = pick_result_icon(correct)
    gcls = grade_css_class(grade)
    grade_html = f'<span class="grade {gcls}">{grade}</span>' if grade else ""
    return f'<span class="pick-chip">{icon} {label} <span class="pick-detail">{detail}</span>{grade_html}</span>'


def nhl_pick_chip(label: str, conf: int, correct) -> str:
    """Render a single NHL bet as a styled chip."""
    icon = pick_result_icon(correct)
    stars = star_display(conf)
    return f'<span class="pick-chip">{icon} {label} {stars}</span>'


def render_nba_game_row(pick: dict) -> str:
    """Render one NBA game as a row with matchup + individual pick chips."""
    away_short = pick.get("away_team", "?").split()[-1]
    home_short = pick.get("home_team", "?").split()[-1]
    matchup = f"{away_short} @ {home_short}"

    chips = []

    if pick.get("spread_pick"):
        team = away_short if pick["spread_pick"] == "AWAY" else home_short
        line = pick.get("spread_line")
        if pick["spread_pick"] == "HOME" and line is not None:
            line = -line
        line_str = f"{line:+.1f}" if line is not None else ""
        grade = pick.get("spread_grade", "")
        chips.append(nba_pick_chip(f"{team} {line_str}", "SPREAD", grade, pick.get("spread_correct")))

    if pick.get("ml_pick"):
        team = pick["ml_pick"].split()[-1]
        odds = f"({pick['ml_odds']:+d})" if pick.get("ml_odds") else ""
        grade = pick.get("ml_grade", "")
        chips.append(nba_pick_chip(f"{team} ML {odds}", "ML", grade, pick.get("ml_correct")))

    # Score if final
    score_html = ""
    if pick.get("result") and pick.get("actual_away_score") is not None:
        score_html = f'<span class="score">{pick["actual_away_score"]}-{pick["actual_home_score"]}</span>'

    chips_html = " ".join(chips)
    return f'<div class="game-row"><div class="game-header"><span class="matchup">{matchup}</span>{score_html}</div><div class="game-chips">{chips_html}</div></div>'


def render_nhl_game_row(pick: dict) -> str:
    """Render one NHL game as a row with matchup + individual pick chips."""
    away = pick.get("away", "?")
    home = pick.get("home", "?")
    matchup = f"{away} @ {home}"

    chips = []

    if pick.get("ml_pick"):
        chips.append(nhl_pick_chip(f"{pick['ml_pick']} ML", pick.get("ml_confidence", 0), pick.get("ml_correct")))

    if pick.get("total_pick"):
        chips.append(nhl_pick_chip(pick["total_pick"], pick.get("total_confidence", 0), pick.get("total_correct")))

    pl = pick.get("pl_pick")
    if pl and pl != "" and pl != "PASS":
        chips.append(nhl_pick_chip(pl, pick.get("pl_confidence", 0), pick.get("pl_correct")))

    if not chips:
        return ""

    # Score if result exists
    score_html = ""
    result = pick.get("result")
    if result and result.get("away_score") is not None:
        score_html = f'<span class="score">{result["away_score"]}-{result["home_score"]}</span>'

    chips_html = " ".join(chips)
    return f'<div class="game-row"><div class="game-header"><span class="matchup">{matchup}</span>{score_html}</div><div class="game-chips">{chips_html}</div></div>'


def day_record_nba(picks: list) -> tuple:
    """Returns (wins, losses) for a day's NBA picks."""
    w = l = 0
    for p in picks:
        for field in ("spread_correct", "ml_correct"):
            if p.get(field) is True: w += 1
            elif p.get(field) is False: l += 1
    return w, l


def day_record_nhl(picks: list) -> tuple:
    """Returns (wins, losses) for a day's NHL top picks."""
    w = l = 0
    for p in picks:
        for field in ("ml_correct", "total_correct", "pl_correct"):
            if p.get(field) is True: w += 1
            elif p.get(field) is False: l += 1
    return w, l


def format_day_record(w, l) -> str:
    if w + l == 0:
        return '<span class="pending">pending</span>'
    pct = w / (w + l) * 100
    cls = "win" if pct >= 55 else ("loss" if pct < 45 else "")
    return f'<span class="{cls}">{w}-{l} ({pct:.0f}%)</span>'


def format_date_display(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = date.today()
        if d == today:
            return "Today"
        elif d == today - timedelta(days=1):
            return "Yesterday"
        return d.strftime("%b %d")
    except (ValueError, TypeError):
        return date_str


# =============================================================================
# TIER / ROLLING / PROFIT COMPUTATIONS
# =============================================================================

def compute_nba_tier_stats(picks: list) -> dict:
    """Group resolved NBA picks by spread_grade and ml_grade, return W-L per grade."""
    tiers = {}
    for p in picks:
        # Spread by grade
        if p.get("spread_correct") is not None and p.get("spread_pick"):
            grade = p.get("spread_grade") or "Ungraded"
            key = f"spread_{grade}"
            if key not in tiers:
                tiers[key] = {"wins": 0, "losses": 0, "type": "Spread", "grade": grade}
            if p["spread_correct"]:
                tiers[key]["wins"] += 1
            else:
                tiers[key]["losses"] += 1
        # ML by grade
        if p.get("ml_correct") is not None and p.get("ml_pick"):
            grade = p.get("ml_grade") or "Ungraded"
            key = f"ml_{grade}"
            if key not in tiers:
                tiers[key] = {"wins": 0, "losses": 0, "type": "ML", "grade": grade}
            if p["ml_correct"]:
                tiers[key]["wins"] += 1
            else:
                tiers[key]["losses"] += 1
    # Merge into grade-level summary (combine spread + ML per grade)
    by_grade = {}
    for v in tiers.values():
        g = v["grade"]
        if g not in by_grade:
            by_grade[g] = {"wins": 0, "losses": 0}
        by_grade[g]["wins"] += v["wins"]
        by_grade[g]["losses"] += v["losses"]
    return by_grade


def compute_nhl_tier_stats(picks: list) -> dict:
    """Group resolved NHL picks by star rating, return W-L per star level."""
    tiers = {}
    for p in picks:
        for bet, field in [("ml", "ml_correct"), ("total", "total_correct"), ("pl", "pl_correct")]:
            if p.get(field) is not None:
                conf = p.get(f"{bet}_confidence", 0)
                if conf <= 0:
                    continue
                if conf not in tiers:
                    tiers[conf] = {"wins": 0, "losses": 0}
                if p[field]:
                    tiers[conf]["wins"] += 1
                else:
                    tiers[conf]["losses"] += 1
    return tiers


def compute_rolling_stats(picks: list, days: int, sport: str) -> dict:
    """Filter resolved picks to last N days, compute W-L."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    w = l = 0
    for p in picks:
        if p.get("date", "") < cutoff:
            continue
        if sport == "nba":
            fields = ("spread_correct", "ml_correct")
        else:
            fields = ("ml_correct", "total_correct", "pl_correct")
        for f in fields:
            if p.get(f) is True:
                w += 1
            elif p.get(f) is False:
                l += 1
    return {"wins": w, "losses": l}


def compute_cumulative_profit(nba_picks: list, nhl_picks: list) -> list:
    """Compute daily cumulative profit in units for both sports."""
    daily = defaultdict(lambda: {"nba": 0.0, "nhl": 0.0})

    for p in nba_picks:
        d = p.get("date", "")
        if not d:
            continue
        # Spread: -110 standard
        if p.get("spread_correct") is True:
            daily[d]["nba"] += 0.91
        elif p.get("spread_correct") is False:
            daily[d]["nba"] -= 1.0
        # ML: use actual odds if available
        if p.get("ml_correct") is True:
            odds = p.get("ml_odds")
            if odds and odds > 0:
                daily[d]["nba"] += odds / 100.0
            elif odds and odds < 0:
                daily[d]["nba"] += 100.0 / abs(odds)
            else:
                daily[d]["nba"] += 0.91
        elif p.get("ml_correct") is False:
            daily[d]["nba"] -= 1.0

    for p in nhl_picks:
        d = p.get("date", "")
        if not d:
            continue
        for bet, field in [("ml", "ml_correct"), ("total", "total_correct"), ("pl", "pl_correct")]:
            if p.get(field) is True:
                daily[d]["nhl"] += 0.91
            elif p.get(field) is False:
                daily[d]["nhl"] -= 1.0

    if not daily:
        return []

    sorted_dates = sorted(daily.keys())
    result = []
    nba_cum = 0.0
    nhl_cum = 0.0
    for d in sorted_dates:
        nba_cum += daily[d]["nba"]
        nhl_cum += daily[d]["nhl"]
        result.append({
            "date": d,
            "nba_cum": round(nba_cum, 2),
            "nhl_cum": round(nhl_cum, 2),
            "total_cum": round(nba_cum + nhl_cum, 2),
        })
    return result


# =============================================================================
# HTML SECTIONS
# =============================================================================

def build_today_section(nba_by_date: dict, nhl_by_date: dict, locked: dict) -> str:
    today = date.today().isoformat()
    nba_today = nba_by_date.get(today, [])
    nhl_today = nhl_by_date.get(today, [])
    today_display = datetime.now().strftime("%b %d")
    nba_locked = today in locked.get("nba", [])
    nhl_locked = today in locked.get("nhl", [])

    html = '<div class="section">\n'
    html += f'<div class="section-header"><h2>Today\'s Picks &mdash; {today_display}</h2></div>\n'
    html += '<div class="cards-row">\n'

    # NBA card
    html += '<div class="card" id="card-nba">\n'
    html += f'<h3>NBA <span class="game-count">{len(nba_today)} top pick{"s" if len(nba_today) != 1 else ""}</span></h3>\n'
    if nba_today:
        html += '<div class="picks-list">\n'
        for p in nba_today:
            html += render_nba_game_row(p)
        html += '</div>\n'
    else:
        html += '<div class="no-picks">No picks yet</div>\n'
    # Lock badge (if locked)
    if nba_locked:
        html += '<div class="lock-status locked"><span class="lock-badge">Locked</span></div>\n'
    html += '</div>\n'

    # NHL card
    html += '<div class="card" id="card-nhl">\n'
    nhl_top_count = sum(1 for p in nhl_today if any([
        p.get("ml_pick"), p.get("total_pick"),
        (p.get("pl_pick") and p["pl_pick"] not in ("", "PASS"))
    ]))
    html += f'<h3>NHL <span class="game-count">{nhl_top_count} top pick{"s" if nhl_top_count != 1 else ""}</span></h3>\n'
    if nhl_today:
        html += '<div class="picks-list">\n'
        for p in nhl_today:
            row = render_nhl_game_row(p)
            if row:
                html += row
        html += '</div>\n'
    else:
        html += '<div class="no-picks">No picks yet</div>\n'
    # Lock badge (if locked)
    if nhl_locked:
        html += '<div class="lock-status locked"><span class="lock-badge">Locked</span></div>\n'
    html += '</div>\n'

    html += '</div>\n'
    html += '</div>\n'
    return html


def format_rolling(stats: dict) -> str:
    """Format rolling stats with color coding."""
    w, l = stats["wins"], stats["losses"]
    total = w + l
    if total == 0:
        return '<span class="pending">--</span>'
    pct = w / total * 100
    cls = "win" if pct >= 55 else ("loss" if pct < 45 else "")
    return f'<span class="{cls}">{w}-{l} ({pct:.0f}%)</span>'


def win_pct_bar(w: int, l: int) -> str:
    """Render a small CSS progress bar for win percentage."""
    total = w + l
    if total == 0:
        return ""
    pct = w / total * 100
    cls = "good" if pct >= 55 else ("bad" if pct < 45 else "neutral")
    return f'<span class="win-pct-bar"><span class="win-pct-fill {cls}" style="width:{pct:.0f}%"></span></span>'


def build_record_section(nba_stats: dict, nhl_stats: dict,
                         nba_picks: list, nhl_picks: list) -> str:
    nba_o = nba_stats["overall"]
    nhl_o = nhl_stats["overall"]
    total_w = nba_o["wins"] + nhl_o["wins"]
    total_l = nba_o["losses"] + nhl_o["losses"]
    total_games = total_w + total_l
    win_pct = (total_w / total_games * 100) if total_games > 0 else 0

    # Compute total profit from cumulative data
    profit_data = compute_cumulative_profit(nba_picks, nhl_picks)
    total_profit = profit_data[-1]["total_cum"] if profit_data else 0.0
    profit_sign = "+" if total_profit >= 0 else ""
    profit_color = "#00b894" if total_profit >= 0 else "#ff4757"

    # Hero stats bar
    html = '<div class="section">\n'
    html += '<div class="hero-stats">\n'
    html += f'<div class="hero-card green"><div class="hero-label">Overall Record</div>'
    html += f'<div class="hero-value">{total_w}-{total_l}</div>'
    html += f'<div class="hero-sub">NBA {nba_o["wins"]}-{nba_o["losses"]} / NHL {nhl_o["wins"]}-{nhl_o["losses"]}</div></div>\n'
    html += f'<div class="hero-card blue"><div class="hero-label">Win Rate</div>'
    html += f'<div class="hero-value">{win_pct:.1f}%</div>'
    html += f'<div class="hero-sub">{total_games} total picks graded</div></div>\n'
    html += f'<div class="hero-card red"><div class="hero-label">Total Profit</div>'
    html += f'<div class="hero-value" style="color:{profit_color}">{profit_sign}{total_profit:.1f}u</div>'
    html += f'<div class="hero-sub">1u per pick at -110</div></div>\n'
    html += '</div>\n'

    html += '<h2>Record Summary <span class="record-subtitle">(top picks only)</span></h2>\n'
    html += '<div class="cards-row">\n'

    # NBA
    html += '<div class="card">\n'
    html += f'<h3>NBA <span class="record-overall">{format_record(nba_o["wins"], nba_o["losses"])}</span></h3>\n'
    html += '<div class="record-breakdown">\n'
    for label, key in [("Spread", "spread"), ("ML", "ml")]:
        s = nba_stats[key]
        if s["wins"] + s["losses"] > 0:
            html += f'<div class="record-row"><span class="record-label">{label}:</span> {format_record(s["wins"], s["losses"])}{win_pct_bar(s["wins"], s["losses"])}</div>\n'
    # Rolling form
    nba_7d = compute_rolling_stats(nba_picks, 7, "nba")
    nba_14d = compute_rolling_stats(nba_picks, 14, "nba")
    html += '<div class="rolling-form">\n'
    html += f'<div class="record-row"><span class="record-label">Last 7d:</span> {format_rolling(nba_7d)}</div>\n'
    html += f'<div class="record-row"><span class="record-label">Last 14d:</span> {format_rolling(nba_14d)}</div>\n'
    html += '</div>\n'
    html += '</div>\n</div>\n'

    # NHL
    html += '<div class="card">\n'
    html += f'<h3>NHL <span class="record-overall">{format_record(nhl_o["wins"], nhl_o["losses"])}</span></h3>\n'
    html += '<div class="record-breakdown">\n'
    for label, key in [("ML", "ml"), ("Total", "total"), ("Puck Line", "pl")]:
        s = nhl_stats[key]
        if s["wins"] + s["losses"] > 0:
            html += f'<div class="record-row"><span class="record-label">{label}:</span> {format_record(s["wins"], s["losses"])}{win_pct_bar(s["wins"], s["losses"])}</div>\n'
    # Rolling form
    nhl_7d = compute_rolling_stats(nhl_picks, 7, "nhl")
    nhl_14d = compute_rolling_stats(nhl_picks, 14, "nhl")
    html += '<div class="rolling-form">\n'
    html += f'<div class="record-row"><span class="record-label">Last 7d:</span> {format_rolling(nhl_7d)}</div>\n'
    html += f'<div class="record-row"><span class="record-label">Last 14d:</span> {format_rolling(nhl_14d)}</div>\n'
    html += '</div>\n'
    html += '</div>\n</div>\n'

    html += '</div>\n</div>\n'
    return html


def build_chart_section(nba_picks: list, nhl_picks: list) -> str:
    """Build an inline SVG cumulative profit chart."""
    data = compute_cumulative_profit(nba_picks, nhl_picks)
    if not data:
        return ""

    # Chart dimensions
    w, h = 800, 250
    pad_l, pad_r, pad_t, pad_b = 50, 20, 15, 35

    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    # Y range
    all_vals = [d["nba_cum"] for d in data] + [d["nhl_cum"] for d in data] + [d["total_cum"] for d in data]
    y_min = min(min(all_vals), 0)
    y_max = max(max(all_vals), 0)
    y_range = y_max - y_min or 1

    def x_pos(i):
        if len(data) == 1:
            return pad_l + plot_w / 2
        return pad_l + (i / (len(data) - 1)) * plot_w

    def y_pos(v):
        return pad_t + plot_h - ((v - y_min) / y_range) * plot_h

    # Build polyline points and gradient fill
    def polyline(key, color, grad_id):
        pts = " ".join(f"{x_pos(i):.1f},{y_pos(d[key]):.1f}" for i, d in enumerate(data))
        # Gradient fill polygon (line down to zero, back along x-axis)
        fill_pts = pts + f" {x_pos(len(data)-1):.1f},{zero_y:.1f} {x_pos(0):.1f},{zero_y:.1f}"
        fill_svg = f'<polygon points="{fill_pts}" fill="url(#{grad_id})" opacity="0.15"/>'
        line_svg = f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5" class="chart-line"/>'
        return fill_svg + line_svg

    # Zero line y
    zero_y = y_pos(0)

    # Y-axis labels
    y_labels = ""
    steps = 5
    for i in range(steps + 1):
        val = y_min + (y_range * i / steps)
        yp = y_pos(val)
        y_labels += f'<text x="{pad_l - 8}" y="{yp + 4}" class="chart-label" text-anchor="end">{val:+.0f}</text>'
        if i > 0 and i < steps:
            y_labels += f'<line x1="{pad_l}" y1="{yp}" x2="{w - pad_r}" y2="{yp}" class="chart-grid"/>'

    # X-axis date labels (show ~6 evenly spaced)
    x_labels = ""
    label_count = min(6, len(data))
    for i in range(label_count):
        idx = int(i * (len(data) - 1) / max(label_count - 1, 1)) if label_count > 1 else 0
        xp = x_pos(idx)
        try:
            d = datetime.strptime(data[idx]["date"], "%Y-%m-%d").strftime("%b %d")
        except (ValueError, TypeError):
            d = data[idx]["date"]
        x_labels += f'<text x="{xp}" y="{h - 5}" class="chart-label" text-anchor="middle">{d}</text>'

    # Invisible hover rects + data points for tooltip
    hover_rects = ""
    rect_w = plot_w / max(len(data), 1)
    for i, d in enumerate(data):
        rx = x_pos(i) - rect_w / 2
        hover_rects += f'<rect x="{rx:.1f}" y="{pad_t}" width="{rect_w:.1f}" height="{plot_h}" fill="transparent" class="hover-rect" data-idx="{i}" data-date="{d["date"]}" data-nba="{d["nba_cum"]}" data-nhl="{d["nhl_cum"]}" data-total="{d["total_cum"]}"/>'

    svg = f'''<svg viewBox="0 0 {w} {h}" class="profit-chart" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="grad-nba" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#00b894"/>
      <stop offset="100%" stop-color="#00b894" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="grad-nhl" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#4dabf7"/>
      <stop offset="100%" stop-color="#4dabf7" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="grad-total" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#c9d1d9"/>
      <stop offset="100%" stop-color="#c9d1d9" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect x="{pad_l}" y="{pad_t}" width="{plot_w}" height="{plot_h}" fill="#0d1117" rx="2"/>
  {y_labels}
  {x_labels}
  <line x1="{pad_l}" y1="{zero_y:.1f}" x2="{w - pad_r}" y2="{zero_y:.1f}" stroke="#30363d" stroke-width="1" stroke-dasharray="4,3"/>
  {polyline("nba_cum", "#00b894", "grad-nba")}
  {polyline("nhl_cum", "#4dabf7", "grad-nhl")}
  {polyline("total_cum", "#c9d1d9", "grad-total")}
  {hover_rects}
</svg>'''

    html = '<div class="section">\n'
    html += '<h2>Cumulative Profit <span class="record-subtitle">(1u per pick, spreads/totals at -110)</span></h2>\n'
    html += '<div class="chart-container">\n'
    html += '<div class="chart-legend">'
    html += '<span class="legend-item"><span class="legend-dot" style="background:#00b894"></span>NBA</span>'
    html += '<span class="legend-item"><span class="legend-dot" style="background:#4dabf7"></span>NHL</span>'
    html += '<span class="legend-item"><span class="legend-dot" style="background:#c9d1d9"></span>Combined</span>'
    html += '</div>\n'
    html += svg
    html += '<div class="chart-tooltip" id="chart-tooltip"></div>\n'
    html += '</div>\n</div>\n'
    return html


def build_tier_section(nba_picks: list, nhl_picks: list) -> str:
    """Build confidence tier breakdown tables."""
    nba_tiers = compute_nba_tier_stats(nba_picks)
    nhl_tiers = compute_nhl_tier_stats(nhl_picks)

    if not nba_tiers and not nhl_tiers:
        return ""

    html = '<div class="section">\n'
    html += '<h2>Confidence Tier Breakdown</h2>\n'
    html += '<div class="cards-row">\n'

    def tier_row_class(pct):
        if pct >= 60:
            return ' class="tier-good"'
        elif pct < 45:
            return ' class="tier-bad"'
        return ""

    # NBA tier card
    html += '<div class="card">\n'
    html += '<h3>NBA by Grade</h3>\n'
    if nba_tiers:
        grade_order = ["A+", "A", "B+", "B", "B-", "Ungraded"]
        html += '<table class="tier-table"><thead><tr><th>Grade</th><th>Record</th><th>Win%</th></tr></thead><tbody>\n'
        for g in grade_order:
            if g not in nba_tiers:
                continue
            t = nba_tiers[g]
            w, l = t["wins"], t["losses"]
            total = w + l
            pct = w / total * 100 if total > 0 else 0
            cls = "win" if pct >= 55 else ("loss" if pct < 45 else "")
            html += f'<tr{tier_row_class(pct)}><td>{g}</td><td>{w}-{l}</td><td class="{cls}">{pct:.0f}%</td></tr>\n'
        html += '</tbody></table>\n'
    else:
        html += '<div class="no-picks">No graded picks yet</div>\n'
    html += '</div>\n'

    # NHL tier card
    html += '<div class="card">\n'
    html += '<h3>NHL by Stars</h3>\n'
    if nhl_tiers:
        html += '<table class="tier-table"><thead><tr><th>Rating</th><th>Record</th><th>Win%</th></tr></thead><tbody>\n'
        for stars in sorted(nhl_tiers.keys(), reverse=True):
            t = nhl_tiers[stars]
            w, l = t["wins"], t["losses"]
            total = w + l
            pct = w / total * 100 if total > 0 else 0
            cls = "win" if pct >= 55 else ("loss" if pct < 45 else "")
            star_str = "&#9733;" * stars
            html += f'<tr{tier_row_class(pct)}><td><span class="stars">{star_str}</span></td><td>{w}-{l}</td><td class="{cls}">{pct:.0f}%</td></tr>\n'
        html += '</tbody></table>\n'
    else:
        html += '<div class="no-picks">No rated picks yet</div>\n'
    html += '</div>\n'

    html += '</div>\n</div>\n'
    return html


def build_daily_section(nba_by_date: dict, nhl_by_date: dict) -> str:
    all_dates = sorted(set(list(nba_by_date.keys()) + list(nhl_by_date.keys())), reverse=True)

    html = '<div class="section">\n'
    html += '<h2>Day-by-Day Results</h2>\n'
    html += '<div class="tabs">\n'
    html += '<button class="tab active" onclick="showTab(\'all\')">All</button>\n'
    html += '<button class="tab tab-nba" onclick="showTab(\'nba\')">NBA</button>\n'
    html += '<button class="tab tab-nhl" onclick="showTab(\'nhl\')">NHL</button>\n'
    html += '</div>\n'

    # Helper to render a day-block
    def day_block(d, sport, picks):
        date_disp = format_date_display(d)
        if sport == "nba":
            w, l = day_record_nba(picks)
            rows = "\n".join(render_nba_game_row(p) for p in picks)
        else:
            w, l = day_record_nhl(picks)
            rows = "\n".join(r for p in picks if (r := render_nhl_game_row(p)))
        record = format_day_record(w, l)
        sport_badge = f'<span class="sport-badge {sport}">{sport.upper()}</span>' if sport else ""
        # Day block classes: sport color + win/loss accent
        block_cls = f"day-{sport}"
        total = w + l
        if total > 0:
            pct = w / total * 100
            if pct >= 55:
                block_cls += " day-win"
            elif pct < 45:
                block_cls += " day-loss"
        return f"""<div class="day-block {block_cls}">
<div class="day-header">
    <span class="day-date">{date_disp}</span>
    {sport_badge}
    <span class="day-record">{record}</span>
</div>
<div class="day-picks">{rows}</div>
</div>"""

    # All tab
    html += '<div class="tab-content" id="tab-all">\n'
    for d in all_dates[:30]:
        if d in nba_by_date:
            html += day_block(d, "nba", nba_by_date[d])
        if d in nhl_by_date:
            html += day_block(d, "nhl", nhl_by_date[d])
    html += '</div>\n'

    # NBA tab
    html += '<div class="tab-content hidden" id="tab-nba">\n'
    for d in sorted(nba_by_date.keys(), reverse=True)[:30]:
        html += day_block(d, "nba", nba_by_date[d])
    html += '</div>\n'

    # NHL tab
    html += '<div class="tab-content hidden" id="tab-nhl">\n'
    for d in sorted(nhl_by_date.keys(), reverse=True)[:30]:
        html += day_block(d, "nhl", nhl_by_date[d])
    html += '</div>\n'

    html += '</div>\n'
    return html


# =============================================================================
# MAIN HTML GENERATION
# =============================================================================

def generate_html(nba_picks: list, nba_picks_all: list, nhl_picks: list) -> str:
    # nba_picks = top-play filtered (for stats, profit, record, rolling)
    # nba_picks_all = all picks (for tier breakdown with "Ungraded", day-by-day display)
    nba_stats = compute_nba_stats(nba_picks)
    nhl_stats = compute_nhl_stats(nhl_picks)
    nba_by_date = group_by_date(nba_picks)
    nba_by_date_all = group_by_date(nba_picks_all)
    nhl_by_date = group_by_date(nhl_picks)
    locked = load_locked_dates()

    generated = datetime.now().strftime("%b %d, %Y %I:%M %p")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sports Picks Dashboard</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #0d1117;
    color: #c9d1d9;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    padding: 16px 20px;
    max-width: 1100px;
    margin: 0 auto;
    line-height: 1.4;
    font-size: 13px;
}}

/* ---- Header ---- */
header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 16px 0 14px;
    margin-bottom: 20px;
    border-bottom: 2px solid #00b894;
}}
header h1 {{
    font-size: 22px;
    font-weight: 700;
    color: #f0f6fc;
    letter-spacing: -0.3px;
}}
header .generated {{
    font-size: 12px;
    color: #6e7681;
}}

/* ---- Sections ---- */
.section {{ margin-bottom: 24px; }}
.section h2 {{
    font-size: 14px; font-weight: 700; color: #f0f6fc;
    margin-bottom: 10px; padding-bottom: 6px;
    border-bottom: 1px solid #1c2129;
    text-transform: uppercase; letter-spacing: 0.5px;
}}
.section-header {{
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid #1c2129;
}}
.section-header h2 {{ margin-bottom: 0; padding-bottom: 0; border-bottom: none; }}
.record-subtitle {{ font-weight: 400; color: #6e7681; font-size: 12px; text-transform: none; letter-spacing: 0; }}

/* ---- Lock badge ---- */
.lock-status {{
    margin-top: 10px; padding-top: 8px; border-top: 1px solid #1c2129;
    text-align: center;
}}
.lock-badge {{
    display: inline-block; background: #0d1117; color: #00b894;
    border: 1px solid #00b894; border-radius: 3px;
    padding: 3px 12px; font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.5px;
}}

/* ---- Hero stats bar ---- */
.hero-stats {{
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
    margin-bottom: 20px;
}}
@media (max-width: 600px) {{ .hero-stats {{ grid-template-columns: 1fr; }} }}
.hero-card {{
    background: #161b22;
    border: 1px solid #1c2129;
    border-radius: 4px;
    padding: 16px;
    text-align: center;
    border-top: 2px solid #30363d;
}}
.hero-card.green {{ border-top-color: #00b894; }}
.hero-card.blue {{ border-top-color: #4dabf7; }}
.hero-card.red {{ border-top-color: #ff4757; }}
.hero-label {{
    font-size: 10px; font-weight: 600; color: #6e7681;
    text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 4px;
}}
.hero-value {{
    font-size: 28px; font-weight: 800; color: #f0f6fc; line-height: 1;
    font-variant-numeric: tabular-nums;
}}
.hero-sub {{ font-size: 11px; color: #484f58; margin-top: 4px; }}

/* ---- Cards ---- */
.cards-row {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
}}
@media (max-width: 700px) {{ .cards-row {{ grid-template-columns: 1fr; }} }}
.card {{
    background: #161b22; border: 1px solid #1c2129;
    border-radius: 4px; padding: 14px;
}}
.card h3 {{ font-size: 13px; font-weight: 700; margin-bottom: 10px; color: #f0f6fc; text-transform: uppercase; letter-spacing: 0.3px; }}
.game-count {{ font-weight: 400; color: #6e7681; font-size: 12px; text-transform: none; letter-spacing: 0; }}
.record-overall {{ font-weight: 600; color: #4dabf7; font-size: 13px; margin-left: 8px; text-transform: none; letter-spacing: 0; }}

/* Sport-colored top border on today's cards */
#card-nba {{ border-top: 2px solid #00b894; }}
#card-nhl {{ border-top: 2px solid #4dabf7; }}

/* ---- Picks list ---- */
.picks-list {{ display: flex; flex-direction: column; gap: 6px; }}
.game-row {{
    background: #0d1117; border-radius: 3px; padding: 8px 10px;
    border-left: 2px solid transparent;
}}
.game-row:hover {{ background: #111820; }}
.game-header {{
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 4px;
}}
.matchup {{ font-weight: 600; font-size: 13px; color: #c9d1d9; }}
.score {{ font-size: 11px; color: #6e7681; }}
.game-chips {{ display: flex; flex-wrap: wrap; gap: 4px; }}

/* ---- Pick chips ---- */
.pick-chip {{
    display: inline-flex; align-items: center; gap: 4px;
    background: #1c2129; border-radius: 3px; padding: 2px 7px;
    font-size: 11px; color: #c9d1d9; white-space: nowrap;
    border-left: 2px solid #30363d;
}}
.pick-chip:has(.win) {{ border-left-color: #00b894; }}
.pick-chip:has(.loss) {{ border-left-color: #ff4757; }}
.pick-chip:has(.pending) {{ border-left-color: #ffa502; }}
.pick-detail {{
    color: #6e7681; font-size: 10px; text-transform: uppercase;
    margin-left: 2px; font-weight: 600;
}}
/* Grade badges */
.grade {{
    border-radius: 2px; padding: 1px 4px;
    font-size: 10px; font-weight: 700; margin-left: 3px;
}}
.grade-a {{ background: rgba(0,184,148,0.15); color: #00b894; }}
.grade-b-plus {{ background: rgba(77,171,247,0.15); color: #4dabf7; }}
.grade-b {{ background: rgba(110,118,129,0.15); color: #8b949e; }}
.grade-default {{ background: #1c2129; color: #6e7681; }}

.no-picks {{
    color: #30363d; font-size: 12px; padding: 12px 0;
}}

/* ---- Records ---- */
.record-breakdown {{ display: flex; flex-direction: column; gap: 4px; }}
.record-row {{ font-size: 13px; color: #c9d1d9; }}
.record-label {{ color: #6e7681; display: inline-block; width: 70px; }}
.rolling-form {{ margin-top: 8px; padding-top: 6px; border-top: 1px solid #1c2129; }}

/* Win% progress bar */
.win-pct-bar {{
    display: block; height: 3px;
    background: #1c2129; margin-top: 3px; overflow: hidden;
}}
.win-pct-fill {{ height: 100%; }}
.win-pct-fill.good {{ background: #00b894; }}
.win-pct-fill.bad {{ background: #ff4757; }}
.win-pct-fill.neutral {{ background: #484f58; }}

/* ---- Colors ---- */
.win {{ color: #00b894; font-weight: 600; }}
.loss {{ color: #ff4757; font-weight: 600; }}
.pending {{ color: #ffa502; }}
.stars {{ color: #ffa502; font-size: 12px; letter-spacing: -1px; }}

/* ---- Tier tables ---- */
.tier-table {{
    width: 100%; border-collapse: collapse; font-size: 12px;
}}
.tier-table th {{
    text-align: left; color: #6e7681; font-weight: 600;
    padding: 4px 8px; border-bottom: 1px solid #1c2129;
    font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px;
}}
.tier-table td {{
    padding: 5px 8px; color: #c9d1d9; border-bottom: 1px solid #1c2129;
}}
.tier-table tr.tier-good {{ background: rgba(0,184,148,0.05); }}
.tier-table tr.tier-bad {{ background: rgba(255,71,87,0.05); }}

/* ---- Profit chart ---- */
.chart-container {{
    background: #161b22; border: 1px solid #1c2129; border-radius: 4px;
    padding: 12px; position: relative;
}}
.profit-chart {{ width: 100%; height: auto; }}
.chart-label {{ fill: #6e7681; font-size: 11px; font-family: inherit; }}
.chart-grid {{ stroke: #1c2129; stroke-width: 1; }}
.chart-line {{ vector-effect: non-scaling-stroke; }}
.chart-legend {{
    display: flex; gap: 16px; margin-bottom: 8px; font-size: 11px; color: #6e7681;
}}
.legend-item {{ display: flex; align-items: center; gap: 5px; }}
.legend-dot {{
    width: 8px; height: 8px; border-radius: 2px; display: inline-block;
}}
.chart-tooltip {{
    display: none; position: absolute; background: #1c2129;
    border: 1px solid #30363d; border-radius: 3px; padding: 8px 10px;
    font-size: 11px; color: #c9d1d9; pointer-events: none; z-index: 10;
    white-space: nowrap;
}}

/* ---- Tabs ---- */
.tabs {{ display: flex; gap: 0; margin-bottom: 12px; border-bottom: 1px solid #1c2129; }}
.tab {{
    background: none; color: #6e7681; border: none; border-bottom: 2px solid transparent;
    padding: 6px 16px; cursor: pointer;
    font-size: 12px; font-family: inherit; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.5px;
}}
.tab.active {{ color: #f0f6fc; border-bottom-color: #4dabf7; }}
.tab:hover {{ color: #c9d1d9; }}
.tab-content.hidden {{ display: none; }}
.tab-nba.active {{ border-bottom-color: #00b894; color: #00b894; }}
.tab-nhl.active {{ border-bottom-color: #4dabf7; color: #4dabf7; }}

/* ---- Day blocks ---- */
.day-block {{
    background: #161b22; border: 1px solid #1c2129;
    border-radius: 4px; padding: 10px 12px; margin-bottom: 6px;
    border-left: 3px solid transparent;
}}
.day-block:hover {{ background: #1a2030; }}
.day-block.day-nba {{ border-left-color: #00b894; }}
.day-block.day-nhl {{ border-left-color: #4dabf7; }}
.day-block.day-win {{ }}
.day-block.day-loss {{ }}
.day-header {{
    display: flex; align-items: center; gap: 8px;
    margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px solid #1c2129;
}}
.day-date {{ font-weight: 700; font-size: 13px; color: #f0f6fc; min-width: 70px; }}
.sport-badge {{
    font-size: 10px; font-weight: 700; padding: 2px 6px;
    border-radius: 2px; text-transform: uppercase; letter-spacing: 0.5px;
}}
.sport-badge.nba {{ background: rgba(0,184,148,0.12); color: #00b894; }}
.sport-badge.nhl {{ background: rgba(77,171,247,0.12); color: #4dabf7; }}
.day-record {{ font-size: 12px; margin-left: auto; font-weight: 600; }}
.day-picks {{ display: flex; flex-direction: column; gap: 4px; }}

/* ---- Mobile ---- */
@media (max-width: 480px) {{
    body {{ padding: 10px; }}
    header h1 {{ font-size: 18px; }}
    .hero-value {{ font-size: 22px; }}
    .hero-stats {{ gap: 8px; }}
}}
</style>
</head>
<body>
<header>
    <h1>Sports Picks Dashboard</h1>
    <span class="generated">{generated}</span>
</header>

{build_today_section(nba_by_date, nhl_by_date, locked)}
{build_record_section(nba_stats, nhl_stats, nba_picks, nhl_picks)}
{build_chart_section(nba_picks, nhl_picks)}
{build_tier_section(nba_picks_all, nhl_picks)}
{build_daily_section(nba_by_date_all, nhl_by_date)}

<script>
function showTab(tab) {{
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + tab).classList.remove('hidden');
    const btn = event.target;
    btn.classList.add('active');
}}

// Chart tooltip
document.querySelectorAll('.hover-rect').forEach(rect => {{
    rect.addEventListener('mousemove', function(e) {{
        const tip = document.getElementById('chart-tooltip');
        if (!tip) return;
        const d = this.dataset;
        tip.innerHTML = '<strong>' + d.date + '</strong><br>' +
            '<span style="color:#00b894">NBA: ' + (d.nba >= 0 ? '+' : '') + parseFloat(d.nba).toFixed(1) + 'u</span><br>' +
            '<span style="color:#4dabf7">NHL: ' + (d.nhl >= 0 ? '+' : '') + parseFloat(d.nhl).toFixed(1) + 'u</span><br>' +
            'Total: ' + (d.total >= 0 ? '+' : '') + parseFloat(d.total).toFixed(1) + 'u';
        tip.style.display = 'block';
        const container = tip.parentElement;
        const rect2 = container.getBoundingClientRect();
        let left = e.clientX - rect2.left + 12;
        if (left + 150 > rect2.width) left = e.clientX - rect2.left - 150;
        tip.style.left = left + 'px';
        tip.style.top = (e.clientY - rect2.top - 40) + 'px';
    }});
    rect.addEventListener('mouseleave', function() {{
        const tip = document.getElementById('chart-tooltip');
        if (tip) tip.style.display = 'none';
    }});
}});
</script>
</body>
</html>"""

    return html


def main():
    print("Dashboard: loading NBA picks...")
    nba_picks_all = load_nba_picks()
    nba_picks = filter_nba_top_picks(nba_picks_all)
    print(f"Dashboard: {len(nba_picks_all)} NBA picks loaded, {len(nba_picks)} top picks")

    print("Dashboard: loading NHL picks...")
    nhl_picks = load_nhl_picks()
    print(f"Dashboard: {len(nhl_picks)} NHL top picks loaded (4+ stars)")

    html = generate_html(nba_picks, nba_picks_all, nhl_picks)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        f.write(html)

    print(f"Dashboard: written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
