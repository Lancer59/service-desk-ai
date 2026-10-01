"""
evaluation/scorers/faithfulness.py

LLM-as-judge scorer: is the answer grounded in the retrieved context / tool output?
Returns a float 0.0–1.0, or None if no context is available for this turn.
"""

import structlog

from evaluation.scorers._llm import get_judge_llm

log = structlog.get_logger()

_PROMPT = """You are an evaluation judge. Score how well the answer is grounded in the provided context.

Context (tool outputs or retrieved content):
{context}

Answer given to the user:
{answer}

Score from 0.0 to 1.0:
- 1.0 = every claim in the answer is supported by the context
- 0.5 = most claims are supported but some are introduced without context backing
- 0.0 = the answer makes claims not present in the context (hallucination)

Respond with ONLY a number between 0.0 and 1.0. No explanation."""


async def score(query: str, answer: str, context: str = "", **kwargs) -> float | None:
    if not context or not context.strip():
        return None

    try:
        llm = get_judge_llm(max_tokens=10)
        prompt = _PROMPT.format(context=context[:3000], answer=answer)
        result = await llm.ainvoke([{"role": "user", "content": prompt}])
        raw = result.content.strip()
        return max(0.0, min(1.0, float(raw)))
    except Exception as e:
        log.warning("eval.faithfulness.failed", error=str(e))
        return None
