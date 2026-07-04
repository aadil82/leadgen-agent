"""
Email Notifier — Send pipeline success/failure alerts via SMTP.

Sends email notifications when the daily pipeline completes (success or failure)
to the configured approval email address.

Usage:
    python -m pipeline.email_notifier --status success --message "20 leads qualified"
    python -m pipeline.email_notifier --status failure --message "OpenAI API error"
"""

import argparse
import json
import os
import smtplib
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

import yaml


# ── Config ─────────────────────────────────────────────────────


def _load_settings() -> Dict[str, Any]:
    """Load settings.yaml."""
    settings_path = os.path.join("config", "settings.yaml")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r") as fh:
                return yaml.safe_load(fh) or {}
        except Exception:
            pass
    return {}


def _get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ── Email Templates ────────────────────────────────────────────

SUCCESS_TEMPLATE = """
LinkedIn SDR Agent — Pipeline Completed ✅

Date: {date}
Duration: {duration}
Status: SUCCESS

Results:
  Total leads processed: {total_leads}
  Qualified leads:       {qualified}
  Rejected leads:        {rejected}
  Hot leads (85+):       {hot}
  Warm leads (75-84):    {warm}

Reports generated:
  • Excel:   {excel}
  • PDF:     {pdf}
  • Summary: {summary}
  • JSON:    {json}

Top technologies: {top_techs}
Top industries:   {top_industries}

View the dashboard: streamlit run app.py
Approval digest: {digest}

---
LinkedIn SDR Agent v2.0
"""

FAILURE_TEMPLATE = """
LinkedIn SDR Agent — Pipeline Failed ❌

Date: {date}
Duration: {duration}
Status: FAILURE

Error:
{error_message}

Traceback:
{traceback}

Please check the logs at data/logs/ for more details.

---
LinkedIn SDR Agent v2.0
"""


# ── Email Sender ───────────────────────────────────────────────


