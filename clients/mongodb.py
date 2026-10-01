"""
clients/mongodb.py — MongoDB client for approval/request persistence.

Credentials/config:
  MONGO_URL        MongoDB connection string
  MONGO_DB_NAME    database name (default: service_desk)
"""

import os
from datetime import datetime, timezone

_client = None
_db = None


def _get_db():
    global _client, _db
    if _db is not None:
        return _db
    try:
        from pymongo import MongoClient
    except ImportError:
        # TODO: pip install pymongo
        raise RuntimeError("pymongo not installed. Run: pip install pymongo")

    _client = MongoClient(os.environ["MONGO_URL"])
    _db = _client[os.environ.get("MONGO_DB_NAME", "service_desk")]
    return _db


def save_approval_request(document_id: str, request_data: dict) -> str:
    """Insert a new pending approval document. Returns the document_id."""
    db = _get_db()
    db["approvals"].insert_one({
        "_id": document_id,
        "status": "Pending",
        "request_data": request_data,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return document_id


def get_approval_request(document_id: str) -> dict | None:
    db = _get_db()
    return db["approvals"].find_one({"_id": document_id})


def claim_and_update_approval(document_id: str, new_status: str) -> bool:
    """
    Atomic compare-and-set: only transitions from Pending.
    Returns True if the claim succeeded (prevents double-click provisioning).
    """
    db = _get_db()
    result = db["approvals"].find_one_and_update(
        {"_id": document_id, "status": "Pending"},
        {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return result is not None
