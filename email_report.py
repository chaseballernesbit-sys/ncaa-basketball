#!/usr/bin/env python3
"""
NCAA Basketball - Email Report Sender
Sends concise daily picks via email - Top 20 plays, parlays, and solo bets
"""

import smtplib
import ssl
import os
import re
import json
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict, Tuple

# Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.environ.get("NCAA_EMAIL_FROM", "")
SENDER_PASSWORD = os.environ.get("NCAA_EMAIL_PASSWORD", "")
RECIPIENT_EMAIL = os.environ.get("NCAA_EMAIL_TO", "chaseballernesbit@gmail.com")

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"


def find_latest_analysis() -> Path:
    """Find the most recent analysis file"""
    analysis_files = sorted(DATA_DIR.glob("analysis_*.md"), reverse=True)
    if analysis_files:
        return analysis_files[0]
    return None


def parse_picks_from_analysis(analysis_text: str) -> Dict:
    """Parse the analysis file to extract picks with edges"""
    picks = {
        'spreads': [],
        'totals': [],
        'moneylines': [],
    }

    lines = analysis_text.split('\n')

    # Parse spread picks - need to look at current line AND next line for edge
    in_spreads = False
    for i, line in enumerate(lines):
        if 'SPREAD PICKS' in line:
            in_spreads = True
            continue
        if 'TOTALS PICKS' in line:
            in_spreads = False
            continue
        if in_spreads and '>>' in line and '⭐' in line:
            # Extract: >> Team +X.X ⭐⭐⭐⭐⭐
            match = re.search(r'>>\s*(.+?)\s*([\+\-]\d+\.?\d*)\s*(⭐+)', line)
            if match:
                team = match.group(1).strip()
                spread = match.group(2)
                stars = len(match.group(3))
                # Get edge from next line
                edge = 0
                if i + 1 < len(lines):
                    edge_match = re.search(r'Edge:\s*([\d\.]+)\s*pts', lines[i + 1])
                    if edge_match:
                        edge = float(edge_match.group(1))
                picks['spreads'].append({
                    'team': team,
                    'spread': spread,
                    'stars': stars,
                    'edge': edge,
                    'type': 'spread'
                })

    # Parse totals picks
    in_totals = False
    for i, line in enumerate(lines):
        if 'TOTALS PICKS' in line:
            in_totals = True
            continue
        if 'GAMES TO AVOID' in line:
            in_totals = False
            continue
        if in_totals and '>>' in line and '⭐' in line:
            # Extract: >> OVER/UNDER X (Game) ⭐⭐⭐
            match = re.search(r'>>\s*(OVER|UNDER)\s*([\d\.]+)\s*\((.+?)\)\s*(⭐+)', line)
            if match:
                direction = match.group(1)
                total = match.group(2)
                game = match.group(3).strip()
                stars = len(match.group(4))
                # Get edge from next line
                edge = 0
                if i + 1 < len(lines):
                    edge_match = re.search(r'Edge:\s*([\d\.]+)\s*pts', lines[i + 1])
                    if edge_match:
                        edge = float(edge_match.group(1))
                picks['totals'].append({
                    'direction': direction,
                    'total': total,
                    'game': game,
                    'stars': stars,
                    'edge': edge,
                    'type': 'total'
                })

    # Parse moneyline picks
    in_ml = False
    for i, line in enumerate(lines):
        if 'MONEYLINE PICKS' in line:
            in_ml = True
            continue
        if 'SPREAD PICKS' in line:
            in_ml = False
            continue
        if in_ml and '>>' in line:
            # HIGH-VALUE UNDERDOGS with stars
            if '⭐' in line:
                match = re.search(r'>>\s*(.+?)\s*ML\s*\(([\+\-]\d+)\)\s*vs\s*(.+?)\s*(⭐+)', line)
                if match:
                    team = match.group(1).strip()
                    odds = match.group(2)
                    opponent = match.group(3).strip()
                    stars = len(match.group(4))
                    # Get edge from next line
                    edge = 0
                    if i + 1 < len(lines):
                        edge_match = re.search(r'Edge:\s*([\d\.]+)%', lines[i + 1])
                        if edge_match:
                            edge = float(edge_match.group(1))
                    picks['moneylines'].append({
                        'team': team,
                        'odds': odds,
                        'opponent': opponent,
                        'stars': stars,
                        'edge': edge,
                        'type': 'ml',
                        'is_underdog': True
                    })
            # Regular ML picks (favorites)
            elif 'ML' in line and 'vs' in line:
                match = re.search(r'>>\s*(.+?)\s*ML\s*\(([\+\-]\d+)\)\s*vs\s*(.+)', line)
                if match:
                    team = match.group(1).strip()
                    odds = match.group(2)
                    opponent = match.group(3).strip()
                    picks['moneylines'].append({
                        'team': team,
                        'odds': odds,
                        'opponent': opponent,
                        'stars': 0,
                        'edge': 0,
                        'type': 'ml',
                        'is_underdog': int(odds) > 0
                    })

    return picks