class EmailNotifier:
    """Send pipeline notifications via SMTP."""

    def __init__(
        self,
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        use_tls: bool = True,
        sender_email: str = "",
        sender_name: str = "LinkedIn SDR Agent",
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.use_tls = use_tls
        self.sender_email = sender_email or smtp_user
        self.sender_name = sender_name

    @classmethod
    def from_settings(cls) -> "EmailNotifier":
        """Create notifier from settings.yaml and environment variables."""
        settings = _load_settings()
        email_config = settings.get("email_notifications", {})
        sender = settings.get("sender", {})

        return cls(
            smtp_host=_get_env(
                "SMTP_HOST",
                email_config.get("smtp_host", ""),
            ),
            smtp_port=int(_get_env(
                "SMTP_PORT",
                str(email_config.get("smtp_port", 587)),
            )),
            smtp_user=_get_env(
                "SMTP_USER",
                email_config.get("smtp_user", ""),
            ),
            smtp_password=_get_env(
                "SMTP_PASSWORD",
                email_config.get("smtp_password", ""),
            ),
            use_tls=email_config.get("use_tls", True),
            sender_email=_get_env(
                "SMTP_FROM",
                sender.get("email", ""),
            ),
            sender_name=sender.get("name", "LinkedIn SDR Agent"),
        )

    def is_configured(self) -> bool:
        """Check if SMTP is properly configured."""
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    def send(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ) -> bool:
        """Send an email. Returns True on success."""
        if not self.is_configured():
            print("  [WARN] Email notifications not configured (missing SMTP settings)")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = f"{self.sender_name} <{self.sender_email}>"
            msg["To"] = to_email
            msg["Subject"] = subject

            # Plain text version
            text_part = MIMEText(body_text, "plain", "utf-8")
            msg.attach(text_part)

            # HTML version (optional, falls back to plain text)
            if body_html:
                html_part = MIMEText(body_html, "html", "utf-8")
                msg.attach(html_part)

            # Connect and send
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            print(f"  ✅ Email notification sent to {to_email}")
            return True

        except smtplib.SMTPAuthenticationError:
            print("  [ERROR] SMTP authentication failed. Check SMTP_USER and SMTP_PASSWORD.")
            return False
        except smtplib.SMTPConnectError:
            print(f"  [ERROR] Cannot connect to SMTP server {self.smtp_host}:{self.smtp_port}")
            return False
        except Exception as e:
            print(f"  [ERROR] Failed to send email: {e}")
            traceback.print_exc()
            return False


# ── Pipeline Notification Helpers ──────────────────────────────


def notify_success(
    summary: Dict[str, Any],
    to_email: Optional[str] = None,
) -> bool:
    """Send a success notification after pipeline completion."""
    settings = _load_settings()
    notifier = EmailNotifier.from_settings()
    if not notifier.is_configured():
        return False

    if to_email is None:
        to_email = _get_env(
            "APPROVAL_EMAIL",
            settings.get("sender", {}).get("approval_email", ""),
        )
    if not to_email:
        print("  [WARN] No approval email configured. Skipping notification.")
        return False

    date = summary.get("date", datetime.now().isoformat())
    duration = summary.get("duration_seconds", 0)
    duration_str = f"{duration:.1f}s" if duration < 60 else f"{duration/60:.1f}min"

    reports = summary.get("reports", {})

    # Build top technologies/industries strings
    top_techs = "None"
    top_industries = "None"

    # Try to read from dashboard JSON for richer data
    json_path = reports.get("dashboard_json", "")
    if json_path and os.path.exists(json_path):
        try:
            with open(json_path, "r") as fh:
                data = json.load(fh)
            techs = data.get("summary", {}).get("top_technologies", [])
            if techs:
                top_techs = ", ".join(f"{t['name']} ({t['count']})" for t in techs[:5])
            inds = data.get("summary", {}).get("top_industries", [])
            if inds:
                top_industries = ", ".join(f"{i['name']} ({i['count']})" for i in inds[:5])
        except Exception:
            pass

    body = SUCCESS_TEMPLATE.format(
        date=date,
        duration=duration_str,
        total_leads=summary.get("total_leads", 0),
        qualified=summary.get("qualified", 0),
        rejected=summary.get("rejected", 0),
        hot=summary.get("hot", 0),
        warm=summary.get("warm", 0),
        excel=reports.get("excel", "N/A"),
        pdf=reports.get("pdf", "N/A"),
        summary=reports.get("summary", "N/A"),
        json=reports.get("dashboard_json", "N/A"),
        top_techs=top_techs,
        top_industries=top_industries,
        digest=reports.get("digest", "N/A"),
    )

    subject = (
        f"✅ Pipeline Complete — {summary.get('qualified', 0)} qualified leads "
        f"({summary.get('date', 'today')})"
    )

    return notifier.send(to_email, subject, body)


def notify_failure(
    error_message: str,
    error_traceback: str = "",
    to_email: Optional[str] = None,
    duration: float = 0,
) -> bool:
    """Send a failure notification when the pipeline crashes."""
    settings = _load_settings()
    notifier = EmailNotifier.from_settings()
    if not notifier.is_configured():
        return False

    if to_email is None:
        to_email = _get_env(
            "APPROVAL_EMAIL",
            settings.get("sender", {}).get("approval_email", ""),
        )
    if not to_email:
        print("  [WARN] No approval email configured. Skipping notification.")
        return False

    duration_str = f"{duration:.1f}s" if duration < 60 else f"{duration/60:.1f}min"

    body = FAILURE_TEMPLATE.format(
        date=datetime.now().isoformat(),
        duration=duration_str,
        error_message=error_message,
        traceback=error_traceback or "No traceback available",
    )

    subject = f"❌ Pipeline Failed — {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    return notifier.send(to_email, subject, body)


# ── CLI ────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Send Pipeline Email Notifications")
    parser.add_argument(
        "--status", "-s", required=True, choices=["success", "failure"],
        help="Pipeline status",
    )
    parser.add_argument("--message", "-m", default="", help="Notification message")
    parser.add_argument("--to", help="Override recipient email")
    parser.add_argument("--summary-json", help="Path to pipeline summary JSON for success notifications")
    args = parser.parse_args()

    if args.status == "success":
        summary = {}
        if args.summary_json and os.path.exists(args.summary_json):
            with open(args.summary_json, "r") as fh:
                summary = json.load(fh)
        else:
            summary = {
                "date": datetime.now().isoformat(),
                "duration_seconds": 0,
                "total_leads": 0,
                "qualified": 0,
                "rejected": 0,
                "reports": {},
            }
        if args.message:
            summary["message"] = args.message
        notify_success(summary, to_email=args.to)
    else:
        notify_failure(
            error_message=args.message or "Unknown error",
            to_email=args.to,
        )


if __name__ == "__main__":
    main()
