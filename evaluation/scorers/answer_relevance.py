"""
evaluation/scorers/answer_relevance.py

LLM-as-judge scorer: does the answer actually address the user's question?
Returns a float 0.0–1.0.
"""

import structlog

from evaluation.scorers._llm import get_judge_llm

log = structlog.get_logger()

_PROMPT = """You are an evaluation judge. Score how well the answer addresses the user's question.

Question: {query}

Answer: {answer}

Score from 0.0 to 1.0:
- 1.0 = answer fully and directly addresses the question
- 0.5 = answer is partially relevant or misses some aspects
- 0.0 = answer is off-topic or does not address the question at all

Respond with ONLY a number between 0.0 and 1.0. No explanation."""


async def score(query: str, answer: str, context: str = "", **kwargs) -> float:
    try:
        llm = get_judge_llm(max_tokens=10)
        prompt = _PROMPT.format(query=query, answer=answer)
        result = await llm.ainvoke([{"role": "user", "content": prompt}])
        raw = result.content.strip()
        return max(0.0, min(1.0, float(raw)))
    except Exception as e:
        log.warning("eval.answer_relevance.failed", error=str(e))
        return 0.0
