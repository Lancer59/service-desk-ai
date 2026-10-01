"""
tools/catalog_tools.py — ServiceNow Service Catalog tools.

Workflow: find_catalog_sys_id → get_catalog_parameters → (user confirms) → order_catalog
"""

from langchain.tools import tool
from pydantic import BaseModel, Field

from clients import servicenow as snow


class FindCatalogInput(BaseModel):
    search_term: str = Field(description="Name or description of the catalog item to find")


class GetCatalogParamsInput(BaseModel):
    catalog_sys_id: str = Field(description="sys_id of the catalog item from find_catalog_sys_id")


class OrderCatalogInput(BaseModel):
    catalog_sys_id: str = Field(description="sys_id of the catalog item to order")
    variables: dict = Field(description="Dict of variable_name: value for all required fields")
    user_email: str = Field(default="", description="Email of the requesting user")


def _extract_fields(item: dict) -> list[dict]:
    """Flatten catalog item variables into a simple list of field descriptors."""
    fields = []
    for var in item.get("variables", []):
        # Skip display-only / container fields
        if var.get("type") in ("container_start", "container_end", "label", "break"):
            continue
        fields.append({
            "name": var.get("name", ""),
            "label": var.get("label", var.get("name", "")),
            "mandatory": var.get("mandatory", False),
            "type": var.get("type", "string"),
            "help_text": var.get("help_text", ""),
        })
    return fields


@tool("find_catalog_sys_id", args_schema=FindCatalogInput)
def find_catalog_sys_id(search_term: str) -> dict:
    """
    Find a ServiceNow catalog item by name or description.
    Returns catalog sys_id, name, and a short description.
    Always confirm with the user before proceeding to order.
    """
    try:
        # Search catalog via table API — filter by name containing the term
        from clients.servicenow import _get
        data = _get(
            "/api/now/table/sc_cat_item",
            {
                "sysparm_query": f"nameLIKE{search_term}^active=true",
                "sysparm_fields": "sys_id,name,short_description",
                "sysparm_limit": "5",
            },
        )
        results = data.get("result", [])
        if not results:
            return {"success": False, "error": f"No catalog items found matching '{search_term}'."}

        return {
            "success": True,
            "items": [
                {
                    "sys_id": r["sys_id"],
                    "name": r["name"],
                    "short_description": r.get("short_description", ""),
                }
                for r in results
            ],
            "note": "Ask the user to confirm which item they want before calling get_catalog_parameters.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("get_catalog_parameters", args_schema=GetCatalogParamsInput)
def get_catalog_parameters(catalog_sys_id: str) -> dict:
    """
    Retrieve all variables/fields required to order a catalog item.
    Returns field names, labels, mandatory flags, and types.
    Collect all mandatory fields from the user before calling order_catalog.
    """
    try:
        item = snow.get_catalog_item(catalog_sys_id)
        if not item:
            return {"success": False, "error": f"Catalog item {catalog_sys_id} not found."}

        fields = _extract_fields(item)
        mandatory = [f for f in fields if f["mandatory"]]
        optional = [f for f in fields if not f["mandatory"]]

        return {
            "success": True,
            "catalog_sys_id": catalog_sys_id,
            "catalog_name": item.get("name", ""),
            "mandatory_fields": mandatory,
            "optional_fields": optional,
            "note": "Collect all mandatory fields from the user, then confirm before calling order_catalog.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("order_catalog", args_schema=OrderCatalogInput)
def order_catalog(catalog_sys_id: str, variables: dict, user_email: str = "") -> dict:
    """
    Place a ServiceNow catalog order. Only call after:
    1. The user has confirmed the catalog item and all variables.
    2. You have verified no duplicate order is in progress.
    This is a side-effecting operation — do not retry without checking for duplicates.
    """
    try:
        if not variables:
            return {"success": False, "error": "No variables provided. Collect required fields first."}

        result = snow.order_catalog_item(catalog_sys_id, variables)
        record = result.get("result", {})
        return {
            "success": True,
            "request_number": record.get("request_number", ""),
            "request_item_number": record.get("request_item_number", ""),
            "request_sys_id": record.get("request_sys_id", ""),
            "note": "Order placed. Share the request number with the user.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
