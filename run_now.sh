#!/bin/bash
# NCAA Basketball - Run Full Analysis + Email
# Usage: ./run_now.sh

cd /Users/mac/Documents/ncaa-basketball

export ODDS_API_KEY="e87c7ea619e4235d4a7026db65625bd0"
export NCAA_EMAIL_FROM="chaseballernesbit@gmail.com"
export NCAA_EMAIL_PASSWORD="jgjb meus qtjc zkpv"
export NCAA_EMAIL_TO="chaseballernesbit@gmail.com"

python3 daily_run.py
