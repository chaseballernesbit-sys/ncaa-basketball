#!/usr/bin/env python3
"""
Betting Mathematics Module
Handles odds conversion, EV calculation, Kelly Criterion, and bet filtering
"""

from typing import Dict, List, Optional, Tuple
import math


# =============================================================================
# ODDS CONVERSION
# =============================================================================

def american_to_decimal(american: int) -> float:
    """Convert American odds to decimal odds"""
    if american > 0:
        return (american / 100) + 1
    else:
        return (100 / abs(american)) + 1


def american_to_implied_prob(american: int) -> float:
    """
    Convert American odds to implied probability (includes vig)

    Examples:
        -110 → 52.4% (standard spread)
        -200 → 66.7% (moderate favorite)
        -455 → 82.0% (heavy favorite)
        +150 → 40.0% (underdog)
        +300 → 25.0% (big underdog)
    """
    if american < 0:
        return abs(american) / (abs(american) + 100)
    else:
        return 100 / (american + 100)


def implied_prob_to_american(prob: float) -> int:
    """Convert implied probability back to American odds"""
    if prob >= 0.5:
        return int(-100 * prob / (1 - prob))
    else:
        return int(100 * (1 - prob) / prob)


def remove_vig(prob1: float, prob2: float) -> Tuple[float, float]:
    """
    Remove vig from two-way market probabilities
    Returns true probabilities that sum to 100%
    """
    total = prob1 + prob2
    return prob1 / total, prob2 / total


# =============================================================================
# EXPECTED VALUE CALCULATIONS
# =============================================================================

def calculate_ev(model_prob: float, american_odds: int, stake: float = 100) -> float:
    """
    Calculate Expected Value for a bet

    EV = (Probability of Win × Profit) - (Probability of Loss × Stake)

    Args:
        model_prob: Our model's win probability (0-1)
        american_odds: The betting odds
        stake: Bet amount (default $100)

    Returns:
        Expected value in dollars
    """
    decimal_odds = american_to_decimal(american_odds)
    profit_if_win = stake * (decimal_odds - 1)

    ev = (model_prob * profit_if_win) - ((1 - model_prob) * stake)
    return ev


def calculate_ev_percentage(model_prob: float, american_odds: int) -> float:
    """
    Calculate EV as a percentage of stake (ROI)

    Example: 5.2% ROI means $5.20 expected profit per $100 bet
    """
    ev = calculate_ev(model_prob, american_odds, stake=100)
    return ev  # Already per $100, so this is the percentage


def calculate_true_edge(model_prob: float, american_odds: int) -> float:
    """
    Calculate true edge: Model probability minus break-even probability

    This is the "real" edge after accounting for juice

    Example:
        Model says 55% win probability
        Odds are -110 (requires 52.4% to break even)
        True edge = 55% - 52.4% = 2.6%
    """
    implied_prob = american_to_implied_prob(american_odds)
    return model_prob - implied_prob


# =============================================================================
# KELLY CRITERION & BET SIZING
# =============================================================================

def kelly_criterion(model_prob: float, american_odds: int) -> float:
    """
    Calculate optimal bet size using Kelly Criterion

    Kelly % = (bp - q) / b
    where:
        b = decimal odds - 1 (profit per $1 bet)
        p = probability of winning
        q = probability of losing (1 - p)

    Returns fraction of bankroll to bet (0-1)
    """
    if model_prob <= 0 or model_prob >= 1:
        return 0

    decimal_odds = american_to_decimal(american_odds)
    b = decimal_odds - 1  # Profit multiplier
    p = model_prob
    q = 1 - p

    kelly = (b * p - q) / b

    # Kelly can be negative (don't bet) or very high (risky)
    return max(0, kelly)


def fractional_kelly(model_prob: float, american_odds: int, fraction: float = 0.25) -> float:
    """
    Calculate fractional Kelly (more conservative)

    Most professional bettors use 1/4 or 1/2 Kelly to reduce variance
    """
    full_kelly = kelly_criterion(model_prob, american_odds)
    return full_kelly * fraction


