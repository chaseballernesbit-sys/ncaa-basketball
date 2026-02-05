#!/usr/bin/env python3
"""
Email sender for NCAA Basketball daily analysis
Uses Gmail SMTP with app password
"""

import smtplib
import ssl
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

def send_analysis_email(analysis_file: str = None):
    """Send the daily analysis via email"""

    # Get email configuration from environment
    email_to = os.environ.get('NCAA_EMAIL_TO')
    email_from = os.environ.get('NCAA_EMAIL_FROM')
    email_password = os.environ.get('NCAA_EMAIL_PASSWORD')

    if not all([email_to, email_from, email_password]):
        print("ERROR: Email not configured. Set NCAA_EMAIL_TO, NCAA_EMAIL_FROM, NCAA_EMAIL_PASSWORD")
        return False

    # Find the analysis file
    if analysis_file is None:
        data_dir = Path(__file__).parent / "data"
        today = datetime.now().strftime('%Y%m%d')
        analysis_file = data_dir / f"analysis_{today}.md"
    else:
        analysis_file = Path(analysis_file)

    if not analysis_file.exists():
        print(f"ERROR: Analysis file not found: {analysis_file}")
        return False

    # Read the analysis
    with open(analysis_file, 'r') as f:
        analysis_content = f.read()

    # Extract top plays for subject line
    top_plays_count = analysis_content.count('⭐⭐⭐⭐⭐')

    # Create email
    today_str = datetime.now().strftime('%B %d, %Y')
    subject = f"🏀 NCAA Basketball Picks - {today_str} ({top_plays_count} 5-star plays)"

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = email_from
    msg['To'] = email_to

    # Plain text version
    text_part = MIMEText(analysis_content, 'plain')
    msg.attach(text_part)

    # Send email via Gmail SMTP
    try:
        # Create SSL context - handle macOS certificate issues
        context = ssl.create_default_context()

        # Try with default certificates first, fall back to unverified if needed
        try:
            import certifi
            context.load_verify_locations(certifi.where())
        except ImportError:
            pass  # certifi not installed, use default

        with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as server:
            server.login(email_from, email_password)
            server.sendmail(email_from, email_to, msg.as_string())

        print(f"✓ Email sent to {email_to}")
        print(f"  Subject: {subject}")
        return True

    except smtplib.SMTPAuthenticationError:
        print("ERROR: Gmail authentication failed. Check app password.")
        return False
    except Exception as e:
        print(f"ERROR: Failed to send email: {e}")
        return False


if __name__ == "__main__":
    # Optional: pass analysis file as argument
    analysis_file = sys.argv[1] if len(sys.argv) > 1 else None
    success = send_analysis_email(analysis_file)
    sys.exit(0 if success else 1)
