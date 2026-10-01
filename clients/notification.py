"""
clients/notification.py — Internal notification service client.

Credentials/config:
  NODE_SERVER_URL         base URL of the node/notification server
  PUBLIC_SERVICE_DESK_URL public URL of this service (used in approval card links)
"""

import os
import requests

TIMEOUT = 15


def _node_base() -> str:
    return os.environ["NODE_SERVER_URL"].rstrip("/")


def notify_user(text: str, email: str, channel_id: str, bot_id: str = "B0004") -> dict:
    """Send a plain text notification to a user via the node notification service."""
    r = requests.post(
        f"{_node_base()}/api/v2.0/notification/api/servicedesk/notify",
        json={"text": text, "botId": bot_id, "email": email, "channelId": channel_id},
        headers={"Content-Type": "application/json"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def send_adaptive_card(recipient_emails: list[str], card_payload: dict) -> dict:
    """Send an Adaptive Card (e.g. approval request) to one or more recipients."""
    r = requests.post(
        f"{_node_base()}/api/v2.0/notification/api/notify",
        json={"recipients": recipient_emails, "card": card_payload},
        headers={"Content-Type": "application/json"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def build_approval_card(
    document_id: str,
    title: str,
    details: str,
) -> dict:
    """Build a minimal Teams Adaptive Card with Approve/Reject buttons."""
    public_url = os.environ.get("PUBLIC_SERVICE_DESK_URL", "http://localhost:8000").rstrip("/")
    approve_url = f"{public_url}/approve?document_id={document_id}&action=approve"
    reject_url = f"{public_url}/approve?document_id={document_id}&action=reject"

    return {
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium"},
            {"type": "TextBlock", "text": details, "wrap": True},
        ],
        "actions": [
            {"type": "Action.OpenUrl", "title": "✅ Approve", "url": approve_url},
            {"type": "Action.OpenUrl", "title": "❌ Reject", "url": reject_url},
        ],
    }
