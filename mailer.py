"""Send case-summary emails to clients via Gmail SMTP (App Password)."""
import smtplib
import ssl
from email.message import EmailMessage

import config


def is_configured():
    return bool(config.GMAIL_ADDRESS and config.GMAIL_APP_PASSWORD)


def send_email(to_addr, subject, body):
    """Send a plain-text email. Returns (ok: bool, error: str)."""
    if not is_configured():
        return False, "Email not configured (set GMAIL_ADDRESS and GMAIL_APP_PASSWORD)."
    if not to_addr:
        return False, "No recipient email on file for this client."
    try:
        msg = EmailMessage()
        msg["From"] = config.GMAIL_ADDRESS
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(body)
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=20) as s:
            s.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
            s.send_message(msg)
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)
