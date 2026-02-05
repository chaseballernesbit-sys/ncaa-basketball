#!/bin/bash
# Quick test to verify email works
# Usage: ./test_email.sh your.email@gmail.com "your-app-password"

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: ./test_email.sh YOUR_EMAIL YOUR_APP_PASSWORD"
    echo ""
    echo "Example:"
    echo "  ./test_email.sh myemail@gmail.com abcd-efgh-ijkl-mnop"
    exit 1
fi

export NCAA_EMAIL_FROM="$1"
export NCAA_EMAIL_PASSWORD="$2"
export NCAA_EMAIL_TO="chaseballernesbit@gmail.com"

echo "Testing email with:"
echo "  From: $NCAA_EMAIL_FROM"
echo "  To: $NCAA_EMAIL_TO"
echo ""

cd /Users/mac/Documents/ncaa-basketball
python3 email_report.py
