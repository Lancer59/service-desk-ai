"""
clients/zoom.py — Zoom Meetings API client.

Credentials/config:
  ZOOM_ACCOUNT_ID
  ZOOM_CLIENT_ID
  ZOOM_CLIENT_SECRET
"""

import base64
import os
import requests

TIMEOUT = 15


def _get_token() -> str:
    account_id = os.environ["ZOOM_ACCOUNT_ID"]
    cred = base64.b64encode(
        f"{os.environ['ZOOM_CLIENT_ID']}:{os.environ['ZOOM_CLIENT_SECRET']}".encode()
    ).decode()
    r = requests.post(
        f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={account_id}",
        headers={"Authorization": f"Basic {cred}"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def create_meeting(topic: str, start_time: str, duration_minutes: int = 60) -> dict:
    token = _get_token()
    r = requests.post(
        "https://api.zoom.us/v2/users/me/meetings",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "topic": topic,
            "type": 2,
            "start_time": start_time,
            "duration": duration_minutes,
            "timezone": "UTC",
            "settings": {"join_before_host": True, "approval_type": 0},
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()
