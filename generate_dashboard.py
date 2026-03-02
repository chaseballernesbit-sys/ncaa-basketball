#!/usr/bin/env python3
"""
NHL Picks Dashboard Generator
Reads NHL pick history and generates a self-contained HTML dashboard.
NHL picks are filtered to top picks only (4+ stars on any bet type).
"""

import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
NHL_PICKS_FILE = Path("/Users/mac/nhl-betting-automation/predictions_history.json")
PROPS_DASHBOARD_FILE = Path("/Users/mac/nhl-betting-automation/props_dashboard_data.json")
OUTPUT_FILE = PROJECT_DIR / "docs" / "index.html"

NHL_TOP_PICK_THRESHOLD = 4  # Only show bet types with this many stars or more


def load_locked_dates() -> dict:
    """Load locked dates from NHL JSON file."""
    locked = {"nhl": []}
    if NHL_PICKS_FILE.exists():
        with open(NHL_PICKS_FILE) as f:
            data = json.load(f)
        locked["nhl"] = data.get("locked_dates", [])
    return locked


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
        # Skip non-NHL games (e.g. Olympic/international — game IDs start with 202509)
        gid = str(p.get("game_id", ""))
        if gid.startswith("202509"):
            continue

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


def load_props_data() -> dict:
    """Load props dashboard data from sos_scraper output.
    Returns empty dict if file doesn't exist (sections just won't render).
    """
    if not PROPS_DASHBOARD_FILE.exists():
        return {}
    try:
        with open(PROPS_DASHBOARD_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


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


def nhl_pick_chip(label: str, conf: int, correct) -> str:
    """Render a single NHL bet as a styled chip."""
    icon = pick_result_icon(correct)
    stars = star_display(conf)
    return f'<span class="pick-chip">{icon} {label} {stars}</span>'


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


def compute_rolling_stats(picks: list, days: int) -> dict:
    """Filter resolved picks to last N days, compute W-L."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    w = l = 0
    for p in picks:
        if p.get("date", "") < cutoff:
            continue
        for f in ("ml_correct", "total_correct", "pl_correct"):
            if p.get(f) is True:
                w += 1
            elif p.get(f) is False:
                l += 1
    return {"wins": w, "losses": l}


def _odds_to_profit(odds) -> float:
    """Convert American odds to profit on a 1u bet. Falls back to -110 (0.91u)."""
    if odds and odds > 0:
        return odds / 100.0
    elif odds and odds < 0:
        return 100.0 / abs(odds)
    return 0.91


def compute_cumulative_profit(nhl_picks: list) -> list:
    """Compute daily cumulative profit in units for NHL."""
    daily = defaultdict(float)

    for p in nhl_picks:
        d = p.get("date", "")
        if not d:
            continue
        odds_keys = {"ml": "ml_odds", "total": "total_odds", "pl": "pl_odds"}
        for bet, field in [("ml", "ml_correct"), ("total", "total_correct"), ("pl", "pl_correct")]:
            if p.get(field) is True:
                daily[d] += _odds_to_profit(p.get(odds_keys[bet]))
            elif p.get(field) is False:
                daily[d] -= 1.0

    if not daily:
        return []

    sorted_dates = sorted(daily.keys())
    result = []
    nhl_cum = 0.0
    for d in sorted_dates:
        nhl_cum += daily[d]
        result.append({
            "date": d,
            "nhl_cum": round(nhl_cum, 2),
        })
    return result


# =============================================================================
# HTML SECTIONS
# =============================================================================

def build_today_section(nhl_by_date: dict, locked: dict) -> str:
    today = date.today().isoformat()
    nhl_today = nhl_by_date.get(today, [])
    today_display = datetime.now().strftime("%b %d")
    nhl_locked = today in locked.get("nhl", [])

    html = '<div class="section">\n'
    html += f'<div class="section-header"><h2>Today\'s Picks &mdash; {today_display}</h2></div>\n'

    # NHL card (full width)
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


def build_record_section(nhl_stats: dict, nhl_picks: list) -> str:
    nhl_o = nhl_stats["overall"]
    total_w = nhl_o["wins"]
    total_l = nhl_o["losses"]
    total_games = total_w + total_l
    win_pct = (total_w / total_games * 100) if total_games > 0 else 0

    # Compute total profit from cumulative data
    profit_data = compute_cumulative_profit(nhl_picks)
    total_profit = profit_data[-1]["nhl_cum"] if profit_data else 0.0
    profit_sign = "+" if total_profit >= 0 else ""
    profit_color = "#00b894" if total_profit >= 0 else "#ff4757"

    # Hero stats bar
    html = '<div class="section">\n'
    html += '<div class="hero-stats">\n'
    html += f'<div class="hero-card green"><div class="hero-label">Overall Record</div>'
    html += f'<div class="hero-value">{total_w}-{total_l}</div>'
    html += f'<div class="hero-sub">{total_games} total picks graded</div></div>\n'
    html += f'<div class="hero-card blue"><div class="hero-label">Win Rate</div>'
    html += f'<div class="hero-value">{win_pct:.1f}%</div>'
    html += f'<div class="hero-sub">top picks only</div></div>\n'
    html += f'<div class="hero-card red"><div class="hero-label">Total Profit</div>'
    html += f'<div class="hero-value" style="color:{profit_color}">{profit_sign}{total_profit:.1f}u</div>'
    html += f'<div class="hero-sub">1u per pick at -110</div></div>\n'
    html += '</div>\n'

    html += '<h2>Record Summary <span class="record-subtitle">(top picks only)</span></h2>\n'

    # NHL record card (full width)
    html += '<div class="card">\n'
    html += f'<h3>NHL <span class="record-overall">{format_record(nhl_o["wins"], nhl_o["losses"])}</span></h3>\n'
    html += '<div class="record-breakdown">\n'
    for label, key in [("ML", "ml"), ("Total", "total"), ("Puck Line", "pl")]:
        s = nhl_stats[key]
        if s["wins"] + s["losses"] > 0:
            html += f'<div class="record-row"><span class="record-label">{label}:</span> {format_record(s["wins"], s["losses"])}{win_pct_bar(s["wins"], s["losses"])}</div>\n'
    # Rolling form
    nhl_7d = compute_rolling_stats(nhl_picks, 7)
    nhl_14d = compute_rolling_stats(nhl_picks, 14)
    html += '<div class="rolling-form">\n'
    html += f'<div class="record-row"><span class="record-label">Last 7d:</span> {format_rolling(nhl_7d)}</div>\n'
    html += f'<div class="record-row"><span class="record-label">Last 14d:</span> {format_rolling(nhl_14d)}</div>\n'
    html += '</div>\n'
    html += '</div>\n</div>\n'

    html += '</div>\n'
    return html


def build_chart_section(nhl_picks: list) -> str:
    """Build an inline SVG cumulative profit chart."""
    data = compute_cumulative_profit(nhl_picks)
    if not data:
        return ""

    # Chart dimensions
    w, h = 800, 250
    pad_l, pad_r, pad_t, pad_b = 50, 20, 15, 35

    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    # Y range
    all_vals = [d["nhl_cum"] for d in data]
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
        hover_rects += f'<rect x="{rx:.1f}" y="{pad_t}" width="{rect_w:.1f}" height="{plot_h}" fill="transparent" class="hover-rect" data-idx="{i}" data-date="{d["date"]}" data-nhl="{d["nhl_cum"]}"/>'

    svg = f'''<svg viewBox="0 0 {w} {h}" class="profit-chart" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="grad-nhl" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#4dabf7"/>
      <stop offset="100%" stop-color="#4dabf7" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect x="{pad_l}" y="{pad_t}" width="{plot_w}" height="{plot_h}" fill="#0d1117" rx="2"/>
  {y_labels}
  {x_labels}
  <line x1="{pad_l}" y1="{zero_y:.1f}" x2="{w - pad_r}" y2="{zero_y:.1f}" stroke="#30363d" stroke-width="1" stroke-dasharray="4,3"/>
  {polyline("nhl_cum", "#4dabf7", "grad-nhl")}
  {hover_rects}
</svg>'''

    html = '<div class="section">\n'
    html += '<h2>Cumulative Profit <span class="record-subtitle">(1u per pick, spreads/totals at -110)</span></h2>\n'
    html += '<div class="chart-container">\n'
    html += '<div class="chart-legend">'
    html += '<span class="legend-item"><span class="legend-dot" style="background:#4dabf7"></span>NHL</span>'
    html += '</div>\n'
    html += svg
    html += '<div class="chart-tooltip" id="chart-tooltip"></div>\n'
    html += '</div>\n</div>\n'
    return html


def build_tier_section(nhl_picks: list) -> str:
    """Build confidence tier breakdown table."""
    nhl_tiers = compute_nhl_tier_stats(nhl_picks)

    if not nhl_tiers:
        return ""

    html = '<div class="section">\n'
    html += '<h2>Confidence Tier Breakdown</h2>\n'

    def tier_row_class(pct):
        if pct >= 60:
            return ' class="tier-good"'
        elif pct < 45:
            return ' class="tier-bad"'
        return ""

    # NHL tier card (full width)
    html += '<div class="card">\n'
    html += '<h3>NHL by Stars</h3>\n'
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
    html += '</div>\n'

    html += '</div>\n'
    return html


def build_daily_section(nhl_by_date: dict) -> str:
    all_dates = sorted(nhl_by_date.keys(), reverse=True)

    html = '<div class="section">\n'
    html += '<h2>Day-by-Day Results</h2>\n'

    for d in all_dates[:30]:
        picks = nhl_by_date[d]
        date_disp = format_date_display(d)
        w, l = day_record_nhl(picks)
        rows = "\n".join(r for p in picks if (r := render_nhl_game_row(p)))
        record = format_day_record(w, l)
        sport_badge = '<span class="sport-badge nhl">NHL</span>'
        block_cls = "day-nhl"
        total = w + l
        if total > 0:
            pct = w / total * 100
            if pct >= 55:
                block_cls += " day-win"
            elif pct < 45:
                block_cls += " day-loss"
        html += f"""<div class="day-block {block_cls}">
<div class="day-header">
    <span class="day-date">{date_disp}</span>
    {sport_badge}
    <span class="day-record">{record}</span>
</div>
<div class="day-picks">{rows}</div>
</div>"""

    html += '</div>\n'
    return html


# =============================================================================
# PROPS SECTIONS
# =============================================================================

def _edge_class(edge: float) -> str:
    """Return CSS class based on edge value."""
    if edge >= 0.08:
        return "edge-good"
    elif edge >= 0.04:
        return "edge-neutral"
    return "edge-low"


def _format_odds(odds) -> str:
    """Format American odds with + prefix for positive."""
    if odds is None:
        return "--"
    return f"{odds:+d}" if isinstance(odds, (int, float)) else str(odds)


def _format_pct(val) -> str:
    """Format a probability as percentage."""
    if val is None:
        return "--"
    return f"{val:.0%}" if val < 1 else f"{val:.1f}%"


def _build_props_table(props: list, title: str, stat_label: str) -> str:
    """Build a props table section. Shared by SOG and Points."""
    if not props:
        return ""

    html = '<div class="section">\n'
    html += f'<h2>{title} <span class="record-subtitle">(SOS + Model + DraftKings)</span></h2>\n'
    html += '<div class="card">\n'
    html += '<table class="props-table"><thead><tr>'
    html += f'<th>Player</th><th>Game</th><th>Proj</th><th>DK Line</th>'
    html += '<th>Odds</th><th>Szn</th><th>L5</th><th>Prob</th><th>Edge</th><th>Why</th>'
    html += '</tr></thead><tbody>\n'

    for p in props[:10]:
        edge_cls = _edge_class(p.get("edge", 0))
        blended = p.get("blended_proj", p.get("sos_proj", 0))
        season = p.get("season_avg")
        l5 = p.get("l5_avg")
        reasons = p.get("matchup_reasons", [])

        html += '<tr>'
        html += f'<td class="prop-player">{p.get("player", "")}'
        if p.get("team"):
            html += f' <span class="prop-team">({p["team"]})</span>'
        html += '</td>'
        html += f'<td>{p.get("game", "")}</td>'
        html += f'<td class="num">{blended:.2f}</td>'
        html += f'<td class="num">{p.get("dk_line", "")}</td>'
        html += f'<td class="num">{_format_odds(p.get("dk_odds"))}</td>'
        html += f'<td class="num">{season:.2f}</td>' if season else '<td class="num dim">--</td>'
        html += f'<td class="num">{l5:.2f}</td>' if l5 else '<td class="num dim">--</td>'
        html += f'<td class="num">{_format_pct(p.get("poisson_prob", p.get("model_prob")))}</td>'
        html += f'<td class="num {edge_cls}">{p.get("edge", 0):.1%}</td>'
        html += f'<td class="prop-reasons">{"; ".join(reasons[:2])}</td>' if reasons else '<td></td>'
        html += '</tr>\n'

    html += '</tbody></table>\n'
    html += '</div>\n</div>\n'
    return html


def build_sog_props_section(props_data: dict) -> str:
    """Build SOG (Shots on Goal) props table section."""
    return _build_props_table(
        props_data.get("top_sog_props", []),
        "Shots on Goal Props", "SOG"
    )


def build_points_props_section(props_data: dict) -> str:
    """Build Points props table section."""
    return _build_props_table(
        props_data.get("top_points_props", []),
        "Points Props", "Points"
    )


def build_hit_rate_section(props_data: dict) -> str:
    """Build hit rate tracking section showing historically profitable props."""
    hit_rate_props = props_data.get("hit_rate_props", [])
    if not hit_rate_props:
        return ""

    today = date.today().isoformat()

    html = '<div class="section">\n'
    html += '<h2>Profitable Props Tracker <span class="record-subtitle">(historical hit rates)</span></h2>\n'
    html += '<div class="card">\n'
    html += '<table class="props-table"><thead><tr>'
    html += '<th>Player</th><th>Market + Line</th><th>Record</th><th>Hit Rate</th>'
    html += '<th>Implied</th><th>Edge</th><th>ROI%</th><th>Streak</th>'
    html += '</tr></thead><tbody>\n'

    for p in hit_rate_props[:15]:
        stat_label = p.get("stat", "").upper()
        if stat_label == "SOG":
            stat_label = "Shots"
        side_label = p.get("side", "over").upper()
        market_line = f"{side_label} {p.get('dk_line', '')} {stat_label}"

        hit_rate = p.get("hit_rate", 0)
        avg_implied = p.get("avg_implied", 0)
        edge_vs = p.get("edge_vs_implied", 0)
        roi = p.get("roi_pct", 0)
        streak = p.get("streak", 0)
        attempts = p.get("attempts", 0)
        hits = p.get("hits", 0)

        # Determine if player is playing today (check last_game field)
        is_today = p.get("last_date", "") == today
        row_cls = ' class="playing-today"' if is_today else ""

        # Edge class
        edge_cls = "edge-good" if edge_vs >= 0.05 else "edge-neutral"
        roi_cls = "win" if roi > 0 else ("loss" if roi < 0 else "")

        # Streak display
        if streak > 0:
            streak_str = f'<span class="win">{streak}W</span>'
        elif streak < 0:
            streak_str = f'<span class="loss">{abs(streak)}L</span>'
        else:
            streak_str = "--"

        html += f'<tr{row_cls}>'
        html += f'<td class="prop-player">{p.get("player", "")}'
        if p.get("team"):
            html += f' <span class="prop-team">({p["team"]})</span>'
        if is_today:
            html += ' <span class="badge-today">LIVE</span>'
        html += f'</td>'
        html += f'<td>{market_line}</td>'
        html += f'<td class="num">{hits}-{attempts - hits}</td>'
        html += f'<td class="num">{hit_rate:.0%}</td>'
        html += f'<td class="num">{avg_implied:.0%}</td>'
        html += f'<td class="num {edge_cls}">{edge_vs:.1%}</td>'
        html += f'<td class="num {roi_cls}">{roi:+.1f}%</td>'
        html += f'<td class="num">{streak_str}</td>'
        html += f'</tr>\n'

    html += '</tbody></table>\n'
    html += '</div>\n</div>\n'
    return html


# =============================================================================
# MAIN HTML GENERATION
# =============================================================================

def generate_html(nhl_picks: list, props_data: dict = None) -> str:
    nhl_stats = compute_nhl_stats(nhl_picks)
    nhl_by_date = group_by_date(nhl_picks)
    locked = load_locked_dates()

    generated = datetime.now().strftime("%b %d, %Y %I:%M %p")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NHL Picks Dashboard</title>
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
    border-bottom: 2px solid #4dabf7;
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
    display: inline-block; background: #0d1117; color: #4dabf7;
    border: 1px solid #4dabf7; border-radius: 3px;
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
.card {{
    background: #161b22; border: 1px solid #1c2129;
    border-radius: 4px; padding: 14px;
}}
.card h3 {{ font-size: 13px; font-weight: 700; margin-bottom: 10px; color: #f0f6fc; text-transform: uppercase; letter-spacing: 0.3px; }}
.game-count {{ font-weight: 400; color: #6e7681; font-size: 12px; text-transform: none; letter-spacing: 0; }}
.record-overall {{ font-weight: 600; color: #4dabf7; font-size: 13px; margin-left: 8px; text-transform: none; letter-spacing: 0; }}

/* Sport-colored top border on today's card */
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

/* ---- Day blocks ---- */
.day-block {{
    background: #161b22; border: 1px solid #1c2129;
    border-radius: 4px; padding: 10px 12px; margin-bottom: 6px;
    border-left: 3px solid transparent;
}}
.day-block:hover {{ background: #1a2030; }}
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
.sport-badge.nhl {{ background: rgba(77,171,247,0.12); color: #4dabf7; }}
.day-record {{ font-size: 12px; margin-left: auto; font-weight: 600; }}
.day-picks {{ display: flex; flex-direction: column; gap: 4px; }}

/* ---- Props tables ---- */
.props-table {{
    width: 100%; border-collapse: collapse; font-size: 12px;
}}
.props-table th {{
    text-align: left; color: #6e7681; font-weight: 600;
    padding: 5px 8px; border-bottom: 1px solid #1c2129;
    font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px;
}}
.props-table td {{
    padding: 6px 8px; color: #c9d1d9; border-bottom: 1px solid #1c2129;
}}
.props-table td.num {{ font-variant-numeric: tabular-nums; text-align: right; }}
.props-table .prop-player {{ font-weight: 600; color: #f0f6fc; white-space: nowrap; }}
.props-table .prop-team {{ font-weight: 400; color: #6e7681; font-size: 11px; }}
.props-table tr:hover {{ background: #111820; }}
.props-table .dim {{ color: #30363d; }}
.props-table .prop-reasons {{ font-size: 10px; color: #6e7681; max-width: 180px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.edge-good {{ color: #00b894; font-weight: 700; }}
.edge-neutral {{ color: #ffa502; font-weight: 600; }}
.edge-low {{ color: #6e7681; }}
.badge-today {{
    display: inline-block; background: rgba(0,184,148,0.15); color: #00b894;
    border: 1px solid rgba(0,184,148,0.3); border-radius: 2px;
    padding: 1px 5px; font-size: 9px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.5px; margin-left: 4px;
    vertical-align: middle;
}}
.playing-today {{ background: rgba(0,184,148,0.03); }}

/* ---- Mobile ---- */
@media (max-width: 480px) {{
    body {{ padding: 10px; }}
    header h1 {{ font-size: 18px; }}
    .hero-value {{ font-size: 22px; }}
    .hero-stats {{ gap: 8px; }}
    .props-table {{ font-size: 11px; }}
    .props-table th, .props-table td {{ padding: 4px 5px; }}
}}
</style>
</head>
<body>
<header>
    <h1>NHL Picks Dashboard</h1>
    <span class="generated">{generated}</span>
</header>

{build_today_section(nhl_by_date, locked)}
{build_record_section(nhl_stats, nhl_picks)}
{build_sog_props_section(props_data) if props_data else ""}
{build_points_props_section(props_data) if props_data else ""}
{build_hit_rate_section(props_data) if props_data else ""}
{build_chart_section(nhl_picks)}
{build_tier_section(nhl_picks)}
{build_daily_section(nhl_by_date)}

<script>
// Chart tooltip
document.querySelectorAll('.hover-rect').forEach(rect => {{
    rect.addEventListener('mousemove', function(e) {{
        const tip = document.getElementById('chart-tooltip');
        if (!tip) return;
        const d = this.dataset;
        tip.innerHTML = '<strong>' + d.date + '</strong><br>' +
            '<span style="color:#4dabf7">NHL: ' + (d.nhl >= 0 ? '+' : '') + parseFloat(d.nhl).toFixed(1) + 'u</span>';
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
    print("Dashboard: loading NHL picks...")
    nhl_picks = load_nhl_picks()
    print(f"Dashboard: {len(nhl_picks)} NHL top picks loaded (4+ stars)")

    props_data = load_props_data()
    if props_data:
        sog_count = len(props_data.get("top_sog_props", []))
        pts_count = len(props_data.get("top_points_props", []))
        hr_count = len(props_data.get("hit_rate_props", []))
        print(f"Dashboard: Props data loaded ({sog_count} SOG, {pts_count} Points, {hr_count} hit rate)")
    else:
        print("Dashboard: No props data found (props sections will be skipped)")

    html = generate_html(nhl_picks, props_data)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        f.write(html)

    print(f"Dashboard: written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