def edge_to_units(true_edge: float, ev_pct: float) -> float:
    """
    Convert edge to unit recommendation

    Conservative approach:
        < 2% true edge: 0.5 units (small)
        2-5% true edge: 1 unit (standard)
        5-8% true edge: 1.5 units
        8-12% true edge: 2 units
        12%+ true edge: 2.5 units (max)

    Also factors in EV% - high edge but low EV (heavy favorite) gets reduced
    """
    if true_edge < 0.02:
        base_units = 0.5
    elif true_edge < 0.05:
        base_units = 1.0
    elif true_edge < 0.08:
        base_units = 1.5
    elif true_edge < 0.12:
        base_units = 2.0
    else:
        base_units = 2.5

    # Reduce units if EV% is low (heavy favorite with small profit potential)
    if ev_pct < 3:
        base_units *= 0.5
    elif ev_pct < 5:
        base_units *= 0.75

    return round(base_units, 1)


# =============================================================================
# BET QUALITY ASSESSMENT
# =============================================================================

def assess_bet_quality(model_prob: float, american_odds: int) -> Dict:
    """
    Comprehensive bet quality assessment

    Returns all relevant metrics for a bet
    """
    implied_prob = american_to_implied_prob(american_odds)
    true_edge = model_prob - implied_prob
    ev = calculate_ev(model_prob, american_odds)
    ev_pct = ev  # Per $100
    kelly = kelly_criterion(model_prob, american_odds)
    half_kelly = fractional_kelly(model_prob, american_odds, 0.5)
    quarter_kelly = fractional_kelly(model_prob, american_odds, 0.25)
    units = edge_to_units(true_edge, ev_pct)

    # Determine bet grade
    if true_edge >= 0.10 and ev_pct >= 8:
        grade = 'A'
        verdict = 'Strong bet'
    elif true_edge >= 0.05 and ev_pct >= 5:
        grade = 'B'
        verdict = 'Good bet'
    elif true_edge >= 0.03 and ev_pct >= 3:
        grade = 'C'
        verdict = 'Marginal bet'
    elif true_edge > 0:
        grade = 'D'
        verdict = 'Juice eats edge'
    else:
        grade = 'F'
        verdict = 'Negative EV'

    return {
        'model_prob': model_prob,
        'implied_prob': implied_prob,
        'true_edge': true_edge,
        'ev': ev,
        'ev_pct': ev_pct,
        'kelly': kelly,
        'half_kelly': half_kelly,
        'quarter_kelly': quarter_kelly,
        'units': units,
        'grade': grade,
        'verdict': verdict,
        'is_profitable': true_edge > 0 and ev > 0,
        'is_worth_betting': true_edge >= 0.03 and ev_pct >= 3,
    }


def filter_bets_by_value(bets: List[Dict], min_true_edge: float = 0.03,
                          min_ev: float = 3.0, max_implied_prob: float = 0.85) -> List[Dict]:
    """
    Filter bets to only include those worth betting

    Args:
        bets: List of bet dictionaries with 'model_prob' and 'odds'
        min_true_edge: Minimum true edge (default 3%)
        min_ev: Minimum EV per $100 (default $3)
        max_implied_prob: Max implied prob (filters heavy favorites, default 85%)

    Returns:
        Filtered list of bets that meet criteria
    """
    worthy_bets = []

    for bet in bets:
        model_prob = bet.get('model_prob', 0.5)
        odds = bet.get('odds', -110)

        assessment = assess_bet_quality(model_prob, odds)

        # Filter criteria
        if assessment['true_edge'] < min_true_edge:
            continue
        if assessment['ev_pct'] < min_ev:
            continue
        if assessment['implied_prob'] > max_implied_prob:
            continue

        # Add assessment to bet
        bet['assessment'] = assessment
        worthy_bets.append(bet)

    return worthy_bets


