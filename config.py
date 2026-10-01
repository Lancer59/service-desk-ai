"""
config.py — loads config.yaml then applies env var overrides.

Secrets (API keys, endpoints) come from env vars only — never config.yaml.
Everything else lives in config.yaml with env overrides for runtime flexibility.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()  # picks up .env file if present, no-op otherwise

_ROOT = Path(__file__).parent


def _load_yaml() -> dict[str, Any]:
    config_path = _ROOT / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def _build_config() -> dict[str, Any]:
    cfg = _load_yaml()

    # Runtime overrides from env vars
    if os.getenv("MEMORY_BACKEND"):
        cfg["memory"]["backend"] = os.getenv("MEMORY_BACKEND")

    if os.getenv("LOG_LEVEL"):
        cfg["logging"]["level"] = os.getenv("LOG_LEVEL")

    return cfg


# Single config object loaded once at startup
settings = _build_config()


# ── Azure OpenAI credentials (required, from env only) ──────────────────────

def get_azure_credentials() -> dict[str, str]:
    """Returns Azure OpenAI credentials from environment. Raises clearly if missing."""
    required = {
        "api_key": "AZURE_OPENAI_API_KEY",
        "azure_endpoint": "AZURE_OPENAI_ENDPOINT",
        "api_version": "AZURE_OPENAI_API_VERSION",
    }
    creds = {}
    missing = []
    for key, env_var in required.items():
        val = os.getenv(env_var)
        if not val:
            missing.append(env_var)
        else:
            creds[key] = val

    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Set them in your shell or in a .env file."
        )
    return creds


# ── Convenience accessors ────────────────────────────────────────────────────

def get_models() -> list[dict]:
    return settings["models"]


def get_model_by_id(model_id: str) -> dict | None:
    return next((m for m in get_models() if m["id"] == model_id), None)


def get_judge_model_id() -> str:
    return settings["evaluation"]["judge_model"]


def get_fallback_chain() -> list[str]:
    return settings.get("fallback_chain", [])


def get_router_config() -> dict:
    return settings["model_router"]


def get_memory_backend() -> str:
    return settings["memory"]["backend"]


def get_skills_config() -> dict:
    return settings["skills"]


def get_evaluation_config() -> dict:
    return settings["evaluation"]


def is_evaluation_enabled() -> bool:
    return settings["evaluation"].get("enabled", True)
