#!/bin/bash
# NCAA Basketball - Run Full Analysis + Email
# Usage: ./run_now.sh

cd /Users/mac/Documents/ncaa-basketball

export ODDS_API_KEY="baf9e5c0d5bb1ad4fbdcabe9766fff22"
export NCAA_EMAIL_FROM="chaseballernesbit@gmail.com"
export NCAA_EMAIL_PASSWORD="jgjb meus qtjc zkpv"
export NCAA_EMAIL_TO="chaseballernesbit@gmail.com"

python3 daily_run.py