# =============================================================================
# PARLAY CALCULATIONS
# =============================================================================

def calculate_parlay_odds(legs: List[int]) -> int:
    """
    Calculate combined parlay odds from individual American odds

    Args:
        legs: List of American odds for each leg

    Returns:
        Combined American odds for the parlay
    """
    combined_decimal = 1.0
    for odds in legs:
        combined_decimal *= american_to_decimal(odds)

    # Convert back to American
    if combined_decimal >= 2.0:
        return int((combined_decimal - 1) * 100)
    else:
        return int(-100 / (combined_decimal - 1))


def calculate_parlay_ev(legs: List[Dict]) -> Dict:
    """
    Calculate parlay EV given legs with model probabilities

    Args:
        legs: List of dicts with 'model_prob' and 'odds'

    Returns:
        Parlay assessment including combined prob, odds, and EV
    """
    combined_model_prob = 1.0
    combined_implied_prob = 1.0
    odds_list = []

    for leg in legs:
        model_prob = leg.get('model_prob', 0.5)
        odds = leg.get('odds', -110)

        combined_model_prob *= model_prob
        combined_implied_prob *= american_to_implied_prob(odds)
        odds_list.append(odds)

    parlay_odds = calculate_parlay_odds(odds_list)
    ev = calculate_ev(combined_model_prob, parlay_odds)
    true_edge = combined_model_prob - combined_implied_prob

    return {
        'combined_model_prob': combined_model_prob,
        'combined_implied_prob': combined_implied_prob,
        'parlay_odds': parlay_odds,
        'ev': ev,
        'ev_pct': ev,
        'true_edge': true_edge,
        'is_positive_ev': ev > 0,
        'num_legs': len(legs),
    }


def calculate_parlay_payout(stake: float, legs: List[int]) -> float:
    """Calculate total payout (stake + profit) for a parlay"""
    parlay_odds = calculate_parlay_odds(legs)
    decimal = american_to_decimal(parlay_odds)
    return stake * decimal


# =============================================================================
# SPREAD/TOTAL SPECIFIC CALCULATIONS
# =============================================================================

def spread_model_prob_from_edge(point_edge: float) -> float:
    """
    Convert point spread edge to win probability

    Based on historical data:
    - Each point of edge ≈ 3% win probability
    - Capped at reasonable bounds

    Example:
        3 point edge → ~59% win probability
        5 point edge → ~65% win probability
        10 point edge → ~80% win probability
    """
    # Logistic function to model diminishing returns
    # At 0 edge = 50%, increases with edge
    base_prob = 0.50
    edge_factor = 0.03  # 3% per point, diminishing

    # Use a softer curve that caps at ~85%
    if point_edge <= 0:
        return base_prob

    # Diminishing returns formula
    prob = base_prob + (0.35 * (1 - math.exp(-edge_factor * point_edge)))
    return min(0.85, max(0.50, prob))


def total_model_prob_from_edge(point_edge: float) -> float:
    """
    Convert total edge to win probability

    Similar to spread, but totals are slightly more volatile
    """
    base_prob = 0.50
    edge_factor = 0.025  # Slightly less confident on totals

    if point_edge <= 0:
        return base_prob

    prob = base_prob + (0.35 * (1 - math.exp(-edge_factor * point_edge)))
    return min(0.80, max(0.50, prob))


def ml_model_prob_from_margin(predicted_margin: float) -> float:
    """
    Convert predicted margin to moneyline win probability

    Based on historical correlation between margin and win %:
    - 0 point margin = 50%
    - 5 point margin ≈ 70%
    - 10 point margin ≈ 85%
    - 15+ point margin ≈ 92%+
    """
    if predicted_margin <= 0:
        # Underdog
        return 0.50 - (0.35 * (1 - math.exp(0.05 * predicted_margin)))
    else:
        # Favorite
        return 0.50 + (0.42 * (1 - math.exp(-0.05 * predicted_margin)))


