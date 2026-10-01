"""
agent/graph.py — LangGraph agent using langchain.agents.create_agent (LangChain v1).

Per-request flow:
  1. Skill loader classifies query → returns skill prompt + tool names
  2. Router selects the right Azure deployment
  3. create_agent builds the ReAct loop with those tools + combined system prompt
  4. Agent is invoked with thread_id = conversation_id for memory continuity
"""

import json
import structlog
from langchain.agents import create_agent

from agent.memory import get_checkpointer
from agent.router import select_model
from skills.loader import load_skills, list_all_skills
from tools.registry import get_tools

log = structlog.get_logger()

BASE_SYSTEM_PROMPT = """You are a helpful IT Service Desk assistant.

Your job is to help employees with IT issues, answer questions, manage support tickets,
and find solutions from the knowledge base.

Guidelines:
- Be concise and professional.
- Always use the available tools rather than guessing or making up information.
- Confirm key details before taking any action (creating/closing tickets, etc.).
- If you cannot resolve an issue, offer to raise a support ticket.
- Never invent ticket numbers, article IDs, or system states.
- The user's email is available in the conversation context; use it when tools require it.
"""


def _get_conversation_history(conversation_id: str) -> list[dict]:
    """
    Read the existing conversation thread from the checkpointer and return
    it as a plain list of {"role": ..., "content": ...} dicts for the skill
    classifier. Returns [] on first turn or if checkpointer has no state yet.
    """
    try:
        from agent.memory import get_checkpointer
        checkpointer = get_checkpointer()
        config = {"configurable": {"thread_id": conversation_id}}
        state = checkpointer.get(config)
        if not state:
            return []

        messages = state.get("channel_values", {}).get("messages", [])
        history = []
        for msg in messages:
            cls_name = msg.__class__.__name__
            if cls_name == "HumanMessage":
                history.append({"role": "user", "content": str(msg.content)})
            elif cls_name == "AIMessage":
                # Only include text content, skip tool call messages
                content = msg.content
                if isinstance(content, str) and content.strip():
                    history.append({"role": "assistant", "content": content})
        return history
    except Exception:
        return []  # non-fatal — classifier falls back gracefully without history


def _extract_tool_context(messages: list) -> str:
    """
    Collect all tool (ToolMessage) outputs from the message list and
    concatenate them into a context string for faithfulness evaluation.
    """
    parts = []
    for msg in messages:
        # ToolMessage has type="tool" in LangChain
        if getattr(msg, "type", None) == "tool" or msg.__class__.__name__ == "ToolMessage":
            content = msg.content
            if isinstance(content, (dict, list)):
                content = json.dumps(content, default=str)
            parts.append(str(content))
    return "\n---\n".join(parts)


def _extract_token_usage(messages: list) -> dict:
    """
    Extract token usage from the last AI message's metadata.
    Handles multiple key variants across Azure OpenAI model versions.
    """
    for msg in reversed(messages):
        if msg.__class__.__name__ not in ("AIMessage", "ChatMessage"):
            continue

        # Try response_metadata first (standard LangChain location)
        meta = getattr(msg, "response_metadata", {}) or {}

        # Azure OpenAI key variants
        usage = (
            meta.get("token_usage")
            or meta.get("usage")
            or meta.get("usage_metadata")
        )

        # Also check usage_metadata as a direct attribute (langchain-core >= 0.2)
        if not usage:
            usage = getattr(msg, "usage_metadata", None)

        if usage and isinstance(usage, dict):
            # Normalise across key variants
            input_tokens = (
                usage.get("prompt_tokens")
                or usage.get("input_tokens")
                or usage.get("input", 0)
            )
            output_tokens = (
                usage.get("completion_tokens")
                or usage.get("output_tokens")
                or usage.get("output", 0)
            )
            total_tokens = (
                usage.get("total_tokens")
                or usage.get("total", 0)
                or (input_tokens + output_tokens)
            )
            return {
                "input": input_tokens or 0,
                "output": output_tokens or 0,
                "total": total_tokens or 0,
            }

    return {"input": 0, "output": 0, "total": 0}


async def run_agent(
    query: str,
    conversation_id: str,
    user_email: str = "",
    model_preference: str = "auto",
) -> dict:
    """
    Run the agent for one user turn.

    Returns: answer, model_used, skills_loaded, tools_called, tool_context, token_usage.
    """
    # 1. Pull existing conversation history from the checkpointer
    #    so the skill classifier has context from previous turns.
    history = _get_conversation_history(conversation_id)

    # 2. Load relevant skills using query + history
    skill_content, tool_names = load_skills(query, history=history)

    # Map tool names back to skill names for the response
    skill_registry = {s["name"]: s["tools"] for s in list_all_skills()}
    skills_loaded = [
        name for name, tools in skill_registry.items()
        if any(t in tool_names for t in tools)
    ]

    log.info(
        "agent.skills_loaded",
        conversation_id=conversation_id,
        skills_loaded=skills_loaded,
        skills_tools=tool_names,
    )

    # 2. Build system prompt: base + skill instructions + user context
    system_prompt = BASE_SYSTEM_PROMPT
    if user_email:
        system_prompt += f"\nThe requesting user's email is: {user_email}\n"
    if skill_content:
        system_prompt += f"\n\n## Domain Instructions\n\n{skill_content}"

    # 3. Select model via router
    llm, model_id = select_model(query, model_preference)

    # 4. Resolve tool names to tool objects
    tools = get_tools(tool_names)

    # 5. Build agent — create_agent compiles a LangGraph ReAct loop
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        checkpointer=get_checkpointer(),
    )

    # 6. Invoke with thread_id for conversation memory
    config = {
        "configurable": {
            "thread_id": conversation_id,
            "user_email": user_email,
        },
        "recursion_limit": 10,
    }

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": query}]},
        config=config,
    )

    messages = result.get("messages", [])

    # 7. Extract final answer
    answer = messages[-1].content if messages else "I was unable to generate a response."

    # 8. Extract tool calls (names only, for response metadata)
    tools_called = []
    for msg in messages:
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            tools_called.extend([tc["name"] for tc in tool_calls])

    # 9. Extract tool outputs — used by faithfulness scorer
    tool_context = _extract_tool_context(messages)

    # 10. Extract token usage — handles multiple Azure key variants
    token_usage = _extract_token_usage(messages)

    log.info(
        "agent.completed",
        conversation_id=conversation_id,
        model_used=model_id,
        tools_called=tools_called,
        token_usage=token_usage,
    )

    return {
        "answer": answer,
        "model_used": model_id,
        "skills_loaded": skills_loaded,
        "tools_called": tools_called,
        "tool_context": tool_context,   # passed to evaluator for faithfulness
        "token_usage": token_usage,
    }
