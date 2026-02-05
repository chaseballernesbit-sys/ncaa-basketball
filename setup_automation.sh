#!/bin/bash
# NCAA Basketball Daily Email Automation Setup
# Run this script to configure daily emails at 8:30 AM

echo "=============================================="
echo "NCAA Basketball Daily Email Setup"
echo "=============================================="
echo ""

PLIST_SRC="/Users/mac/Documents/ncaa-basketball/com.ncaa.basketball.daily.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.ncaa.basketball.daily.plist"

# Check if already installed
if launchctl list | grep -q "com.ncaa.basketball.daily"; then
    echo "Automation is already installed. Unloading first..."
    launchctl unload "$PLIST_DST" 2>/dev/null
fi

echo ""
echo "Step 1: Gmail App Password"
echo "--------------------------"
echo "You need a Gmail App Password (NOT your regular password)."
echo ""
echo "To create one:"
echo "  1. Go to: https://myaccount.google.com/apppasswords"
echo "  2. Sign in to your Google account"
echo "  3. Select 'Mail' and 'Mac' as the app/device"
echo "  4. Click 'Generate'"
echo "  5. Copy the 16-character password"
echo ""
read -p "Enter your Gmail address: " GMAIL_ADDRESS
read -sp "Enter your Gmail App Password: " GMAIL_PASSWORD
echo ""

echo ""
echo "Step 2: Odds API Key (Optional)"
echo "-------------------------------"
echo "Get a FREE key at: https://the-odds-api.com/"
echo "(Press Enter to skip)"
read -p "Enter your Odds API key: " ODDS_KEY

# Create the plist with actual values
cat > "$PLIST_DST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ncaa.basketball.daily</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/mac/Documents/ncaa-basketball/daily_run.py</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>30</integer>
    </dict>

    <key>EnvironmentVariables</key>
    <dict>
        <key>NCAA_EMAIL_FROM</key>
        <string>${GMAIL_ADDRESS}</string>
        <key>NCAA_EMAIL_PASSWORD</key>
        <string>${GMAIL_PASSWORD}</string>
        <key>NCAA_EMAIL_TO</key>
        <string>chaseballernesbit@gmail.com</string>
        <key>ODDS_API_KEY</key>
        <string>${ODDS_KEY}</string>
    </dict>

    <key>StandardOutPath</key>
    <string>/Users/mac/Documents/ncaa-basketball/logs/launchd_stdout.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/mac/Documents/ncaa-basketball/logs/launchd_stderr.log</string>

    <key>WorkingDirectory</key>
    <string>/Users/mac/Documents/ncaa-basketball</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

echo ""
echo "Step 3: Installing automation..."
echo "--------------------------------"

# Load the plist
launchctl load "$PLIST_DST"

if launchctl list | grep -q "com.ncaa.basketball.daily"; then
    echo "✓ Automation installed successfully!"
    echo ""
    echo "The daily email will be sent at 8:30 AM every day."
    echo ""
    echo "To test it now, run:"
    echo "  launchctl start com.ncaa.basketball.daily"
    echo ""
    echo "To check status:"
    echo "  launchctl list | grep ncaa"
    echo ""
    echo "To uninstall:"
    echo "  launchctl unload ~/Library/LaunchAgents/com.ncaa.basketball.daily.plist"
    echo ""
    echo "Logs are saved to:"
    echo "  /Users/mac/Documents/ncaa-basketball/logs/"
else
    echo "✗ Installation failed. Check the plist file."
    exit 1
fi

echo ""
echo "=============================================="
echo "Setup complete!"
echo "=============================================="
