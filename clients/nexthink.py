"""
clients/nexthink.py — Nexthink API client.

Credentials/config:
  NEXTHINK_URL          base URL
  NEXTHINK_TOKEN_URL    token endpoint
  NEXTHINK_AUTH_MODE    basic | client_credentials
  NEXTHINK_CLIENT_ID    client ID (client_credentials mode)
  NEXTHINK_CLIENT_SECRET
  NEXTHINK_USERNAME     username (basic mode)
  NEXTHINK_PASSWORD
"""

import base64
import os
import time
import requests

TIMEOUT = 30
_token_cache: dict = {}


def _base() -> str:
    return os.environ["NEXTHINK_URL"].rstrip("/")


def get_token() -> str:
    now = time.time()
    if _token_cache.get("token") and _token_cache.get("expires_at", 0) > now + 60:
        return _token_cache["token"]

    token_url = os.environ["NEXTHINK_TOKEN_URL"]
    auth_mode = os.environ.get("NEXTHINK_AUTH_MODE", "basic").lower()

    if auth_mode == "client_credentials":
        cred = base64.b64encode(
            f"{os.environ['NEXTHINK_CLIENT_ID']}:{os.environ['NEXTHINK_CLIENT_SECRET']}".encode()
        ).decode()
        r = requests.post(
            token_url,
            headers={"Authorization": f"Basic {cred}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials"},
            timeout=TIMEOUT,
        )
    else:  # basic
        cred = base64.b64encode(
            f"{os.environ['NEXTHINK_USERNAME']}:{os.environ['NEXTHINK_PASSWORD']}".encode()
        ).decode()
        r = requests.post(
            token_url,
            headers={"Authorization": f"Basic {cred}"},
            timeout=TIMEOUT,
        )

    r.raise_for_status()
    data = r.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 3599)
    return _token_cache["token"]


def post(endpoint: str, payload: dict) -> dict:
    """Generic authenticated POST to a Nexthink endpoint."""
    r = requests.post(
        f"{_base()}{endpoint}",
        headers={
            "Authorization": f"Bearer {get_token()}",
            "Accept": "*/*",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()
