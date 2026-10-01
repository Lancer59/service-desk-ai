"""
tools/registry.py — maps tool names to tool objects.

The skill loader returns which tool names are needed for a request.
This registry resolves those names to actual LangChain tool objects.

To add a new domain:
  1. Create tools/<domain>_tools.py with @tool decorated functions.
  2. Import and add to ALL_TOOLS below.
"""

from langchain.tools import BaseTool

# ── Ticket tools ──────────────────────────────────────────────────────────────
from tools.ticket_tools import (
    close_ticket,
    create_ticket,
    get_ticket_status,
    update_ticket,
)

# ── Catalog tools ─────────────────────────────────────────────────────────────
from tools.catalog_tools import (
    find_catalog_sys_id,
    get_catalog_parameters,
    order_catalog,
)

# ── Knowledge tools ───────────────────────────────────────────────────────────
from tools.knowledge_tools import get_article_detail, search_knowledge_base

# ── VM / infrastructure tools ─────────────────────────────────────────────────
from tools.vm_tools import (
    get_vm_data,
    look_alike_vm,
    server_commission,
    server_decommission,
    start_vm,
    stop_vm,
    vm_configuration_tool,
)

# ── Nexthink endpoint tools ───────────────────────────────────────────────────
from tools.nexthink_tools import script_executor, script_finder

# ── Identity / group tools ────────────────────────────────────────────────────
from tools.identity_tools import (
    check_group_membership_tool,
    check_group_name_tool,
    list_group_members_tool,
    list_security_groups_tool,
    mfa_reset,
    resolve_user_tool,
    submit_request_for_approval_tool,
)

# ── Meeting / calendar tools ──────────────────────────────────────────────────
from tools.meeting_tools import calendar_tool, create_google_meet, create_zoom_meeting

# ── Notification tools ────────────────────────────────────────────────────────
from tools.notification_tools import (
    notify_user,
    send_email,
    send_major_incident_notification,
)

# ── Master registry ───────────────────────────────────────────────────────────

ALL_TOOLS: dict[str, BaseTool] = {
    # tickets
    "create_ticket": create_ticket,
    "get_ticket_status": get_ticket_status,
    "update_ticket": update_ticket,
    "close_ticket": close_ticket,
    # catalog
    "find_catalog_sys_id": find_catalog_sys_id,
    "get_catalog_parameters": get_catalog_parameters,
    "order_catalog": order_catalog,
    # knowledge
    "search_knowledge_base": search_knowledge_base,
    "get_article_detail": get_article_detail,
    # vm / infrastructure
    "get_vm_data": get_vm_data,
    "vm_configuration_tool": vm_configuration_tool,
    "start_vm": start_vm,
    "stop_vm": stop_vm,
    "server_commission": server_commission,
    "Look_Alike_VM": look_alike_vm,
    "server_decommission": server_decommission,
    # nexthink
    "script_finder": script_finder,
    "script_executor": script_executor,
    # identity
    "mfa_reset": mfa_reset,
    "check_group_name_tool": check_group_name_tool,
    "list_security_groups_tool": list_security_groups_tool,
    "resolve_user_tool": resolve_user_tool,
    "check_group_membership_tool": check_group_membership_tool,
    "list_group_members_tool": list_group_members_tool,
    "submit_request_for_approval_tool": submit_request_for_approval_tool,
    # meetings
    "calendar_tool": calendar_tool,
    "create_google_meet": create_google_meet,
    "create_zoom_meeting": create_zoom_meeting,
    # notifications
    "notify_user": notify_user,
    "send_email": send_email,
    "send_major_incident_notification": send_major_incident_notification,
}


def get_tools(tool_names: list[str]) -> list[BaseTool]:
    """Resolve a list of tool names to tool objects. Logs a warning for unknown names."""
    import structlog
    log = structlog.get_logger()
    resolved = []
    for name in tool_names:
        tool = ALL_TOOLS.get(name)
        if tool:
            resolved.append(tool)
        else:
            log.warning("registry.tool_not_found", tool_name=name)
    return resolved


def get_all_tools() -> list[BaseTool]:
    """Return every registered tool. Used by /models endpoint for inspection."""
    return list(ALL_TOOLS.values())
