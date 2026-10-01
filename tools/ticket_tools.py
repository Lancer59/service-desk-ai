"""
tools/ticket_tools.py — ServiceNow incident tools.

Covers: create, status lookup (incident/request/RITM/task), update, close.
All mutations require the caller sys_id resolved from the user's email.
"""

import os
from langchain.tools import tool
from pydantic import BaseModel, Field

from clients import servicenow as snow


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateTicketInput(BaseModel):
    summary: str = Field(description="Short one-line description of the issue")
    description: str = Field(description="Detailed explanation of the problem")
    priority: str = Field(default="3", description="Priority: 1=Critical, 2=High, 3=Medium, 4=Low")
    user_email: str = Field(default="", description="Email of the affected user")
    assignment_group: str = Field(default="", description="Assignment group override (optional)")


class GetTicketStatusInput(BaseModel):
    ticket_number: str = Field(description="Ticket number e.g. INC0012345, REQ0001234, RITM0001234")


class UpdateTicketInput(BaseModel):
    ticket_number: str = Field(description="Ticket number to update")
    work_note: str = Field(default="", description="Work note to add")
    priority: str = Field(default="", description="New priority (1-4) if changing")


class CloseTicketInput(BaseModel):
    ticket_number: str = Field(description="Incident number to close, e.g. INC0012345")
    closing_note: str = Field(default="Issue resolved.", description="Resolution summary")


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool("create_ticket", args_schema=CreateTicketInput)
def create_ticket(
    summary: str,
    description: str,
    priority: str = "3",
    user_email: str = "",
    assignment_group: str = "",
) -> dict:
    """
    Create a new ServiceNow incident. Use when the user reports a problem and wants
    it formally logged. Always collect summary, description, and priority first.
    """
    try:
        from config import settings
        sn_cfg = settings.get("servicenow", {})
        default_group = assignment_group or sn_cfg.get("default_assignment_group", "Service Desk")

        caller_sys_id = ""
        if user_email:
            caller_sys_id = snow.get_caller_sys_id(user_email)

        payload = {
            "short_description": summary,
            "description": description,
            "priority": str(priority),
            "assignment_group": default_group,
        }
        if caller_sys_id:
            payload["caller_id"] = caller_sys_id

        result = snow.create_incident(payload)
        record = result.get("result", {})
        return {
            "success": True,
            "ticket_number": record.get("number", ""),
            "sys_id": record.get("sys_id", ""),
            "summary": summary,
            "priority": priority,
            "state": "New",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("get_ticket_status", args_schema=GetTicketStatusInput)
def get_ticket_status(ticket_number: str) -> dict:
    """
    Get current status of a ticket. Handles incidents (INC), requests (REQ),
    request items (RITM), and catalog tasks (TASK).
    """
    try:
        num = ticket_number.strip().upper()

        if num.startswith("INC"):
            row = snow.get_incident_by_number(
                num,
                "number,priority,sys_created_on,comments,sla_due,state,short_description,made_sla,assigned_to",
            )
            if not row:
                return {"success": False, "error": f"Ticket {num} not found."}
            return {
                "success": True,
                "ticket_number": row.get("number"),
                "type": "incident",
                "state": row.get("state"),
                "priority": row.get("priority"),
                "short_description": row.get("short_description"),
                "assigned_to": row.get("assigned_to"),
                "created_on": row.get("sys_created_on"),
                "sla_due": row.get("sla_due"),
                "made_sla": row.get("made_sla"),
                "comments": row.get("comments"),
            }

        elif num.startswith("REQ"):
            rows = snow.get_request(num)
            if not rows:
                return {"success": False, "error": f"Request {num} not found."}
            r = rows[0]
            ritm_rows = snow.get_request_items(num)
            task_rows = snow.get_catalog_tasks(num)
            return {
                "success": True,
                "ticket_number": r.get("number"),
                "type": "request",
                "stage": r.get("stage"),
                "opened_at": r.get("opened_at"),
                "due_date": r.get("due_date"),
                "items": [
                    {"number": i.get("number"), "item": i.get("cat_item"),
                     "state": i.get("state"), "comments": i.get("comments")}
                    for i in ritm_rows
                ],
                "tasks": [
                    {"number": t.get("number"), "description": t.get("short_description"),
                     "group": t.get("assignment_group"), "comments": t.get("comments")}
                    for t in task_rows
                ],
            }

        else:
            return {"success": False, "error": f"Unrecognised ticket prefix in '{num}'. Expected INC or REQ."}

    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("update_ticket", args_schema=UpdateTicketInput)
def update_ticket(ticket_number: str, work_note: str = "", priority: str = "") -> dict:
    """
    Update a ServiceNow incident: add a work note or change priority.
    Provide at least one of work_note or priority.
    """
    try:
        if not work_note and not priority:
            return {"success": False, "error": "Provide work_note or priority to update."}

        num = ticket_number.strip().upper()

        if num.startswith("INC"):
            row = snow.get_incident_by_number(num, "sys_id,number")
            if not row:
                return {"success": False, "error": f"Incident {num} not found."}
            sys_id = row["sys_id"]
            payload = {}
            if work_note:
                payload["work_notes"] = work_note
            if priority:
                payload["priority"] = str(priority)
            snow.update_incident(sys_id, payload)
            return {"success": True, "ticket_number": num, "updated": list(payload.keys())}

        else:
            # RITM / request item update
            items = snow.get_request_items(num)
            if not items:
                return {"success": False, "error": f"No request items found for {num}."}
            sys_id = items[0]["sys_id"]
            payload = {}
            if work_note:
                payload["work_notes"] = work_note
            if priority:
                payload["priority"] = str(priority)
            snow.update_request_item(sys_id, payload)
            return {"success": True, "ticket_number": num, "updated": list(payload.keys())}

    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("close_ticket", args_schema=CloseTicketInput)
def close_ticket(ticket_number: str, closing_note: str = "Issue resolved.") -> dict:
    """
    Close a ServiceNow incident after the user confirms their issue is resolved.
    Only call this when the user explicitly says the problem is fixed.
    """
    try:
        from config import settings
        close_state = os.environ.get(
            "SERVICENOW_CLOSE_STATE",
            settings.get("servicenow", {}).get("close_state", "6"),
        )
        num = ticket_number.strip().upper()
        row = snow.get_incident_by_number(num, "sys_id,number,state")
        if not row:
            return {"success": False, "error": f"Incident {num} not found."}

        snow.close_incident(row["sys_id"], closing_note, close_state)
        return {
            "success": True,
            "ticket_number": num,
            "state": "Resolved",
            "closing_note": closing_note,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