def build_concise_email(picks: Dict) -> str:
    """Build a concise email with top 20 plays, parlays, and solo bets"""
    today = datetime.now().strftime("%A, %B %d")

    lines = []
    lines.append("=" * 50)
    lines.append(f"🏀 NCAA BASKETBALL PICKS - {today}")
    lines.append("=" * 50)
    lines.append("")

    # Combine all picks and sort by stars/edge
    all_picks = []

    for p in picks['spreads']:
        all_picks.append(p)
    for p in picks['totals']:
        all_picks.append(p)
    for p in picks['moneylines']:
        if p.get('stars', 0) > 0:  # Only starred ML picks
            all_picks.append(p)

    # Sort by stars (descending), then edge
    all_picks.sort(key=lambda x: (x.get('stars', 0), x.get('edge', 0)), reverse=True)

    # Take top 20
    top_picks = all_picks[:20]

    if not top_picks:
        lines.append("No high-value plays found today.")
        lines.append("Sometimes the best bet is no bet.")
        return '\n'.join(lines)

    # ========== TOP 20 PLAYS ==========
    lines.append("🎯 TOP PLAYS (Best Value)")
    lines.append("-" * 50)

    for i, pick in enumerate(top_picks, 1):
        stars = "⭐" * pick.get('stars', 0)
        if pick['type'] == 'spread':
            lines.append(f"{i}. {pick['team']} {pick['spread']} {stars}")
            lines.append(f"   Edge: {pick['edge']:.1f} pts")
        elif pick['type'] == 'total':
            lines.append(f"{i}. {pick['direction']} {pick['total']} ({pick['game']}) {stars}")
            lines.append(f"   Edge: {pick['edge']:.1f} pts")
        elif pick['type'] == 'ml':
            lines.append(f"{i}. {pick['team']} ML ({pick['odds']}) {stars}")
            lines.append(f"   Edge: {pick['edge']:.1f}%")
        lines.append("")

    # ========== SOLO BETS (High Confidence Singles) ==========
    lines.append("")
    lines.append("💰 BEST SOLO BETS")
    lines.append("-" * 50)

    # 5-star picks are best for solo bets
    solo_bets = [p for p in top_picks if p.get('stars', 0) >= 4][:5]

    if solo_bets:
        for pick in solo_bets:
            stars = "⭐" * pick.get('stars', 0)
            if pick['type'] == 'spread':
                lines.append(f"• {pick['team']} {pick['spread']} {stars}")
            elif pick['type'] == 'total':
                lines.append(f"• {pick['direction']} {pick['total']} ({pick['game']}) {stars}")
            elif pick['type'] == 'ml':
                lines.append(f"• {pick['team']} ML ({pick['odds']}) {stars}")
        lines.append("")
        lines.append("These are the highest-confidence plays for straight bets.")
    else:
        lines.append("No 4+ star plays today - consider smaller units or passing.")

    # ========== MONEYLINE PLAYS ==========
    lines.append("")
    lines.append("🎰 MONEYLINE PLAYS")
    lines.append("-" * 50)

    # Favorites (safe ML plays)
    safe_favorites = [p for p in picks['moneylines'] if not p.get('is_underdog') and int(p['odds']) <= -200]
    if safe_favorites:
        lines.append("Safe Favorites (-200 or better):")
        for p in safe_favorites[:5]:
            lines.append(f"  • {p['team']} ML ({p['odds']}) vs {p['opponent']}")

    # Value underdogs
    value_dogs = [p for p in picks['moneylines'] if p.get('is_underdog') and p.get('stars', 0) >= 2]
    if value_dogs:
        lines.append("")
        lines.append("Value Underdogs:")
        for p in value_dogs[:3]:
            stars = "⭐" * p.get('stars', 0)
            lines.append(f"  • {p['team']} ML ({p['odds']}) vs {p['opponent']} {stars}")
            if p.get('edge'):
                lines.append(f"    Edge: {p['edge']:.1f}%")

    # ========== PARLAY SUGGESTIONS ==========
    lines.append("")
    lines.append("🎲 SMART PARLAYS")
    lines.append("-" * 50)

    # Build parlays from high-confidence picks
    five_star = [p for p in top_picks if p.get('stars', 0) == 5]
    four_star = [p for p in top_picks if p.get('stars', 0) == 4]

    if len(five_star) >= 2:
        lines.append("")
        lines.append("2-LEG PARLAY (5-Star Picks):")
        for p in five_star[:2]:
            if p['type'] == 'spread':
                lines.append(f"  • {p['team']} {p['spread']}")
            elif p['type'] == 'total':
                lines.append(f"  • {p['direction']} {p['total']} ({p['game']})")
            elif p['type'] == 'ml':
                lines.append(f"  • {p['team']} ML ({p['odds']})")

    if len(five_star) >= 3:
        lines.append("")
        lines.append("3-LEG PARLAY (5-Star Picks):")
        for p in five_star[:3]:
            if p['type'] == 'spread':
                lines.append(f"  • {p['team']} {p['spread']}")
            elif p['type'] == 'total':
                lines.append(f"  • {p['direction']} {p['total']} ({p['game']})")
            elif p['type'] == 'ml':
                lines.append(f"  • {p['team']} ML ({p['odds']})")

    # Mixed parlay with favorites
    if safe_favorites and five_star:
        lines.append("")
        lines.append("MIXED PARLAY (Favorite ML + Spread):")
        if safe_favorites:
            lines.append(f"  • {safe_favorites[0]['team']} ML ({safe_favorites[0]['odds']})")
        if five_star:
            p = five_star[0]
            if p['type'] == 'spread':
                lines.append(f"  • {p['team']} {p['spread']}")
            elif p['type'] == 'total':
                lines.append(f"  • {p['direction']} {p['total']}")

    if not five_star and not four_star:
        lines.append("No high-confidence parlays today - stick to singles or pass.")

    # ========== FOOTER ==========
    lines.append("")
    lines.append("=" * 50)
    lines.append("⚠️  Bet responsibly. Never bet more than you can afford to lose.")
    lines.append("=" * 50)

    return '\n'.join(lines)


