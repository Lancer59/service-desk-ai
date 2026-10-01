"""
tools/nexthink_tools.py — Nexthink endpoint remediation tools.

script_finder: maps user issue to an approved script name (allow-list only).
script_executor: executes the approved script on the user's device after consent.
"""

from langchain.tools import tool
from pydantic import BaseModel, Field

from clients import nexthink
from config import settings


class ScriptFinderInput(BaseModel):
    issue_description: str = Field(description="Description of the endpoint issue to remediate")


class ScriptExecutorInput(BaseModel):
    script_name: str = Field(description="Approved script name from script_finder")
    device_identifier: str = Field(
        description="Device hostname, serial number, or user email to identify the target device"
    )
    user_consent: bool = Field(
        description="Must be True — user must explicitly consent before execution"
    )


def _get_script_map() -> dict:
    return settings.get("nexthink", {}).get("script_map", {})


def _get_action_endpoint() -> str:
    return settings.get("nexthink", {}).get("action_endpoint", "/api/v1/remote-actions/execute")


@tool("script_finder", args_schema=ScriptFinderInput)
def script_finder(issue_description: str) -> dict:
    """
    Identify the approved Nexthink remediation script for an endpoint issue.
    Returns the script name and a description. Only scripts on the configured
    allow-list are returned — never arbitrary scripts.
    Use this before script_executor.
    """
    issue_lower = issue_description.lower()
    script_map = _get_script_map()

    matched_script = None
    matched_keyword = None
    for keyword, script_name in script_map.items():
        if keyword.replace("_", " ") in issue_lower or keyword in issue_lower:
            matched_script = script_name
            matched_keyword = keyword
            break

    if not matched_script:
        return {
            "success": False,
            "message": (
                "No approved remediation script found for this issue. "
                "Consider raising a support ticket instead."
            ),
        }

    return {
        "success": True,
        "script_name": matched_script,
        "matched_issue": matched_keyword,
        "note": (
            f"Found script '{matched_script}'. "
            "Get explicit user consent before calling script_executor."
        ),
    }


@tool("script_executor", args_schema=ScriptExecutorInput)
def script_executor(
    script_name: str,
    device_identifier: str,
    user_consent: bool,
) -> dict:
    """
    Execute an approved Nexthink remediation script on the user's device.
    Requires user_consent=True — never execute without explicit user agreement.
    Only accepts scripts returned by script_finder (allow-list enforced here too).
    """
    try:
        if not user_consent:
            return {
                "success": False,
                "error": "Execution blocked: user_consent must be True. Ask the user to confirm.",
            }

        # Enforce allow-list — never execute a script not in config
        allowed_scripts = set(_get_script_map().values())
        if script_name not in allowed_scripts:
            return {
                "success": False,
                "error": f"Script '{script_name}' is not on the approved allow-list. Execution blocked.",
            }

        endpoint = _get_action_endpoint()
        payload = {
            "script": script_name,
            "device": device_identifier,
        }
        result = nexthink.post(endpoint, payload)

        return {
            "success": True,
            "script_name": script_name,
            "device": device_identifier,
            "result": result,
            "note": "Script executed. Ask the user to check if the issue is resolved.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
