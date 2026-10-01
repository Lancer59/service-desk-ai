"""
tools/identity_tools.py — Microsoft Graph identity and group tools.

Covers: MFA reset, group lookup, user resolution, membership check,
group creation, member addition, list members.

All group mutations go through an approval flow — see notification_tools.py.
"""

import uuid
from langchain.tools import tool
from pydantic import BaseModel, Field

from clients import graph


class MFAResetInput(BaseModel):
    user_email: str = Field(description="Email of the user whose MFA needs resetting")


class CheckGroupInput(BaseModel):
    group_name: str = Field(description="Exact display name of the security group to check")


class ResolveUserInput(BaseModel):
    name_query: str = Field(description="Full or partial display name of the user to resolve")


class CheckMembershipInput(BaseModel):
    group_id: str = Field(description="Object ID of the security group")
    user_object_ids: list[str] = Field(description="List of user object IDs to check")


class ListMembersInput(BaseModel):
    group_id: str = Field(description="Object ID of the security group")


class CreateGroupInput(BaseModel):
    group_name: str = Field(description="Display name for the new security group")
    description: str = Field(default="", description="Optional description")


class AddMemberInput(BaseModel):
    group_id: str = Field(description="Object ID of the group")
    user_object_id: str = Field(description="Object ID of the user to add")


class NoInput(BaseModel):
    """Empty schema for zero-argument tools."""
    pass


class SubmitApprovalInput(BaseModel):
    request_type: str = Field(description="Type of request: create_group or add_members")
    group_name: str = Field(description="Display name of the group")
    group_id: str = Field(description="Object ID of the group (empty string if creating new)")
    member_ids: list[str] = Field(description="List of user object IDs to add")
    user_email: str = Field(description="Email of the requesting user")
    conversation_id: str = Field(description="Current conversation ID for callback")
    approver_emails: list[str] = Field(description="Email addresses of approvers who will receive the card")


@tool("mfa_reset", args_schema=MFAResetInput)
def mfa_reset(user_email: str) -> dict:
    """
    Reset a user's Microsoft Authenticator MFA registration.
    HIGH IMPACT: verify the user's identity before calling this.
    Deletes all Microsoft Authenticator methods for the user.
    """
    try:
        methods = graph.get_mfa_methods(user_email)
        if not methods:
            return {
                "success": True,
                "message": f"No Microsoft Authenticator methods found for {user_email}. Nothing to reset.",
            }

        deleted = []
        for method in methods:
            graph.delete_mfa_method(user_email, method["id"])
            deleted.append(method["id"])

        return {
            "success": True,
            "user_email": user_email,
            "methods_deleted": len(deleted),
            "message": f"MFA reset complete for {user_email}. User must re-register their authenticator.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("check_group_name_tool", args_schema=CheckGroupInput)
def check_group_name_tool(group_name: str) -> dict:
    """
    Check whether an Entra ID security group with the given name exists.
    Returns the group ID if found.
    """
    try:
        groups = graph.check_group_exists(group_name)
        if groups:
            return {
                "success": True,
                "exists": True,
                "group_id": groups[0]["id"],
                "display_name": groups[0]["displayName"],
            }
        return {"success": True, "exists": False, "message": f"No group named '{group_name}' found."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("list_security_groups_tool", args_schema=NoInput)
def list_security_groups_tool() -> dict:
    """
    Retrieve a list of all Entra ID security groups.
    Use to help the user find the correct group name.
    """
    try:
        groups = graph.list_security_groups()
        return {"success": True, "groups": groups, "count": len(groups)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("resolve_user_tool", args_schema=ResolveUserInput)
def resolve_user_tool(name_query: str) -> dict:
    """
    Resolve a name or partial name to Entra ID users.
    Returns object ID, display name, and UPN for each match.
    Always use exact object IDs for subsequent Graph operations.
    """
    try:
        users = graph.resolve_users(name_query)
        if not users:
            return {"success": False, "error": f"No users found matching '{name_query}'."}
        return {
            "success": True,
            "users": [
                {"id": u["id"], "display_name": u.get("displayName", ""), "upn": u.get("userPrincipalName", "")}
                for u in users
            ],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("check_group_membership_tool", args_schema=CheckMembershipInput)
def check_group_membership_tool(group_id: str, user_object_ids: list[str]) -> dict:
    """
    Check if specified users are already members of a security group.
    Returns which users are already members (to avoid duplicate adds).
    """
    try:
        members = graph.get_group_members(group_id)
        existing_ids = {m["id"] for m in members}
        return {
            "success": True,
            "already_members": [uid for uid in user_object_ids if uid in existing_ids],
            "not_members": [uid for uid in user_object_ids if uid not in existing_ids],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("list_group_members_tool", args_schema=ListMembersInput)
def list_group_members_tool(group_id: str) -> dict:
    """List current members of an Entra ID security group."""
    try:
        members = graph.get_group_members(group_id)
        return {
            "success": True,
            "group_id": group_id,
            "members": [
                {"id": m["id"], "display_name": m.get("displayName", ""), "upn": m.get("userPrincipalName", "")}
                for m in members
            ],
            "count": len(members),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("submit_request_for_approval_tool", args_schema=SubmitApprovalInput)
def submit_request_for_approval_tool(
    request_type: str,
    group_name: str,
    group_id: str,
    member_ids: list[str],
    user_email: str,
    conversation_id: str,
    approver_emails: list[str],
) -> dict:
    """
    Save a group create/member-add request and send it for approval via Teams card.
    Provisioning only happens after the approver clicks Approve.
    Returns a document_id to track the approval status.
    """
    try:
        from clients.mongodb import save_approval_request
        from clients.notification import build_approval_card, send_adaptive_card

        document_id = str(uuid.uuid4())
        request_data = {
            "request_type": request_type,
            "group_name": group_name,
            "group_id": group_id,
            "member_ids": member_ids,
            "convid": conversation_id,
            "email": user_email,
        }
        save_approval_request(document_id, request_data)

        details = (
            f"Type: {request_type}\n"
            f"Group: {group_name}\n"
            f"Members to add: {len(member_ids)}\n"
            f"Requested by: {user_email}"
        )
        card = build_approval_card(document_id, f"Approval Request: {request_type}", details)
        send_adaptive_card(approver_emails, card)

        return {
            "success": True,
            "document_id": document_id,
            "message": "Request submitted for approval. The approver will receive a Teams notification.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