# =============================================================================
# FORMATTING HELPERS
# =============================================================================

def format_odds(american: int) -> str:
    """Format American odds with + sign for positive"""
    if american > 0:
        return f"+{american}"
    return str(american)


def format_prob(prob: float) -> str:
    """Format probability as percentage"""
    return f"{prob * 100:.1f}%"


def format_ev(ev: float) -> str:
    """Format EV with + sign and dollar"""
    if ev >= 0:
        return f"+${ev:.2f}"
    return f"-${abs(ev):.2f}"


def format_edge(edge: float) -> str:
    """Format edge as percentage with + sign"""
    if edge >= 0:
        return f"+{edge * 100:.1f}%"
    return f"{edge * 100:.1f}%"


def get_bet_summary(model_prob: float, american_odds: int) -> str:
    """
    Get a one-line summary of bet quality

    Example: "Model: 58% | Need: 52.4% | Edge: +5.6% | EV: +$6.20 | Grade: B"
    """
    assessment = assess_bet_quality(model_prob, american_odds)

    return (
        f"Model: {format_prob(assessment['model_prob'])} | "
        f"Need: {format_prob(assessment['implied_prob'])} | "
        f"Edge: {format_edge(assessment['true_edge'])} | "
        f"EV: {format_ev(assessment['ev'])} | "
        f"Grade: {assessment['grade']}"
    )


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("BETTING MATH EXAMPLES")
    print("=" * 60)

    # Example 1: Standard spread bet
    print("\n1. SPREAD BET: -110 odds, model says 57% to cover")
    assessment = assess_bet_quality(0.57, -110)
    print(f"   Implied prob (break-even): {format_prob(assessment['implied_prob'])}")
    print(f"   True edge: {format_edge(assessment['true_edge'])}")
    print(f"   EV per $100: {format_ev(assessment['ev'])}")
    print(f"   Kelly: {assessment['kelly']:.1%} of bankroll")
    print(f"   Recommended: {assessment['units']} units")
    print(f"   Grade: {assessment['grade']} - {assessment['verdict']}")

    # Example 2: Heavy favorite
    print("\n2. HEAVY FAVORITE ML: -350 odds, model says 82%")
    assessment = assess_bet_quality(0.82, -350)
    print(f"   Implied prob (break-even): {format_prob(assessment['implied_prob'])}")
    print(f"   True edge: {format_edge(assessment['true_edge'])}")
    print(f"   EV per $100: {format_ev(assessment['ev'])}")
    print(f"   Recommended: {assessment['units']} units")
    print(f"   Grade: {assessment['grade']} - {assessment['verdict']}")

    # Example 3: Value underdog
    print("\n3. UNDERDOG ML: +180 odds, model says 42%")
    assessment = assess_bet_quality(0.42, 180)
    print(f"   Implied prob (break-even): {format_prob(assessment['implied_prob'])}")
    print(f"   True edge: {format_edge(assessment['true_edge'])}")
    print(f"   EV per $100: {format_ev(assessment['ev'])}")
    print(f"   Recommended: {assessment['units']} units")
    print(f"   Grade: {assessment['grade']} - {assessment['verdict']}")

    # Example 4: 2-leg parlay
    print("\n4. 2-LEG PARLAY: Two -110 bets, model says 57% each")
    parlay = calculate_parlay_ev([
        {'model_prob': 0.57, 'odds': -110},
        {'model_prob': 0.57, 'odds': -110},
    ])
    print(f"   Combined model prob: {format_prob(parlay['combined_model_prob'])}")
    print(f"   Combined implied prob: {format_prob(parlay['combined_implied_prob'])}")
    print(f"   Parlay odds: {format_odds(parlay['parlay_odds'])}")
    print(f"   EV per $100: {format_ev(parlay['ev'])}")
    print(f"   Positive EV: {'Yes ✓' if parlay['is_positive_ev'] else 'No ✗'}")
