"""
clients/smtp.py — SMTP email client.

Credentials/config:
  SMTP_HOST       default: smtp.gmail.com
  SMTP_PORT       default: 587
  SMTP_USER       sender email address
  SMTP_PASSWORD   sender password / app password
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email(to: str | list[str], subject: str, body_html: str) -> None:
    """Send an HTML email. to can be a single address or a list."""
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]

    recipients = [to] if isinstance(to, str) else to

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP(host, port, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.login(user, password)
        server.sendmail(user, recipients, msg.as_string())


def send_plain_email(to: str, subject: str, body: str) -> None:
    """Send a plain text email."""
    send_email(to, subject, f"<pre>{body}</pre>")
