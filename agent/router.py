"""
agent/router.py — multi-model router for Azure OpenAI deployments.

Single public function:
    select_model(query, preference) -> AzureChatOpenAI

Strategies:
  auto        — route by estimated query complexity
  cost        — cheapest deployment (lowest cost_rank)
  performance — best quality (lowest perf_rank)
  fast        — lowest latency (lowest latency_rank)
  <model_id>  — pin to exact deployment

Fallback: if the selected model fails, cascade through fallback_chain.
"""

import structlog

from langchain_openai import AzureChatOpenAI

from config import (
    get_azure_credentials,
    get_fallback_chain,
    get_model_by_id,
    get_models,
    get_router_config,
)

log = structlog.get_logger()


def _estimate_complexity(query: str) -> str:
    """
    Simple heuristic: estimate query complexity as 'simple' or 'complex'.
    Uses token count approximation (1 token ≈ 4 chars) and keyword signals.
    """
    router_cfg = get_router_config()
    threshold = router_cfg.get("complexity_threshold", 150)

    approx_tokens = len(query) / 4
    complex_signals = [
        "analyze", "compare", "explain why", "design", "architect",
        "step by step", "in detail", "thoroughly", "comprehensive",
    ]
    has_complex_signal = any(sig in query.lower() for sig in complex_signals)

    if approx_tokens > threshold or has_complex_signal:
        return "complex"
    return "simple"


def _pick_by_rank(rank_field: str) -> dict:
    """Return the model with the lowest value for the given rank field."""
    models = get_models()
    return min(models, key=lambda m: m.get(rank_field, 999))


def _select_deployment(query: str, preference: str) -> dict:
    """Return the model config dict based on the routing strategy."""
    preference = (preference or "auto").strip().lower()

    if preference == "auto":
        complexity = _estimate_complexity(query)
        if complexity == "complex":
            return _pick_by_rank("perf_rank")
        else:
            return _pick_by_rank("cost_rank")

    elif preference == "cost":
        return _pick_by_rank("cost_rank")

    elif preference == "performance":
        return _pick_by_rank("perf_rank")

    elif preference == "fast":
        return _pick_by_rank("latency_rank")

    else:
        # Treat preference as an explicit model id
        model = get_model_by_id(preference)
        if model:
            return model
        log.warning("router.unknown_preference", preference=preference, fallback="auto")
        return _pick_by_rank("cost_rank")


def _build_llm(model_cfg: dict) -> AzureChatOpenAI:
    """Instantiate AzureChatOpenAI from a model config dict."""
    creds = get_azure_credentials()

    kwargs = dict(
        azure_deployment=model_cfg["deployment"],
        azure_endpoint=creds["azure_endpoint"],
        api_key=creds["api_key"],
        api_version=creds["api_version"],
        max_tokens=model_cfg.get("max_tokens", 4096),
    )

    # Some models (e.g. o-series, gpt-5.x) only support the default temperature.
    # Set supports_temperature: false in config.yaml to skip passing it.
    if model_cfg.get("supports_temperature", True):
        kwargs["temperature"] = 0

    return AzureChatOpenAI(**kwargs)


def select_model(query: str, preference: str = "auto") -> tuple[AzureChatOpenAI, str]:
    """
    Select the appropriate Azure OpenAI deployment and return an LLM instance.

    Returns:
        (llm, model_id) — the LangChain LLM and the deployment id that was selected.

    Falls back through fallback_chain on instantiation failure.
    """
    model_cfg = _select_deployment(query, preference)
    log.info("router.selected", model_id=model_cfg["id"], preference=preference)

    try:
        return _build_llm(model_cfg), model_cfg["id"]
    except Exception as e:
        log.warning("router.primary_failed", model_id=model_cfg["id"], error=str(e))

    # Cascade through fallback chain
    for fallback_id in get_fallback_chain():
        if fallback_id == model_cfg["id"]:
            continue  # skip the one that just failed
        fallback_cfg = get_model_by_id(fallback_id)
        if not fallback_cfg:
            continue
        try:
            log.info("router.fallback", model_id=fallback_id)
            return _build_llm(fallback_cfg), fallback_id
        except Exception as fe:
            log.warning("router.fallback_failed", model_id=fallback_id, error=str(fe))

    raise RuntimeError("All models in the router and fallback chain failed to initialise.")
