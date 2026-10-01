"""
api/models.py — Pydantic request and response schemas for all routes.
"""

import uuid
from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User's message")
    conversation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Conversation thread ID — generate once per conversation, reuse for follow-ups",
    )
    user_email: str = Field(default="", description="User's email address")
    model_preference: str = Field(
        default="auto",
        description="Routing strategy: auto | cost | performance | fast | <deployment_id>",
    )


class TokenUsage(BaseModel):
    input: int = 0
    output: int = 0
    total: int = 0


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str
    model_used: str
    skills_loaded: list[str]
    tools_called: list[str]
    token_usage: TokenUsage
    latency_ms: int


class HealthResponse(BaseModel):
    status: str  # "ok" or "degraded"
    models_reachable: list[str]
    models_unreachable: list[str]


class SkillInfo(BaseModel):
    name: str
    domain: str
    description: str = ""
    trigger_keywords: list[str]
    tools: list[str]


class ModelInfo(BaseModel):
    id: str
    deployment: str
    cost_rank: int
    perf_rank: int
    latency_rank: int
    max_tokens: int
    tags: list[str]


class ErrorResponse(BaseModel):
    error: str
    detail: Any = None
