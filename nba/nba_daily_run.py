#!/usr/bin/env python3
"""
NBA Basketball Daily Runner
Runs scraper -> analyzer -> email in sequence
"""

import subprocess
import sys
import os
import smtplib
import ssl
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

PROJECT_DIR = Path(__file__).parent.parent
NBA_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
LOG_DIR = PROJECT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def run_step(name: str, script: str) -> bool:
    """Run a Python script and return success status."""
    log(f"Starting: {name}")

    try:
        result = subprocess.run(
            [sys.executable, str(NBA_DIR / script)],
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout (NBA API can be slow)
        )

        if result.returncode == 0:
            log(f"  {name} completed successfully")
            if result.stdout:
                lines = result.stdout.strip().split('\n')
                for line in lines[-5:]:
                    log(f"  {line}")
            return True
        else:
            log(f"  {name} failed with code {result.returncode}")
            if result.stderr:
                log(f"  Error: {result.stderr[:500]}")
            if result.stdout:
                log(f"  Output: {result.stdout[-500:]}")
            return False

    except subprocess.TimeoutExpired:
        log(f"  {name} timed out after 10 minutes")
        return False
    except Exception as e:
        log(f"  {name} error: {e}")
        return False


def build_top10_email(data_file: Path, analysis_file: Path) -> str:
    """Build a quality-filtered top picks email with actionable bets."""
    import json
    sys.path.insert(0, str(PROJECT_DIR))
    from nba.nba_analyzer import NBAAnalyzer

    today_fmt = datetime.now().strftime("%A %B %d, %Y")

    with open(data_file) as f:
        data = json.load(f)

    analyzer = NBAAnalyzer(data)
    analyses = analyzer.analyze_all_games()

    # Build all picks with clear action language
    all_picks = []

    for a in analyses:
        if a.get("error"):
            continue

        away = a["away_name"]
        home = a["home_name"]
        expected = a.get("expected", {})
        sv = a.get("spread_value", {})
        tv = a.get("total_value", {})
        ml = a.get("ml_value", {})
        sit = a.get("situational", {})
        confidence = analyzer.calculate_pick_confidence(a)

        predicted_spread = expected.get("predicted_spread", 0)
        away_score = expected.get("away_score", 0)
        home_score = expected.get("home_score", 0)
        predicted_total = expected.get("predicted_total", 0)

        line_spread = sv.get("actual_spread")
        edge = sv.get("value_points", 0)
        pick_team = sv.get("pick_team", "PASS")
        total_line = tv.get("actual_total")
        total_pick = tv.get("pick", "PASS")
        away_ml = ml.get("away_ml")
        home_ml = ml.get("home_ml")

        # Key injuries for context
        away_inj = sit.get("away_injury_impact", 0)
        home_inj = sit.get("home_injury_impact", 0)
        inj_notes = []
        for d in sit.get("away_injury_details", []):
            if "PPG" in d and any(t in d for t in ["superstar", "allstar", "quality_starter"]):
                name = d.split("(")[0].strip()
                inj_notes.append(f"{name} OUT ({away})")
        for d in sit.get("home_injury_details", []):
            if "PPG" in d and any(t in d for t in ["superstar", "allstar", "quality_starter"]):
                name = d.split("(")[0].strip()
                inj_notes.append(f"{name} OUT ({home})")

        # SPREAD pick
        if pick_team in ("AWAY", "HOME"):
            if pick_team == "AWAY":
                bet_team = away
                spread_display = f"{line_spread:+.1f}" if line_spread else ""
                margin_desc = f"{'wins by' if predicted_spread > 0 else 'loses by only'} {abs(predicted_spread):.0f}"
                reason = f"Model: {away} {margin_desc}, getting {line_spread:+.1f}"
            else:
                bet_team = home
                home_line = -line_spread if line_spread else 0
                spread_display = f"{home_line:+.1f}"
                reason = f"Model: {home} wins by {abs(predicted_spread):.0f}, giving only {abs(home_line):.1f}"

            spread_grade = sv.get("grade", "")
            spread_hit_pct = sv.get("hit_pct", 0)

            all_picks.append({
                "type": "SPREAD",
                "action": f"{bet_team} {spread_display}",
                "matchup": f"{away} @ {home}",
                "reason": reason,
                "confidence": confidence,
                "edge": abs(edge),
                "inj_notes": inj_notes[:2],
                "grade": spread_grade,
                "hit_pct": spread_hit_pct,
            })

        # ML UPSET pick (model picks the underdog)
        ml_pick = ml.get("ml_pick")
        ml_grade = ml.get("grade", "")
        ml_hit_pct = ml.get("hit_pct", 0)
        if ml_pick == "AWAY_ML" and away_ml and away_ml > 0:
            all_picks.append({
                "type": "MONEYLINE",
                "action": f"{away} ML ({away_ml:+d})",
                "matchup": f"{away} @ {home}",
                "reason": f"Model: {away} wins outright as underdog ({away_ml:+d})",
                "confidence": confidence,
                "edge": ml.get("ml_value", 0),
                "inj_notes": inj_notes[:2],
                "grade": ml_grade,
                "hit_pct": ml_hit_pct,
            })
        elif ml_pick == "HOME_ML" and home_ml and home_ml > 0:
            all_picks.append({
                "type": "MONEYLINE",
                "action": f"{home} ML ({home_ml:+d})",
                "matchup": f"{away} @ {home}",
                "reason": f"Model: {home} wins outright as underdog ({home_ml:+d})",
                "confidence": confidence,
                "edge": ml.get("ml_value", 0),
                "inj_notes": inj_notes[:2],
                "grade": ml_grade,
                "hit_pct": ml_hit_pct,
            })

    # Filter to quality threshold picks only
    top_picks = []
    for pick in all_picks:
        if pick["type"] == "SPREAD" and pick.get("hit_pct", 0) >= 59:
            top_picks.append(pick)
        elif pick["type"] == "MONEYLINE" and pick.get("hit_pct", 0) >= 59:
            top_picks.append(pick)

    # Sort by confidence (primary) then edge (secondary)
    top_picks.sort(key=lambda p: (p["confidence"], p["edge"]), reverse=True)

    # Build email
    lines = []
    lines.append(f"NBA TOP PICKS — {today_fmt}")
    lines.append("=" * 50)
    lines.append("")

    if not top_picks:
        lines.append("  No top picks today — no bets meet quality threshold.")
        lines.append("")
    else:
        for i, pick in enumerate(top_picks, 1):
            grade_str = f" [{pick['grade']} {pick['hit_pct']:.0f}%]" if pick.get("grade") else ""
            lines.append(f"  {i}. {pick['action']}{grade_str}")
            lines.append(f"     {pick['matchup']}  [{pick['type']}]")
            lines.append(f"     {pick['reason']}")
            if pick["inj_notes"]:
                lines.append(f"     Key injuries: {', '.join(pick['inj_notes'])}")
            lines.append("")

    lines.append("-" * 50)
    lines.append(f"{data.get('games_count', '?')} games today | {len(top_picks)} picks meet quality threshold (B+ grade / 3pt edge)")
    lines.append("")

    return "\n".join(lines)


