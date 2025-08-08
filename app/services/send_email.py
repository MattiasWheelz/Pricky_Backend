import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
from pathlib import Path

# Load env vars
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
TO_EMAIL = os.getenv("TO_EMAIL", "pricky0portfolio@gmail.com")

def send_email(subject: str, body: str) -> bool:
    if not EMAIL_USER or not EMAIL_PASS:
        print("❌ Missing email credentials in environment variables.")
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = TO_EMAIL

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, TO_EMAIL, msg.as_string())
        return True
    except Exception as e:
        print("❌ Email error:", e)
        return False
