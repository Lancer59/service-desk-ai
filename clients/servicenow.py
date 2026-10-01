"""
clients/servicenow.py — typed ServiceNow REST client.

All methods raise on non-2xx. Callers catch and return safe error dicts.
Credentials: SERVICENOW_DOMAIN, SERVICENOW_USER, SERVICENOW_PASSWORD
"""

import os
import requests
from requests.auth import HTTPBasicAuth

TIMEOUT = 30


def _auth() -> HTTPBasicAuth:
    return HTTPBasicAuth(
        os.environ["SERVICENOW_USER"],
        os.environ["SERVICENOW_PASSWORD"],
    )


def _base() -> str:
    return os.environ["SERVICENOW_DOMAIN"].rstrip("/")


def _get(path: str, params: dict = None) -> dict:
    r = requests.get(
        f"{_base()}{path}",
        auth=_auth(),
        params=params or {},
        headers={"Accept": "application/json"},
        timeout=TIMEOUT,
        verify=True,
    )
    r.raise_for_status()
    return r.json()


def _post(path: str, payload: dict) -> dict:
    r = requests.post(
        f"{_base()}{path}",
        auth=_auth(),
        json=payload,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=TIMEOUT,
        verify=True,
    )
    r.raise_for_status()
    return r.json()


def _put(path: str, payload: dict) -> dict:
    r = requests.put(
        f"{_base()}{path}",
        auth=_auth(),
        json=payload,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=TIMEOUT,
        verify=True,
    )
    r.raise_for_status()
    return r.json()


# ── User lookup ───────────────────────────────────────────────────────────────

def get_caller_sys_id(email: str) -> str:
    """Resolve a user email to a ServiceNow sys_id. Returns '' if not found."""
    data = _get(
        "/api/now/v1/table/sys_user",
        {"sysparm_query": f"email={email}", "sysparm_fields": "sys_id"},
    )
    results = data.get("result", [])
    return results[0]["sys_id"] if results else ""


# ── Incidents ─────────────────────────────────────────────────────────────────

def create_incident(payload: dict) -> dict:
    return _post("/api/now/v1/table/incident", payload)


def get_incident_by_number(number: str, fields: str = "number,state,priority,short_description,sys_id") -> dict:
    data = _get(
        "/api/now/v1/table/incident",
        {
            "sysparm_query": f"number={number}",
            "sysparm_display_value": "true",
            "sysparm_fields": fields,
        },
    )
    results = data.get("result", [])
    return results[0] if results else {}


def get_incidents_by_date(date_prefix: str) -> list:
    data = _get(
        "/api/now/v1/table/incident",
        {
            "sysparm_query": f"sys_created_onSTARTSWITH{date_prefix}",
            "sysparm_display_value": "true",
            "sysparm_fields": "number,priority,sys_created_on,comments,sla_due,state,short_description,made_sla",
        },
    )
    return data.get("result", [])


def update_incident(sys_id: str, payload: dict) -> dict:
    return _put(f"/api/now/table/incident/{sys_id}", payload)


def close_incident(sys_id: str, close_notes: str, close_state: str) -> dict:
    return _put(
        f"/api/now/v1/table/incident/{sys_id}",
        {"close_notes": close_notes, "state": close_state},
    )


# ── Requests / RITM / tasks ───────────────────────────────────────────────────

def get_request(number: str) -> list:
    data = _get(
        "/api/now/table/sc_request",
        {
            "sysparm_query": f"numberSTARTSWITH{number}",
            "sysparm_display_value": "true",
            "sysparm_fields": "number,opened_at,stage,due_date",
        },
    )
    return data.get("result", [])


def get_request_items(request_number: str) -> list:
    data = _get(
        "/api/now/table/sc_req_item",
        {
            "sysparm_query": f"requestSTARTSWITH{request_number}",
            "sysparm_display_value": "true",
            "sysparm_fields": "number,cat_item,state,comments",
        },
    )
    return data.get("result", [])


def get_catalog_tasks(request_number: str) -> list:
    data = _get(
        "/api/now/table/sc_task",
        {
            "sysparm_query": f"requestSTARTSWITH{request_number}",
            "sysparm_display_value": "true",
            "sysparm_fields": "number,sys_created_on,short_description,assignment_group,comments",
        },
    )
    return data.get("result", [])


def update_request_item(sys_id: str, payload: dict) -> dict:
    return _put(f"/api/now/table/sc_req_item/{sys_id}", payload)


# ── Catalog ───────────────────────────────────────────────────────────────────

def get_catalog_item(catalog_sys_id: str) -> dict:
    data = _get(f"/api/sn_sc/servicecatalog/items/{catalog_sys_id}")
    return data.get("result", {})


def order_catalog_item(catalog_sys_id: str, variables: dict) -> dict:
    return _post(
        f"/api/sn_sc/servicecatalog/items/{catalog_sys_id}/order_now",
        {"variables": variables},
    )


# ── Interactions ──────────────────────────────────────────────────────────────

def create_interaction(payload: dict) -> dict:
    return _post("/api/now/v1/table/interaction", payload)


def close_interaction(interaction_sys_id: str) -> dict:
    return _post(f"/api/now/interaction/{interaction_sys_id}/close", {})