def send_email(subject: str, body: str):
    """Send email with the analysis"""

    if not SENDER_PASSWORD:
        print("⚠️ NCAA_EMAIL_PASSWORD not set - skipping email")
        print("Set environment variable to enable email delivery")
        return False

    if not SENDER_EMAIL:
        print("⚠️ NCAA_EMAIL_FROM not set - skipping email")
        return False

    try:
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = SENDER_EMAIL
        message["To"] = RECIPIENT_EMAIL

        # Plain text version
        text_part = MIMEText(body, "plain")
        message.attach(text_part)

        # Connect and send
        context = ssl.create_default_context()

        # Fix for macOS certificate issues
        import certifi
        context.load_verify_locations(certifi.where())

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, message.as_string())

        print(f"✓ Email sent to {RECIPIENT_EMAIL}")
        return True

    except Exception as e:
        print(f"⚠️ Error sending email: {e}")
        return False


def main():
    """Main entry point"""
    # Find latest analysis file
    analysis_file = find_latest_analysis()

    if not analysis_file:
        print(f"Error: No analysis files found in {DATA_DIR}")
        print("Run the analyzer first: python analyze_games.py")
        return 1

    print(f"Loading analysis from: {analysis_file}")

    with open(analysis_file) as f:
        analysis_text = f.read()

    # Parse picks from analysis
    picks = parse_picks_from_analysis(analysis_text)

    total_picks = len(picks['spreads']) + len(picks['totals']) + len([p for p in picks['moneylines'] if p.get('stars', 0) > 0])
    print(f"  Found {len(picks['spreads'])} spread picks, {len(picks['totals'])} total picks, {len(picks['moneylines'])} ML picks")

    if total_picks == 0:
        print("  No valuable plays found today - skipping email")
        return 0

    # Build concise email
    email_body = build_concise_email(picks)

    # Send email
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"🏀 NCAA Picks - {today}"

    success = send_email(subject, email_body)

    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
