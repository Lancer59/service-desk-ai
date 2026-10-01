"""
evaluation/scorers/intent_recognition.py

Heuristic scorer: did the agent recognise the correct domain intent?
Checks whether the skills/tools that were loaded match the query's apparent domain.
Returns True/False.
"""

import structlog

from skills.loader import list_all_skills

log = structlog.get_logger()


def _dominant_domain(query: str) -> str | None:
    """
    Find the skill domain with the highest keyword overlap for this query.
    Returns the domain name or None if nothing matches.
    """
    query_lower = query.lower()
    best_domain = None
    best_score = 0.0

    for skill in list_all_skills():
        keywords = skill["trigger_keywords"]
        if not keywords:
            continue
        hits = sum(1 for kw in keywords if kw in query_lower)
        score = hits / len(keywords)
        if score > best_score:
            best_score = score
            best_domain = skill["domain"]

    return best_domain if best_score > 0 else None


async def score(
    query: str,
    answer: str,
    context: str = "",
    skills_loaded: list[str] | None = None,
    **kwargs,
) -> bool:
    """
    Returns True if at least one of the loaded skills matches the query's dominant domain.
    Returns False if no skills were loaded or the wrong domain was loaded.
    """
    try:
        if not skills_loaded:
            # No skills loaded — either general query or miss
            dominant = _dominant_domain(query)
            return dominant is None  # True only if query genuinely has no domain

        dominant = _dominant_domain(query)
        if dominant is None:
            return True  # No clear domain in query, anything is fine

        return dominant in skills_loaded

    except Exception as e:
        log.warning("eval.intent_recognition.failed", error=str(e))
        return False
