"""
evaluation/scorers/_llm.py

Shared helper: builds the judge LLM instance using the same router logic
so temperature and other model-specific settings are respected.
"""

from agent.router import _build_llm
from config import get_judge_model_id, get_model_by_id


def get_judge_llm(max_tokens: int = 10):
    """Return an LLM instance for the configured judge model, max_tokens overridden."""
    judge_id = get_judge_model_id()
    model_cfg = get_model_by_id(judge_id)
    if not model_cfg:
        raise ValueError(f"Judge model '{judge_id}' not found in config.yaml models list.")
    # Override max_tokens for eval — we only need a short score response
    cfg = {**model_cfg, "max_tokens": max_tokens}
    return _build_llm(cfg)
