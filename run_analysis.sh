#!/bin/bash
#
# NCAA Basketball Daily Analysis Runner
# Scrapes data, generates analysis, and sends email
#
# Usage:
#   ./run_analysis.sh              # Run for today
#   ./run_analysis.sh 20260204     # Run for specific date
#   ./run_analysis.sh --no-email   # Run without sending email
#
# Scheduled daily at 8:30 AM via crontab

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load environment variables (handle both interactive and non-interactive shells)
if [ -f ~/.zshrc ]; then
    # Extract just the export statements
    eval "$(grep '^export ' ~/.zshrc 2>/dev/null || true)"
fi

# Ensure key variables are set (fallback for launchd which sets them in plist)
: "${ODDS_API_KEY:=}"
: "${NCAA_EMAIL_TO:=}"
: "${NCAA_EMAIL_FROM:=}"
: "${NCAA_EMAIL_PASSWORD:=}"

# Parse arguments
SEND_EMAIL=true
DATE_ARG=""

for arg in "$@"; do
    case $arg in
        --no-email)
            SEND_EMAIL=false
            ;;
        *)
            DATE_ARG="$arg"
            ;;
    esac
done

echo "========================================"
echo "NCAA Basketball Analysis - $(date)"
echo "========================================"
echo ""

# Check API key
if [ -z "$ODDS_API_KEY" ]; then
    echo "WARNING: ODDS_API_KEY not set. Using ESPN odds only."
else
    echo "✓ Odds API key configured"
fi

echo ""

# Step 1: Run the scraper
echo "[STEP 1/3] Scraping data from all sources..."
if [ -n "$DATE_ARG" ]; then
    python3 scrape_ncaa_data.py "$DATE_ARG"
else
    python3 scrape_ncaa_data.py
fi

if [ $? -ne 0 ]; then
    echo "ERROR: Data scraping failed!"
    exit 1
fi

echo ""

# Step 2: Run analysis
echo "[STEP 2/3] Running analysis engine..."
python3 analyze_games.py

if [ $? -ne 0 ]; then
    echo "ERROR: Analysis failed!"
    exit 1
fi

echo ""

# Step 3: Send email
TODAY=$(date +%Y%m%d)
ANALYSIS_FILE="data/analysis_${DATE_ARG:-$TODAY}.md"

if [ "$SEND_EMAIL" = true ]; then
    echo "[STEP 3/3] Sending email..."
    python3 send_email.py "$ANALYSIS_FILE"

    if [ $? -ne 0 ]; then
        echo "WARNING: Email sending failed, but analysis is complete."
    fi
else
    echo "[STEP 3/3] Skipping email (--no-email flag)"
fi

echo ""
echo "========================================"
echo "COMPLETE"
echo "========================================"
echo "Data: data/ncaa_data_${DATE_ARG:-$TODAY}.json"
echo "Analysis: $ANALYSIS_FILE"
echo "========================================"
