#!/usr/bin/env python3
"""
NCAA Basketball - Line Movement Tracker
Lightweight script to track line movement throughout the day.
Run multiple times to build line history.
"""

import json
import sys
import logging
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from config import DATA_DIR, LOGS_DIR, ODDS_API_KEY
from scrape_ncaa_data import NCAADataScraper

# Configure logging
log_file = LOGS_DIR / f"line_tracker_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def main():
    """Track current lines and update history"""
    logger.info("=" * 50)
    logger.info(f"Line Movement Tracker - {datetime.now().strftime('%H:%M')}")
    logger.info("=" * 50)

    if not ODDS_API_KEY:
        logger.error("ODDS_API_KEY not set - cannot track lines")
        return 1

    scraper = NCAADataScraper()

    # Fetch current odds
    logger.info("Fetching current odds...")
    odds = scraper.scrape_odds_api()

    if not odds:
        logger.warning("No odds returned from API")
        return 1

    logger.info(f"Got odds for {len(odds)} games")

    # Update line history
    logger.info("Updating line history...")
    history = scraper.update_line_history(odds)

    # Calculate movement
    movement = scraper.calculate_line_movement(history)

    # Log sharp action
    sharp_count = 0
    for game_key, mv in movement.items():
        if mv.get('has_sharp_action'):
            sharp_count += 1
            logger.info(f"SHARP ACTION: {game_key}")
            for signal in mv.get('signals', []):
                logger.info(f"  → {signal}")

    # Summary
    logger.info("=" * 50)
    logger.info(f"Tracking {len(movement)} games")
    logger.info(f"Snapshots today: {len(history.get('snapshots', []))}")
    logger.info(f"Sharp action detected: {sharp_count} games")
    logger.info("=" * 50)

    # If we have the full data file, update it with line movement
    today = datetime.now().strftime('%Y%m%d')
    data_file = DATA_DIR / f"ncaa_data_{today}.json"

    if data_file.exists():
        logger.info(f"Updating {data_file} with line movement data...")
        with open(data_file, 'r') as f:
            data = json.load(f)

        # Update games with line movement
        for game in data.get('games', []):
            away = game.get('away', {}).get('name', '')
            home = game.get('home', {}).get('name', '')
            game_key = f"{away}@{home}"

            if game_key in movement:
                game['line_movement'] = movement[game_key]

        # Update summary
        sharp_games = [k for k, v in movement.items() if v.get('has_sharp_action')]
        data['line_movement_summary'] = {
            'games_tracked': len(movement),
            'snapshots_today': len(history.get('snapshots', [])),
            'sharp_action_games': sharp_games,
            'sharp_action_count': len(sharp_games),
            'last_updated': datetime.now().isoformat(),
        }

        with open(data_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        logger.info("Data file updated with line movement")

    return 0


if __name__ == "__main__":
    sys.exit(main())