def send_nba_email() -> bool:
    """Send the NBA top picks email."""
    sender = os.environ.get("NCAA_EMAIL_FROM", "")
    password = os.environ.get("NCAA_EMAIL_PASSWORD", "")
    recipient = os.environ.get("NCAA_EMAIL_TO", "")

    if not all([sender, password, recipient]):
        log("  Email credentials not set - skipping email")
        return False

    today = datetime.now().strftime("%Y%m%d")
    data_file = DATA_DIR / f"nba_data_{today}.json"
    analysis_file = DATA_DIR / f"nba_analysis_{today}.md"

    if not analysis_file.exists():
        log(f"  No analysis file found: {analysis_file}")
        return False

    email_body = build_top10_email(data_file, analysis_file)

    today_fmt = datetime.now().strftime("%Y-%m-%d")
    subject = f"NBA Top Picks - {today_fmt}"

    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = recipient

        text_part = MIMEText(email_body, "plain")
        message.attach(text_part)

        context = ssl.create_default_context()
        try:
            import certifi
            context.load_verify_locations(certifi.where())
        except ImportError:
            pass

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls(context=context)
            server.login(sender, password)
            server.sendmail(sender, recipient, message.as_string())

        log(f"  Email sent to {recipient}")
        return True

    except Exception as e:
        log(f"  Email error: {e}")
        return False


def main():
    today = datetime.now().strftime("%Y-%m-%d")

    log("=" * 60)
    log("NBA BASKETBALL DAILY RUN")
    log(f"Date: {today}")
    log("=" * 60)

    # Step 1: Scrape data
    if not run_step("NBA Data Scraper", "nba_scraper.py"):
        log("  Scraper failed - continuing anyway (may use cached data)")

    # Step 2: Run analysis
    if not run_step("NBA Game Analyzer", "nba_analyzer.py"):
        log("  Analysis failed - cannot send email")
        return 1

    # Step 3: Track picks
    log("Starting: Pick Tracker")
    try:
        import json
        today_compact = datetime.now().strftime("%Y%m%d")
        data_file = DATA_DIR / f"nba_data_{today_compact}.json"
        if data_file.exists():
            sys.path.insert(0, str(PROJECT_DIR))
            from nba.nba_pick_tracker import save_today_picks, update_results
            from nba.nba_analyzer import NBAAnalyzer

            # Update yesterday's results first
            update_results()

            # Save today's picks
            with open(data_file) as f:
                data = json.load(f)
            analyzer = NBAAnalyzer(data)
            analyses = analyzer.analyze_all_games()
            save_today_picks(analyses, data.get("games", []))
        else:
            log(f"  No data file for pick tracker: {data_file}")
    except Exception as e:
        log(f"  Pick tracker error (non-fatal): {e}")

    # Step 4: Send email
    log("Starting: Email Report")
    if send_nba_email():
        log("  Email sent successfully")
    else:
        log("  Email failed - check credentials")

    log("=" * 60)
    log("NBA DAILY RUN COMPLETE")
    log("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
