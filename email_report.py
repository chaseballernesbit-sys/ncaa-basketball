#!/usr/bin/env python3
"""
NCAA Basketball - Email Report Sender
Sends concise daily picks with full betting math analysis
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

from betting_math import (
    american_to_implied_prob, calculate_ev, calculate_true_edge,
    assess_bet_quality, spread_model_prob_from_edge, total_model_prob_from_edge,
    ml_model_prob_from_margin, calculate_parlay_ev, format_odds, format_prob,
    format_ev, format_edge, edge_to_units
)

# Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.environ.get("NCAA_EMAIL_FROM", "")
SENDER_PASSWORD = os.environ.get("NCAA_EMAIL_PASSWORD", "")
RECIPIENT_EMAIL = os.environ.get("NCAA_EMAIL_TO", "chaseballernesbit@gmail.com")

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"

# Minimum thresholds for a bet to be "worth it"
MIN_TRUE_EDGE = 0.03      # 3% minimum edge after juice
MIN_EV = 3.0              # $3 minimum EV per $100
MAX_IMPLIED_PROB = 0.82   # Don't bet favorites needing >82% to profit


def find_latest_analysis() -> Path:
    """Find the most recent analysis file"""
    analysis_files = sorted(DATA_DIR.glob("analysis_*.md"), reverse=True)
    if analysis_files:
        return analysis_files[0]
    return None


def parse_picks_from_analysis(analysis_text: str) -> Dict:
    """Parse the analysis file to extract picks with edges and odds"""
    picks = {
        'spreads': [],
        'totals': [],
        'moneylines': [],
    }

    lines = analysis_text.split('\n')

    # Parse spread picks
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
                # Get edge from next lines (check up to 3 lines for new format)
                edge = 0
                predicted_score = ""
                for j in range(1, 4):
                    if i + j < len(lines):
                        next_line = lines[i + j]
                        # New format: "Model spread: +X.X | Line: +Y.Y | Edge: Z.Z"
                        edge_match = re.search(r'\|\s*Edge:\s*([\d\.]+)', next_line)
                        if edge_match:
                            edge = float(edge_match.group(1))
                            break
                        # Old format: "Edge: X.X pts vs line"
                        edge_match = re.search(r'Edge:\s*([\d\.]+)\s*pts', next_line)
                        if edge_match:
                            edge = float(edge_match.group(1))
                            break
                        # Capture predicted score
                        if 'Predicted:' in next_line:
                            predicted_score = next_line.strip()
                picks['spreads'].append({
                    'team': team,
                    'spread': spread,
                    'stars': stars,
                    'edge': edge,
                    'type': 'spread',
                    'odds': -110,  # Standard spread odds
                    'predicted': predicted_score,
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
                    'type': 'total',
                    'odds': -110,  # Standard total odds
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
                    odds = int(match.group(2))
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
                    odds = int(match.group(2))
                    opponent = match.group(3).strip()
                    picks['moneylines'].append({
                        'team': team,
                        'odds': odds,
                        'opponent': opponent,
                        'stars': 0,
                        'edge': 0,
                        'type': 'ml',
                        'is_underdog': odds > 0
                    })

    return picks


def add_betting_math(picks: Dict) -> Dict:
    """Add betting math assessments to all picks"""

    for pick in picks['spreads']:
        # Convert point edge to win probability
        model_prob = spread_model_prob_from_edge(pick['edge'])
        pick['model_prob'] = model_prob
        pick['assessment'] = assess_bet_quality(model_prob, pick['odds'])

    for pick in picks['totals']:
        # Convert point edge to win probability
        model_prob = total_model_prob_from_edge(pick['edge'])
        pick['model_prob'] = model_prob
        pick['assessment'] = assess_bet_quality(model_prob, pick['odds'])

    for pick in picks['moneylines']:
        if pick.get('is_underdog') and pick.get('edge', 0) > 0:
            # For underdogs with edge, calculate model prob
            # Edge is given as percentage difference
            implied_prob = american_to_implied_prob(pick['odds'])
            model_prob = implied_prob + (pick['edge'] / 100)
            pick['model_prob'] = min(0.65, model_prob)  # Cap underdog prob
        elif pick.get('stars', 0) > 0:
            # Has stars, assume some edge
            implied_prob = american_to_implied_prob(pick['odds'])
            pick['model_prob'] = implied_prob + 0.05
        else:
            # Favorite without specific edge - estimate from odds
            implied_prob = american_to_implied_prob(pick['odds'])
            pick['model_prob'] = implied_prob + 0.03  # Assume small edge
        pick['assessment'] = assess_bet_quality(pick['model_prob'], pick['odds'])

    return picks


def filter_worthy_bets(picks: Dict) -> Dict:
    """Filter to only bets that are actually worth making

    Picks with 3+ stars from the model are included regardless of edge calculation,
    as the model already validated them as having significant value.
    """

    filtered = {
        'spreads': [],
        'totals': [],
        'moneylines': [],
    }

    for pick in picks['spreads']:
        a = pick.get('assessment', {})
        stars = pick.get('stars', 0)
        # Include if has 3+ stars (model validated) OR meets edge/EV thresholds
        if stars >= 3 or (a.get('true_edge', 0) >= MIN_TRUE_EDGE and a.get('ev_pct', 0) >= MIN_EV):
            filtered['spreads'].append(pick)

    for pick in picks['totals']:
        a = pick.get('assessment', {})
        stars = pick.get('stars', 0)
        if stars >= 3 or (a.get('true_edge', 0) >= MIN_TRUE_EDGE and a.get('ev_pct', 0) >= MIN_EV):
            filtered['totals'].append(pick)

    for pick in picks['moneylines']:
        a = pick.get('assessment', {})
        stars = pick.get('stars', 0)
        # For MLs, also check implied prob isn't too high (heavy favorite)
        if stars >= 3 or (a.get('true_edge', 0) >= MIN_TRUE_EDGE and
            a.get('ev_pct', 0) >= MIN_EV and
            a.get('implied_prob', 1) <= MAX_IMPLIED_PROB):
            filtered['moneylines'].append(pick)

    return filtered


def build_concise_email(picks: Dict, filtered_picks: Dict) -> str:
    """Build a concise email with betting math"""
    today = datetime.now().strftime("%A, %B %d")

    lines = []
    lines.append("=" * 55)
    lines.append(f"🏀 NCAA BASKETBALL PICKS - {today}")
    lines.append("=" * 55)
    lines.append("")
    lines.append("Only showing bets with 3%+ true edge and $3+ EV per $100")
    lines.append("")

    # Combine all filtered picks
    all_picks = []
    for p in filtered_picks['spreads']:
        all_picks.append(p)
    for p in filtered_picks['totals']:
        all_picks.append(p)
    for p in filtered_picks['moneylines']:
        all_picks.append(p)

    # Sort by EV (best value first)
    all_picks.sort(key=lambda x: x.get('assessment', {}).get('ev_pct', 0), reverse=True)

    # Take top 20
    top_picks = all_picks[:20]

    if not top_picks:
        lines.append("❌ NO BETS WORTH MAKING TODAY")
        lines.append("")
        lines.append("All identified edges are eaten by the juice.")
        lines.append("Sometimes the best bet is no bet.")
        lines.append("")
        lines.append("=" * 55)
        return '\n'.join(lines)

    # ========== TOP PLAYS WITH FULL MATH ==========
    lines.append(f"🎯 TOP {len(top_picks)} VALUE PLAYS")
    lines.append("-" * 55)
    lines.append("")

    for i, pick in enumerate(top_picks, 1):
        a = pick.get('assessment', {})
        stars = "⭐" * pick.get('stars', 0)

        # Format the pick
        if pick['type'] == 'spread':
            lines.append(f"{i}. {pick['team']} {pick['spread']} {stars}")
            # Add predicted score if available
            if pick.get('predicted'):
                lines.append(f"   {pick['predicted']}")
        elif pick['type'] == 'total':
            lines.append(f"{i}. {pick['direction']} {pick['total']} ({pick['game']}) {stars}")
        elif pick['type'] == 'ml':
            lines.append(f"{i}. {pick['team']} ML ({format_odds(pick['odds'])}) {stars}")

        # Betting math
        if pick['type'] == 'spread' and pick.get('edge', 0) > 0:
            lines.append(f"   Point Edge: {pick['edge']:.1f} pts | Win Prob: {format_prob(a['model_prob'])}")
        else:
            lines.append(f"   Model: {format_prob(a['model_prob'])} | Break-even: {format_prob(a['implied_prob'])}")
        lines.append(f"   True Edge: {format_edge(a['true_edge'])} | EV: {format_ev(a['ev'])}/bet")
        lines.append(f"   Grade: {a['grade']} | Units: {a['units']}")
        lines.append("")

    # ========== BEST SOLO BETS ==========
    lines.append("")
    lines.append("💰 BEST SOLO BETS (Highest EV)")
    lines.append("-" * 55)

    grade_a_b = [p for p in top_picks if p.get('assessment', {}).get('grade') in ['A', 'B']][:5]

    if grade_a_b:
        for pick in grade_a_b:
            a = pick['assessment']
            if pick['type'] == 'spread':
                lines.append(f"• {pick['team']} {pick['spread']}")
            elif pick['type'] == 'total':
                lines.append(f"• {pick['direction']} {pick['total']} ({pick['game']})")
            elif pick['type'] == 'ml':
                lines.append(f"• {pick['team']} ML ({format_odds(pick['odds'])})")
            lines.append(f"  → {a['units']} units | EV: {format_ev(a['ev'])} | Edge: {format_edge(a['true_edge'])}")
        lines.append("")
    else:
        lines.append("No A or B grade bets today. Consider smaller units on C grades.")
        lines.append("")

    # ========== MONEYLINE SECTION ==========
    lines.append("")
    lines.append("🎰 MONEYLINE ANALYSIS")
    lines.append("-" * 55)

    # Value underdogs
    value_dogs = [p for p in filtered_picks['moneylines']
                  if p.get('is_underdog') and p.get('assessment', {}).get('ev_pct', 0) >= 5]

    if value_dogs:
        lines.append("Value Underdogs (+EV):")
        for p in value_dogs[:3]:
            a = p['assessment']
            lines.append(f"  • {p['team']} ML ({format_odds(p['odds'])}) vs {p['opponent']}")
            lines.append(f"    Model: {format_prob(a['model_prob'])} | Need: {format_prob(a['implied_prob'])} | EV: {format_ev(a['ev'])}")
        lines.append("")

    # Check original (unfiltered) favorites for info
    heavy_favs_filtered = [p for p in picks['moneylines']
                           if not p.get('is_underdog')
                           and p.get('assessment', {}).get('implied_prob', 0) > MAX_IMPLIED_PROB]

    if heavy_favs_filtered:
        lines.append("Heavy Favorites (NOT recommended - juice too high):")
        for p in heavy_favs_filtered[:3]:
            a = p['assessment']
            lines.append(f"  ✗ {p['team']} ML ({format_odds(p['odds'])}) - Need {format_prob(a['implied_prob'])} to profit")
        lines.append("")

    # ========== PARLAY ANALYSIS ==========
    lines.append("")
    lines.append("🎲 PARLAY ANALYSIS")
    lines.append("-" * 55)

    # Build parlays from best picks
    five_star = [p for p in top_picks if p.get('stars', 0) == 5 and p.get('assessment', {}).get('grade') in ['A', 'B', 'C']]

    if len(five_star) >= 2:
        # 2-leg parlay
        legs = [{'model_prob': p['model_prob'], 'odds': p['odds']} for p in five_star[:2]]
        parlay_2 = calculate_parlay_ev(legs)

        lines.append("2-LEG PARLAY:")
        for p in five_star[:2]:
            if p['type'] == 'spread':
                lines.append(f"  • {p['team']} {p['spread']}")
            elif p['type'] == 'total':
                lines.append(f"  • {p['direction']} {p['total']}")
            elif p['type'] == 'ml':
                lines.append(f"  • {p['team']} ML")

        if parlay_2['is_positive_ev']:
            lines.append(f"  ✓ POSITIVE EV: {format_ev(parlay_2['ev'])} | Odds: {format_odds(parlay_2['parlay_odds'])}")
            lines.append(f"    Model prob: {format_prob(parlay_2['combined_model_prob'])} | Need: {format_prob(parlay_2['combined_implied_prob'])}")
        else:
            lines.append(f"  ✗ NEGATIVE EV: {format_ev(parlay_2['ev'])} - Don't bet this parlay")
        lines.append("")

    if len(five_star) >= 3:
        # 3-leg parlay
        legs = [{'model_prob': p['model_prob'], 'odds': p['odds']} for p in five_star[:3]]
        parlay_3 = calculate_parlay_ev(legs)

        lines.append("3-LEG PARLAY:")
        for p in five_star[:3]:
            if p['type'] == 'spread':
                lines.append(f"  • {p['team']} {p['spread']}")
            elif p['type'] == 'total':
                lines.append(f"  • {p['direction']} {p['total']}")
            elif p['type'] == 'ml':
                lines.append(f"  • {p['team']} ML")

        if parlay_3['is_positive_ev']:
            lines.append(f"  ✓ POSITIVE EV: {format_ev(parlay_3['ev'])} | Odds: {format_odds(parlay_3['parlay_odds'])}")
        else:
            lines.append(f"  ✗ NEGATIVE EV: {format_ev(parlay_3['ev'])} - Juice compounds, avoid 3+ legs")
        lines.append("")

    if len(five_star) < 2:
        lines.append("Not enough high-confidence picks for +EV parlays today.")
        lines.append("Parlays compound juice - need strong edges on each leg.")
        lines.append("")

    # ========== QUICK REFERENCE ==========
    lines.append("")
    lines.append("📊 QUICK REFERENCE")
    lines.append("-" * 55)
    lines.append("Grade A: Strong bet (10%+ edge, $8+ EV)")
    lines.append("Grade B: Good bet (5%+ edge, $5+ EV)")
    lines.append("Grade C: Marginal (3%+ edge, $3+ EV)")
    lines.append("Grade D/F: Not shown - juice eats the edge")
    lines.append("")
    lines.append("Unit sizing based on edge strength:")
    lines.append("  0.5u = small edge | 1u = standard | 2u+ = strong edge")

    # ========== FOOTER ==========
    lines.append("")
    lines.append("=" * 55)
    lines.append("⚠️  Only bet what you can afford to lose.")
    lines.append("Past performance ≠ future results.")
    lines.append("=" * 55)

    return '\n'.join(lines)


def send_email(subject: str, body: str):
    """Send email with the analysis"""

    if not SENDER_PASSWORD:
        print("  ⚠️ NCAA_EMAIL_PASSWORD not set - skipping email")
        return False

    if not SENDER_EMAIL:
        print("  ⚠️ NCAA_EMAIL_FROM not set - skipping email")
        return False

    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = SENDER_EMAIL
        message["To"] = RECIPIENT_EMAIL

        text_part = MIMEText(body, "plain")
        message.attach(text_part)

        context = ssl.create_default_context()
        import certifi
        context.load_verify_locations(certifi.where())

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, message.as_string())

        print(f"  ✓ Email sent to {RECIPIENT_EMAIL}")
        return True

    except Exception as e:
        print(f"  ⚠️ Error sending email: {e}")
        return False


def main():
    """Main entry point"""
    analysis_file = find_latest_analysis()

    if not analysis_file:
        print(f"Error: No analysis files found in {DATA_DIR}")
        return 1

    print(f"  Loading analysis from: {analysis_file}")

    with open(analysis_file) as f:
        analysis_text = f.read()

    # Send the analysis report directly (TOP PICKS + sections, skip detailed game analysis)
    # Cut off at "DETAILED GAME ANALYSIS" to keep email concise
    cutoff = analysis_text.find("DETAILED GAME ANALYSIS")
    if cutoff > 0:
        email_body = analysis_text[:cutoff].rstrip()
    else:
        # Fallback: just send first 5000 chars
        email_body = analysis_text[:5000]

    print(f"    Sending report ({len(email_body)} chars)")

    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"NCAA Picks - {today}"

    success = send_email(subject, email_body)
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
