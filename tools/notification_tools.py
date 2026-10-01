"""
tools/notification_tools.py — Notification and email tools.

Covers: node notify, email send, major incident notification.
"""

from langchain.tools import tool
from pydantic import BaseModel, Field


class NotifyUserInput(BaseModel):
    message: str = Field(description="Plain text message to send to the user")
    user_email: str = Field(description="Email address of the recipient")
    channel_id: str = Field(default="", description="Channel ID if sending to a specific chat channel")


class SendEmailInput(BaseModel):
    to: str = Field(description="Recipient email address")
    subject: str = Field(description="Email subject")
    body: str = Field(description="Email body (plain text; will be wrapped in basic HTML)")


class MajorIncidentInput(BaseModel):
    ticket_number: str = Field(description="Incident number, e.g. INC0012345")
    domain: str = Field(description="Affected domain/service, e.g. Network, Email, VPN")
    short_description: str = Field(description="One-line summary of the major incident")
    description: str = Field(description="Detailed description of impact and scope")
    priority: str = Field(default="high", description="Priority: critical, high, medium")
    status: str = Field(default="New", description="Current status")


@tool("notify_user", args_schema=NotifyUserInput)
def notify_user(message: str, user_email: str, channel_id: str = "") -> dict:
    """
    Send a notification message to a user via the configured notification service.
    Use for proactive updates, confirmations, or alerts.
    """
    try:
        from clients.notification import notify_user as _notify
        result = _notify(text=message, email=user_email, channel_id=channel_id)
        return {"success": True, "recipient": user_email, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("send_email", args_schema=SendEmailInput)
def send_email(to: str, subject: str, body: str) -> dict:
    """
    Send an email notification to a user. Use for formal communications,
    ticket confirmations, or follow-up information.
    """
    try:
        from clients.smtp import send_email as _send
        _send(to=to, subject=subject, body_html=f"<p>{body.replace(chr(10), '<br>')}</p>")
        return {"success": True, "to": to, "subject": subject}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("send_major_incident_notification", args_schema=MajorIncidentInput)
def send_major_incident_notification(
    ticket_number: str,
    domain: str,
    short_description: str,
    description: str,
    priority: str = "high",
    status: str = "New",
) -> dict:
    """
    Send a major incident notification to all stakeholders via the notification service.
    Use only for confirmed major incidents (P1/P2) that affect multiple users.
    """
    try:
        from clients.notification import send_adaptive_card

        card = {
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": [
                {"type": "TextBlock", "text": f"🚨 MAJOR INCIDENT: {ticket_number}",
                 "weight": "Bolder", "size": "Large", "color": "Attention"},
                {"type": "FactSet", "facts": [
                    {"title": "Domain", "value": domain},
                    {"title": "Priority", "value": priority.upper()},
                    {"title": "Status", "value": status},
                    {"title": "Summary", "value": short_description},
                ]},
                {"type": "TextBlock", "text": description, "wrap": True},
            ],
        }

        # TODO: send to configured major incident distribution list
        # send_adaptive_card(major_incident_recipients, card)

        return {
            "success": True,
            "ticket_number": ticket_number,
            "card_built": True,
            "note": "TODO: configure major incident recipient list in env/config and uncomment send call.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
