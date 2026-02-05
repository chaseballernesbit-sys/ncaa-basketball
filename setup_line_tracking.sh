#!/bin/bash
# Setup script for NCAA Basketball Line Tracking
#
# This sets up 4 scheduled jobs:
# - 8:30 AM: Full analysis + email (already exists)
# - 12:00 PM: Line tracking (sharp money detection)
# - 4:00 PM: Line tracking (pre-evening games)
# - 6:30 PM: Line tracking (final lines before games)
#
# Usage: ./setup_line_tracking.sh YOUR_ODDS_API_KEY

echo "NCAA Basketball - Line Movement Tracking Setup"
echo "=============================================="
echo ""

# Check for ODDS_API_KEY
if [ -z "$1" ]; then
    echo "Usage: ./setup_line_tracking.sh YOUR_ODDS_API_KEY"
    echo ""
    echo "Get a FREE API key at: https://the-odds-api.com/"
    echo "(Free tier: 500 requests/month - plenty for line tracking)"
    exit 1
fi

ODDS_API_KEY="$1"

# Update the plist files with the API key
echo "Updating launchd configuration with API key..."

# Update noon job
sed -i '' "s|<string></string>|<string>$ODDS_API_KEY</string>|" ~/Library/LaunchAgents/com.ncaa.basketball.lines.noon.plist
sed -i '' "s|<string>ODDS_API_KEY_HERE</string>|<string>$ODDS_API_KEY</string>|" ~/Library/LaunchAgents/com.ncaa.basketball.lines.noon.plist

# Update afternoon job
sed -i '' "s|<string></string>|<string>$ODDS_API_KEY</string>|" ~/Library/LaunchAgents/com.ncaa.basketball.lines.afternoon.plist
sed -i '' "s|<string>ODDS_API_KEY_HERE</string>|<string>$ODDS_API_KEY</string>|" ~/Library/LaunchAgents/com.ncaa.basketball.lines.afternoon.plist

# Update evening job
sed -i '' "s|<string></string>|<string>$ODDS_API_KEY</string>|" ~/Library/LaunchAgents/com.ncaa.basketball.lines.evening.plist
sed -i '' "s|<string>ODDS_API_KEY_HERE</string>|<string>$ODDS_API_KEY</string>|" ~/Library/LaunchAgents/com.ncaa.basketball.lines.evening.plist

echo "✓ API key configured"
echo ""

# Load the launchd jobs
echo "Loading scheduled jobs..."

launchctl unload ~/Library/LaunchAgents/com.ncaa.basketball.lines.noon.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.ncaa.basketball.lines.noon.plist
echo "✓ 12:00 PM line check loaded"

launchctl unload ~/Library/LaunchAgents/com.ncaa.basketball.lines.afternoon.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.ncaa.basketball.lines.afternoon.plist
echo "✓ 4:00 PM line check loaded"

launchctl unload ~/Library/LaunchAgents/com.ncaa.basketball.lines.evening.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.ncaa.basketball.lines.evening.plist
echo "✓ 6:30 PM line check loaded"

echo ""
echo "=============================================="
echo "LINE TRACKING SCHEDULE:"
echo ""
echo "  8:30 AM  - Full analysis + email"
echo "  12:00 PM - Line tracking (morning sharp action)"
echo "  4:00 PM  - Line tracking (afternoon movement)"
echo "  6:30 PM  - Line tracking (pre-game lines)"
echo ""
echo "=============================================="
echo ""
echo "To run line tracking manually:"
echo "  python3 /Users/mac/Documents/ncaa-basketball/track_lines.py"
echo ""
echo "To check job status:"
echo "  launchctl list | grep ncaa.basketball"
echo ""
echo "Line history stored in:"
echo "  /Users/mac/Documents/ncaa-basketball/data/line_history/"
echo ""
