"""
clients/graph.py — Microsoft Graph API client with token caching.

Credentials: GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET
Optional: GRAPH_BASE_URL (defaults to https://graph.microsoft.com/v1.0)
"""

import os
import time
import requests

TIMEOUT = 30
_token_cache: dict = {}  # {"token": str, "expires_at": float}


def _base() -> str:
    return os.environ.get("GRAPH_BASE_URL", "https://graph.microsoft.com/v1.0").rstrip("/")


def get_token() -> str:
    """Acquire or return cached client-credentials token."""
    now = time.time()
    if _token_cache.get("token") and _token_cache.get("expires_at", 0) > now + 60:
        return _token_cache["token"]

    tenant = os.environ["GRAPH_TENANT_ID"]
    r = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["GRAPH_CLIENT_ID"],
            "client_secret": os.environ["GRAPH_CLIENT_SECRET"],
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 3599)
    return _token_cache["token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"}


def _get(path: str, params: dict = None) -> dict:
    r = requests.get(f"{_base()}{path}", headers=_headers(), params=params or {}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _post(path: str, payload: dict) -> dict:
    r = requests.post(f"{_base()}{path}", headers=_headers(), json=payload, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _delete(path: str) -> None:
    r = requests.delete(f"{_base()}{path}", headers=_headers(), timeout=TIMEOUT)
    r.raise_for_status()


# ── Users ─────────────────────────────────────────────────────────────────────

def resolve_users(name_query: str) -> list:
    data = _get("/users", {"$filter": f"startswith(displayName,'{name_query}')",
                           "$select": "id,displayName,userPrincipalName"})
    return data.get("value", [])


def get_mfa_methods(user_email: str) -> list:
    data = _get(f"/users/{user_email}/authentication/microsoftAuthenticatorMethods")
    return data.get("value", [])


def delete_mfa_method(user_email: str, method_id: str) -> None:
    _delete(f"/users/{user_email}/authentication/microsoftAuthenticatorMethods/{method_id}")


# ── Groups ────────────────────────────────────────────────────────────────────

def check_group_exists(display_name: str) -> list:
    data = _get("/groups", {
        "$filter": f"securityEnabled eq true and displayName eq '{display_name}'",
        "$select": "id,displayName",
    })
    return data.get("value", [])


def list_security_groups() -> list:
    data = _get("/groups", {"$filter": "securityEnabled eq true", "$select": "id,displayName"})
    return data.get("value", [])


def get_group_members(group_id: str) -> list:
    data = _get(f"/groups/{group_id}/members", {"$select": "id,displayName,userPrincipalName"})
    return data.get("value", [])


def create_security_group(display_name: str, mail_nickname: str, description: str = "") -> dict:
    return _post("/groups", {
        "displayName": display_name,
        "mailEnabled": False,
        "mailNickname": mail_nickname,
        "securityEnabled": True,
        "description": description or "Created via Service Desk Bot",
    })


def add_group_member(group_id: str, user_object_id: str) -> None:
    _post(f"/groups/{group_id}/members/$ref", {
        "@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{user_object_id}"
    })


# ── Calendar / Teams meetings ─────────────────────────────────────────────────

def create_teams_meeting(organizer_user: str, payload: dict) -> dict:
    return _post(f"/users/{organizer_user}/calendar/events", payload)


# ── Intune / device ───────────────────────────────────────────────────────────

def sync_managed_device(managed_device_id: str) -> None:
    r = requests.post(
        f"https://graph.microsoft.com/v1.0/deviceManagement/managedDevices/{managed_device_id}/syncDevice",
        headers=_headers(),
        timeout=TIMEOUT,
    )
    r.raise_for_status()
