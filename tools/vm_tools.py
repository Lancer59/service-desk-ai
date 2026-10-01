"""
tools/vm_tools.py — VM and server lifecycle tools.

All mutation tools require user consent before execution.
"""

from langchain.tools import tool
from pydantic import BaseModel, Field

from clients import vm_api


class VMNameInput(BaseModel):
    vm_name: str = Field(description="Exact name of the VM or server")


class NoInput(BaseModel):
    """Empty schema for zero-argument tools."""
    pass


class CommissionInput(BaseModel):
    vm_name: str = Field(description="Name for the new VM/server")
    os: str = Field(description="Operating system, e.g. Windows Server 2022, Ubuntu 22.04")
    size: str = Field(description="VM size/SKU, e.g. Standard_D2s_v3")
    location: str = Field(description="Azure region or data center location")
    criticality: str = Field(description="Business criticality: low, medium, high, critical")
    justification: str = Field(description="Business justification for provisioning")
    user_email: str = Field(default="", description="Email of the requesting user")


class LookAlikeInput(BaseModel):
    source_vm_name: str = Field(description="Source VM whose configuration to replicate")
    new_vm_name: str = Field(description="Name for the new VM")
    justification: str = Field(description="Business justification")
    user_email: str = Field(default="", description="Email of the requesting user")


class DecommissionInput(BaseModel):
    vm_name: str = Field(description="Name of the VM/server to decommission")
    justification: str = Field(description="Business justification for decommissioning")
    user_email: str = Field(default="", description="Email of the requesting user")


@tool("get_vm_data", args_schema=NoInput)
def get_vm_data() -> dict:
    """
    List available virtual machines. Use for discovery or to present VM options
    before a look-alike or configuration request.
    """
    try:
        result = vm_api.list_vms()
        return {"success": True, "vms": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("vm_configuration_tool", args_schema=VMNameInput)
def vm_configuration_tool(vm_name: str) -> dict:
    """
    Retrieve the configuration of a specific VM. Use before commissioning a look-alike.
    Present the config to the user for review and get consent before proceeding.
    """
    try:
        config = vm_api.get_vm_config(vm_name)
        return {"success": True, "vm_name": vm_name, "configuration": config}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("start_vm", args_schema=VMNameInput)
def start_vm(vm_name: str) -> dict:
    """
    Start a stopped or inaccessible VM. Confirm the VM name with the user first.
    """
    try:
        result = vm_api.start_vm(vm_name)
        return {"success": True, "vm_name": vm_name, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("stop_vm", args_schema=VMNameInput)
def stop_vm(vm_name: str) -> dict:
    """
    Stop a running VM. Always confirm with the user before stopping — this is disruptive.
    """
    try:
        result = vm_api.stop_vm(vm_name)
        return {"success": True, "vm_name": vm_name, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("server_commission", args_schema=CommissionInput)
def server_commission(
    vm_name: str, os: str, size: str, location: str,
    criticality: str, justification: str, user_email: str = "",
) -> dict:
    """
    Commission a new VM/server. Requires: name, OS, size, location, criticality,
    justification, and explicit user confirmation. Never commission without all fields.
    """
    try:
        payload = {
            "name": vm_name, "os": os, "size": size,
            "location": location, "criticality": criticality,
            "justification": justification, "requested_by": user_email,
        }
        result = vm_api.commission_server(payload)
        return {"success": True, "vm_name": vm_name, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("Look_Alike_VM", args_schema=LookAlikeInput)
def look_alike_vm(
    source_vm_name: str, new_vm_name: str,
    justification: str, user_email: str = "",
) -> dict:
    """
    Commission a new VM by cloning the configuration of an existing one.
    First call vm_configuration_tool to retrieve and present the source config,
    get user consent, then call this tool.
    """
    try:
        source_config = vm_api.get_vm_config(source_vm_name)
        payload = {
            **source_config,
            "name": new_vm_name,
            "justification": justification,
            "requested_by": user_email,
            "source_vm": source_vm_name,
        }
        result = vm_api.commission_server(payload)
        return {"success": True, "new_vm_name": new_vm_name, "cloned_from": source_vm_name, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("server_decommission", args_schema=DecommissionInput)
def server_decommission(vm_name: str, justification: str, user_email: str = "") -> dict:
    """
    Decommission and delete a VM/server. This is irreversible.
    Require explicit written confirmation from the user before calling.
    """
    try:
        payload = {"name": vm_name, "justification": justification, "requested_by": user_email}
        result = vm_api.decommission_server(payload)
        return {"success": True, "vm_name": vm_name, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
