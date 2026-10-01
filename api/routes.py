"""
api/routes.py — all route definitions.

Routes:
  POST /chat          — main conversational endpoint
  GET  /health        — liveness + model reachability
  GET  /skills        — list registered skills
  GET  /models        — list configured model deployments
  GET  /approve       — approval webhook (approve/reject pending requests)
"""

import asyncio
import time

import structlog
from fastapi import APIRouter, HTTPException, Query

from agent.graph import run_agent
from api.models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ModelInfo,
    SkillInfo,
    TokenUsage,
)
from config import get_models
from evaluation.evaluator import evaluate
from skills.loader import list_all_skills

router = APIRouter()
log = structlog.get_logger()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main conversational endpoint.

    Send a query with a conversation_id. Reuse the same conversation_id
    for follow-up messages — the agent remembers the thread via LangGraph checkpointer.
    """
    start = time.monotonic()

    try:
        result = await run_agent(
            query=request.query,
            conversation_id=request.conversation_id,
            user_email=request.user_email,
            model_preference=request.model_preference,
        )
    except EnvironmentError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        log.error("chat.error", error=str(e), conversation_id=request.conversation_id)
        raise HTTPException(status_code=500, detail="Agent error. Check server logs.")

    latency_ms = int((time.monotonic() - start) * 1000)

    # Fire-and-forget evaluation — tool_context now populated for faithfulness scorer
    asyncio.create_task(
        evaluate(
            query=request.query,
            answer=result["answer"],
            context=result.get("tool_context", ""),
            conversation_id=request.conversation_id,
            skills_loaded=result["skills_loaded"],
        )
    )

    usage = result.get("token_usage", {})
    return ChatResponse(
        answer=result["answer"],
        conversation_id=request.conversation_id,
        model_used=result["model_used"],
        skills_loaded=result["skills_loaded"],
        tools_called=result["tools_called"],
        token_usage=TokenUsage(
            input=usage.get("input", 0),
            output=usage.get("output", 0),
            total=usage.get("total", 0),
        ),
        latency_ms=latency_ms,
    )


@router.get("/health", response_model=HealthResponse)
async def health():
    """Liveness check — probes each configured Azure deployment."""
    from agent.router import _build_llm
    from config import get_models

    reachable = []
    unreachable = []

    for model_cfg in get_models():
        try:
            llm = _build_llm(model_cfg)
            await llm.ainvoke([{"role": "user", "content": "ping"}])
            reachable.append(model_cfg["id"])
        except EnvironmentError:
            # Missing creds — all unreachable
            return HealthResponse(
                status="degraded",
                models_reachable=[],
                models_unreachable=[m["id"] for m in get_models()],
            )
        except Exception:
            unreachable.append(model_cfg["id"])

    return HealthResponse(
        status="ok" if not unreachable else "degraded",
        models_reachable=reachable,
        models_unreachable=unreachable,
    )


@router.get("/skills", response_model=list[SkillInfo])
async def skills():
    """List all registered skills."""
    return [SkillInfo(**s) for s in list_all_skills()]


@router.get("/models", response_model=list[ModelInfo])
async def models():
    """List all configured Azure OpenAI deployments."""
    return [
        ModelInfo(
            id=m["id"],
            deployment=m["deployment"],
            cost_rank=m.get("cost_rank", 0),
            perf_rank=m.get("perf_rank", 0),
            latency_rank=m.get("latency_rank", 0),
            max_tokens=m.get("max_tokens", 0),
            tags=m.get("tags", []),
        )
        for m in get_models()
    ]


@router.get("/approve")
async def approve(
    document_id: str = Query(..., description="Approval document ID from the Teams card"),
    action: str = Query(..., description="approve or reject"),
):
    """
    Approval webhook — called when an approver clicks Approve or Reject
    on the Teams Adaptive Card sent by submit_request_for_approval_tool.

    On approval, provisions the requested group operation.
    Uses atomic compare-and-set to prevent double-click provisioning.
    """
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    try:
        from clients.mongodb import claim_and_update_approval, get_approval_request
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    doc = get_approval_request(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Approval request {document_id} not found.")

    if doc["status"] != "Pending":
        return {
            "document_id": document_id,
            "status": doc["status"],
            "message": f"Request already processed with status: {doc['status']}",
        }

    if action == "reject":
        claimed = claim_and_update_approval(document_id, "Rejected")
        if not claimed:
            return {"document_id": document_id, "message": "Already processed by another request."}
        log.info("approval.rejected", document_id=document_id)
        return {"document_id": document_id, "status": "Rejected", "message": "Request rejected."}

    # Approve — claim atomically first, then provision
    claimed = claim_and_update_approval(document_id, "Approved")
    if not claimed:
        return {"document_id": document_id, "message": "Already processed by another request."}

    request_data = doc["request_data"]
    request_type = request_data.get("request_type", "")

    try:
        from clients import graph as graph_client
        from clients.mongodb import claim_and_update_approval as update_status

        if request_type == "add_members":
            group_id = request_data["group_id"]
            for user_id in request_data.get("member_ids", []):
                graph_client.add_group_member(group_id, user_id)
            claim_and_update_approval(document_id, "provisioned")
            log.info("approval.provisioned", document_id=document_id, type="add_members")
            return {
                "document_id": document_id,
                "status": "provisioned",
                "message": f"Added {len(request_data.get('member_ids', []))} member(s) to group.",
            }

        elif request_type == "create_group":
            group_name = request_data["group_name"]
            mail_nickname = group_name.lower().replace(" ", "_")
            new_group = graph_client.create_security_group(group_name, mail_nickname)
            new_group_id = new_group.get("id", "")

            # Add members if any were specified
            for user_id in request_data.get("member_ids", []):
                graph_client.add_group_member(new_group_id, user_id)

            claim_and_update_approval(document_id, "provisioned")
            log.info("approval.provisioned", document_id=document_id, type="create_group")
            return {
                "document_id": document_id,
                "status": "provisioned",
                "group_id": new_group_id,
                "message": f"Group '{group_name}' created successfully.",
            }

        else:
            # TODO: add handlers for other request types here
            claim_and_update_approval(document_id, "Failed")
            raise HTTPException(
                status_code=422,
                detail=f"Unknown request_type '{request_type}'. Cannot provision.",
            )

    except HTTPException:
        raise
    except Exception as e:
        claim_and_update_approval(document_id, "Failed")
        log.error("approval.provision_failed", document_id=document_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Provisioning failed: {e}")
