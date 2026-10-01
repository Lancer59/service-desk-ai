"""
clients/vm_api.py — Internal Azure/VM orchestration API client.

Credentials/config:
  VM_API_URL   base URL of the internal VM API (e.g. https://internal-api/api/v2.0/azure)
"""

import os
import requests

TIMEOUT = 60  # VM ops can be slow


def _base() -> str:
    return os.environ["VM_API_URL"].rstrip("/")


def _get(path: str) -> dict:
    r = requests.get(f"{_base()}{path}", timeout=TIMEOUT, verify=True)
    r.raise_for_status()
    return r.json()


def _post(path: str, payload: dict = None) -> dict:
    r = requests.post(f"{_base()}{path}", json=payload or {}, timeout=TIMEOUT, verify=True)
    r.raise_for_status()
    return r.json()


def list_vms() -> dict:
    return _get("/vmList")


def get_vm_config(vm_name: str) -> dict:
    return _get(f"/vmConfig/{vm_name}")


def start_vm(vm_name: str) -> dict:
    return _post(f"/startVM/{vm_name}")


def stop_vm(vm_name: str) -> dict:
    return _post(f"/stopVM/{vm_name}")


def commission_server(payload: dict) -> dict:
    """Commission/create a new VM or server."""
    # TODO: confirm exact endpoint with platform team
    return _post("/commissionVM", payload)


def decommission_server(payload: dict) -> dict:
    """Decommission/delete a VM or server."""
    # TODO: confirm exact endpoint with platform team
    return _post("/decommissionVM", payload)
