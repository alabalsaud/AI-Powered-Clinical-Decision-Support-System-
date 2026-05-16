"""
app/services/email_service.py — Gmail SMTP email sender for password reset codes.
"""
from __future__ import annotations

import smtplib
import random
import string
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Tuple

from app.core.config import settings

# In-memory store: email → (code, expires_at)
# Code expires after 10 minutes
_RESET_STORE: Dict[str, Tuple[str, float]] = {}
CODE_TTL = 600  # 10 minutes in seconds


def _generate_code(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def generate_and_store_code(email: str) -> str:
    """Generate a 6-digit reset code, store it, and return it."""
    code = _generate_code()
    _RESET_STORE[email.lower()] = (code, time.time() + CODE_TTL)
    return code


def verify_code(email: str, code: str) -> bool:
    """Return True if the code is valid and not expired."""
    entry = _RESET_STORE.get(email.lower())
    if not entry:
        return False
    stored_code, expires_at = entry
    if time.time() > expires_at:
        _RESET_STORE.pop(email.lower(), None)
        return False
    return stored_code == code.strip()


def consume_code(email: str) -> None:
    """Remove the code after successful password reset."""
    _RESET_STORE.pop(email.lower(), None)


def send_reset_email(to_email: str, code: str, full_name: str = "") -> None:
    """Send password reset code via Gmail SMTP."""
    if not settings.SMTP_EMAIL or not settings.SMTP_PASSWORD:
        raise RuntimeError(
            "SMTP not configured. Add SMTP_EMAIL and SMTP_PASSWORD to your .env file."
        )

    name = full_name or to_email.split("@")[0]
    subject = "AI-CDSS — Your Password Reset Code"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8"/>
      <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0f0a1e; margin: 0; padding: 0; }}
        .wrap {{ max-width: 520px; margin: 40px auto; background: #1a1035; border-radius: 16px;
                 border: 1px solid rgba(124,58,237,0.25); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg,#6d28d9,#7c3aed); padding: 32px 36px; text-align:center; }}
        .header h1 {{ color:#fff; font-size:22px; margin:0; letter-spacing:-0.5px; }}
        .header p {{ color:rgba(255,255,255,0.75); font-size:13px; margin:6px 0 0; }}
        .body {{ padding: 36px; }}
        .body p {{ color: #c4b5fd; font-size:14px; line-height:1.7; margin:0 0 16px; }}
        .code-box {{ background:#0f0a1e; border:2px solid #7c3aed; border-radius:12px;
                     text-align:center; padding:24px; margin:24px 0; }}
        .code {{ font-family: 'Courier New', monospace; font-size:40px; font-weight:800;
                 color:#a78bfa; letter-spacing:10px; }}
        .note {{ color:#6b7280; font-size:12px; margin-top:10px; }}
        .footer {{ padding:20px 36px; border-top:1px solid rgba(124,58,237,0.15);
                   text-align:center; color:#4b5563; font-size:11px; }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="header">
          <h1>🏥 AI · CDSS</h1>
          <p>Clinical Decision Support System</p>
        </div>
        <div class="body">
          <p>Hello, <strong style="color:#e9d5ff">{name}</strong></p>
          <p>We received a request to reset your password. Use the code below — it expires in <strong style="color:#a78bfa">10 minutes</strong>.</p>
          <div class="code-box">
            <div class="code">{code}</div>
            <div class="note">Do not share this code with anyone.</div>
          </div>
          <p>If you did not request a password reset, you can safely ignore this email. Your account remains secure.</p>
        </div>
        <div class="footer">
          AI-CDSS · Alfaisal University Capstone &nbsp;·&nbsp; This is an automated message, do not reply.
        </div>
      </div>
    </body>
    </html>
    """

    plain_body = (
        f"Hello {name},\n\n"
        f"Your AI-CDSS password reset code is: {code}\n\n"
        f"This code expires in 10 minutes.\n\n"
        f"If you did not request this, please ignore the email."
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"AI-CDSS <{settings.SMTP_EMAIL}>"
    msg["To"] = to_email

    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(settings.SMTP_EMAIL, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_EMAIL, to_email, msg.as_string())
