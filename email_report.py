#!/usr/bin/env python3
"""
NCAA Basketball - Email Report Sender
Sends the daily analysis via email
"""

import smtplib
import ssl
import os
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.environ.get("NCAA_EMAIL_FROM", "")
SENDER_PASSWORD = os.environ.get("NCAA_EMAIL_PASSWORD", "")
RECIPIENT_EMAIL = os.environ.get("NCAA_EMAIL_TO", "chaseballernesbit@gmail.com")

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"


def find_latest_analysis() -> Path:
    """Find the most recent analysis file"""
    analysis_files = sorted(DATA_DIR.glob("analysis_*.md"), reverse=True)
    if analysis_files:
        return analysis_files[0]
    return None


def send_email(subject: str, body: str):
    """Send email with the analysis"""

    if not SENDER_PASSWORD:
        print("⚠️ NCAA_EMAIL_PASSWORD not set - skipping email")
        print("Set environment variable to enable email delivery")
        return False

    if not SENDER_EMAIL:
        print("⚠️ NCAA_EMAIL_FROM not set - skipping email")
        return False

    try:
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = SENDER_EMAIL
        message["To"] = RECIPIENT_EMAIL

        # Plain text version
        text_part = MIMEText(body, "plain")
        message.attach(text_part)

        # Connect and send
        context = ssl.create_default_context()

        # Fix for macOS certificate issues
        import certifi
        context.load_verify_locations(certifi.where())

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, message.as_string())

        print(f"✓ Email sent to {RECIPIENT_EMAIL}")
        return True

    except Exception as e:
        print(f"⚠️ Error sending email: {e}")
        return False


def main():
    """Main entry point"""
    # Find latest analysis file
    analysis_file = find_latest_analysis()

    if not analysis_file:
        print(f"Error: No analysis files found in {DATA_DIR}")
        print("Run the analyzer first: python analyze_games.py")
        return 1

    print(f"Loading analysis from: {analysis_file}")

    with open(analysis_file) as f:
        analysis = f.read()

    # Send email
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"🏀 NCAA Basketball Picks - {today}"

    success = send_email(subject, analysis)

    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
