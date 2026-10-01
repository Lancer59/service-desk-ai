"""
evaluation/evaluator.py — fire-and-forget evaluation runner.

Called via asyncio.create_task() after the /chat response is sent.
Never blocks the client.

To add a new scorer:
  1. Create evaluation/scorers/my_scorer.py with async score() function.
  2. Add it to the SCORERS list below.
"""

import asyncio

import structlog

from config import get_evaluation_config, is_evaluation_enabled
from evaluation.scorers import answer_relevance, drift, faithfulness, intent_recognition

log = structlog.get_logger()

# Ordered list of (name, scorer_module) — add new scorers here
SCORERS = [
    ("answer_relevance", answer_relevance),
    ("faithfulness", faithfulness),
    ("intent_recognition", intent_recognition),
    ("drift", drift),
]


async def _run_scorers(
    query: str,
    answer: str,
    context: str,
    conversation_id: str,
    skills_loaded: list[str],
) -> dict:
    """Run all enabled scorers concurrently and return results dict."""
    eval_cfg = get_evaluation_config()
    enabled_scorers = eval_cfg.get("scorers", [s[0] for s in SCORERS])

    active = [(name, mod) for name, mod in SCORERS if name in enabled_scorers]

    tasks = [
        mod.score(
            query=query,
            answer=answer,
            context=context,
            conversation_id=conversation_id,
            skills_loaded=skills_loaded,
        )
        for _, mod in active
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    scores = {}
    for (name, _), result in zip(active, results):
        if isinstance(result, Exception):
            log.warning("eval.scorer_error", scorer=name, error=str(result))
            scores[name] = None
        else:
            scores[name] = result

    return scores


async def evaluate(
    query: str,
    answer: str,
    context: str = "",
    conversation_id: str = "",
    skills_loaded: list[str] | None = None,
) -> None:
    """
    Entry point — run all scorers and log results.
    Designed to be called with asyncio.create_task(), never awaited directly
    by the request handler.

    TODO: persist scores to a DB for dashboards and regression tracking.
    """
    if not is_evaluation_enabled():
        return

    try:
        scores = await _run_scorers(
            query=query,
            answer=answer,
            context=context,
            conversation_id=conversation_id,
            skills_loaded=skills_loaded or [],
        )

        log.info(
            "eval.scores",
            conversation_id=conversation_id,
            answer_relevance=scores.get("answer_relevance"),
            faithfulness=scores.get("faithfulness"),
            intent_recognition=scores.get("intent_recognition"),
            drift=scores.get("drift"),
        )

        # TODO: write scores to DB
        # await db.insert("evaluations", {
        #     "conversation_id": conversation_id,
        #     "timestamp": datetime.utcnow().isoformat(),
        #     **scores,
        # })

    except Exception as e:
        # Evaluation must never crash the app — log and move on
        log.error("eval.run_failed", conversation_id=conversation_id, error=str(e))
