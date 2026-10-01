"""
skills/loader.py — progressive skill loading via LLM intent classification.

On each request, a lightweight LLM call classifies the query against the
available skill catalogue and returns ONLY the skill names that are relevant.
Those skills' prompt bodies and tools are then loaded and injected.

Public interface (unchanged):
    load_skills(query: str) -> tuple[str, list[str]]
    list_all_skills() -> list[dict]

To swap in llmpivot or any other skill source, only this file changes.
graph.py and routes.py are unaware of how skills are selected.
"""

import json
import re
from pathlib import Path

import structlog
import yaml

from config import get_skills_config

log = structlog.get_logger()

_SKILLS_REGISTRY: list[dict] = []  # populated once at startup

# Project root resolved from this file's location — works regardless of cwd
_PROJECT_ROOT = Path(__file__).parent.parent

# ── File parsing ──────────────────────────────────────────────────────────────

def _parse_skill_file(path: Path) -> dict | None:
    """Parse a skill .md file into a dict with front-matter metadata + body."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not match:
        return None
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None

    return {
        "name": meta.get("name", path.stem),
        "domain": meta.get("domain", "general"),
        "description": meta.get("description", f"Handles {meta.get('domain', path.stem)} related requests"),
        "trigger_keywords": [kw.lower() for kw in meta.get("trigger_keywords", [])],
        "tools": meta.get("tools", []),
        "body": match.group(2).strip(),
    }


def _load_registry() -> None:
    """Load all skill .md files once at startup into the in-memory registry."""
    global _SKILLS_REGISTRY
    cfg = get_skills_config()
    skills_path = (_PROJECT_ROOT / cfg["path"]).resolve()
    _SKILLS_REGISTRY = []
    for md_file in sorted(skills_path.glob("*.md")):
        skill = _parse_skill_file(md_file)
        if skill:
            _SKILLS_REGISTRY.append(skill)
    log.info("skills.registry_loaded", count=len(_SKILLS_REGISTRY),
             skills=[s["name"] for s in _SKILLS_REGISTRY])


# ── LLM-based intent classifier ───────────────────────────────────────────────

def _build_classifier_prompt(query: str, history: list[dict] | None = None) -> str:
    """
    Build the classification prompt.
    Sends skill names + descriptions + last few conversation turns to the LLM.
    Does NOT send full skill bodies — keeps the call cheap and fast.

    history: list of {"role": "user"|"assistant", "content": str} dicts,
             most recent last. We use the last 6 messages (3 turns) max.
    """
    skill_list = "\n".join(
        f'- "{s["name"]}": {s["description"]}  (keywords: {", ".join(s["trigger_keywords"][:6])})'
        for s in _SKILLS_REGISTRY
    )

    history_block = ""
    if history:
        recent = history[-6:]  # last 3 turns max
        lines = []
        for msg in recent:
            role = msg.get("role", "user").capitalize()
            content = str(msg.get("content", ""))[:200]  # truncate long messages
            lines.append(f"  {role}: {content}")
        history_block = "\n\nRecent conversation:\n" + "\n".join(lines)

    return f"""You are a skill router for an IT service desk assistant.

Given the current user query and recent conversation history, identify which skills are needed.
Return ONLY a JSON array of skill names. Return [] if no skill is needed (greetings, out-of-scope).
Consider the full conversation context — if a ticket flow is in progress, keep ticket_skill active.

Available skills:
{skill_list}{history_block}

Current user query: "{query}"

Respond with ONLY valid JSON. Examples:
- ["ticket_skill"]
- ["knowledge_skill"]
- ["ticket_skill", "meeting_skill"]
- []"""


def _classify_with_llm(query: str, history: list[dict] | None = None) -> list[str]:
    """
    Use a lightweight LLM call to classify which skills are needed.
    Falls back to keyword matching if the LLM call fails.
    """
    try:
        from agent.router import select_model

        llm, model_id = select_model(query, preference="cost")
        prompt = _build_classifier_prompt(query, history)
        result = llm.invoke([{"role": "user", "content": prompt}])
        raw = result.content.strip()

        # Strip markdown code fences if the model wraps the JSON
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()

        skill_names = json.loads(raw)
        if not isinstance(skill_names, list):
            raise ValueError("Expected a JSON array")

        # Validate — only accept names that exist in the registry
        valid_names = {s["name"] for s in _SKILLS_REGISTRY}
        matched = [n for n in skill_names if n in valid_names]

        log.info("skills.classified", query_preview=query[:60], selected=matched, model=model_id)
        return matched

    except Exception as e:
        log.warning("skills.llm_classify_failed", error=str(e), fallback="keyword")
        return _classify_with_keywords(query)


def _classify_with_keywords(query: str) -> list[str]:
    """
    Fallback: simple keyword overlap. Used when the LLM classifier fails.
    """
    cfg = get_skills_config()
    threshold = cfg.get("relevance_threshold", 0.1)
    query_lower = query.lower()
    matched = []
    for skill in _SKILLS_REGISTRY:
        keywords = skill["trigger_keywords"]
        if not keywords:
            continue
        hits = sum(1 for kw in keywords if kw in query_lower)
        if hits / len(keywords) >= threshold:
            matched.append(skill["name"])
    return matched


# ── Public API ────────────────────────────────────────────────────────────────

def load_skills(query: str, history: list[dict] | None = None) -> tuple[str, list[str]]:
    """
    Classify the query + conversation history via LLM and load only relevant skills.

    Args:
        query:   current user message
        history: list of {"role": "user"|"assistant", "content": str} from the
                 checkpointer — most recent last. Pass None on first turn.

    Returns:
        system_prompt_addition: concatenated markdown body of matched skills
        tool_names:             flat list of tool names from all matched skills
    """
    if not _SKILLS_REGISTRY:
        _load_registry()

    if not _SKILLS_REGISTRY:
        return "", []

    matched_names = _classify_with_llm(query, history)

    skill_map = {s["name"]: s for s in _SKILLS_REGISTRY}
    bodies: list[str] = []
    tools: list[str] = []

    for name in matched_names:
        skill = skill_map.get(name)
        if skill:
            bodies.append(skill["body"])
            tools.extend(skill["tools"])

    return "\n\n---\n\n".join(bodies), tools


def list_all_skills() -> list[dict]:
    """Return skill metadata (no body) — used by the /skills endpoint."""
    if not _SKILLS_REGISTRY:
        _load_registry()
    return [
        {
            "name": s["name"],
            "domain": s["domain"],
            "description": s.get("description", ""),
            "trigger_keywords": s["trigger_keywords"],
            "tools": s["tools"],
        }
        for s in _SKILLS_REGISTRY
    ]
