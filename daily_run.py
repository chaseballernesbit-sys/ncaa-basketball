#!/usr/bin/env python3
"""
NCAA Basketball Daily Runner
Runs scraper -> analyzer -> email in sequence
Designed to be called by launchd/cron at 8:30 AM ET
"""

import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
LOG_DIR = PROJECT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

def log(message: str):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def run_step(name: str, script: str) -> bool:
    """Run a Python script and return success status"""
    log(f"Starting: {name}")

    try:
        result = subprocess.run(
            [sys.executable, str(PROJECT_DIR / script)],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            log(f"✓ {name} completed successfully")
            if result.stdout:
                # Print last few lines of output
                lines = result.stdout.strip().split('\n')
                for line in lines[-5:]:
                    log(f"  {line}")
            return True
        else:
            log(f"✗ {name} failed with code {result.returncode}")
            if result.stderr:
                log(f"  Error: {result.stderr[:500]}")
            return False

    except subprocess.TimeoutExpired:
        log(f"✗ {name} timed out after 5 minutes")
        return False
    except Exception as e:
        log(f"✗ {name} error: {e}")
        return False

def main():
    """Run the full daily pipeline"""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"daily_run_{today}.log"

    log("=" * 60)
    log("NCAA BASKETBALL DAILY RUN")
    log("=" * 60)

    # Step 1: Scrape data
    if not run_step("Data Scraper", "scrape_ncaa_data.py"):
        log("⚠️ Scraper failed - continuing anyway (may use cached data)")

    # Step 2: Run analysis
    if not run_step("Game Analyzer", "analyze_games.py"):
        log("✗ Analysis failed - cannot send email")
        return 1

    # Step 3: Send email
    if not run_step("Email Report", "email_report.py"):
        log("⚠️ Email failed - check credentials")
        return 1

    log("=" * 60)
    log("✓ DAILY RUN COMPLETE")
    log("=" * 60)

    return 0

if __name__ == "__main__":
    sys.exit(main())
