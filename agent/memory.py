"""
agent/memory.py — checkpointer factory.

Returns the right LangGraph checkpointer based on config.
InMemorySaver is the default for local dev.

To swap backends, set MEMORY_BACKEND env var:
  memory   → InMemorySaver (default, in-process)
  redis    → TODO: RedisSaver
  postgres → TODO: PostgresSaver
"""

from langgraph.checkpoint.memory import InMemorySaver

from config import get_memory_backend

# Single shared checkpointer instance for the lifetime of the process.
# InMemorySaver is thread-safe for concurrent requests.
_checkpointer = None


def get_checkpointer():
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    backend = get_memory_backend()

    if backend == "memory":
        _checkpointer = InMemorySaver()

    elif backend == "redis":
        # TODO: pip install langgraph-checkpoint-redis
        # from langgraph.checkpoint.redis import RedisSaver
        # import os
        # _checkpointer = RedisSaver.from_conn_string(os.environ["REDIS_URL"])
        raise NotImplementedError("Redis checkpointer not yet configured. Set MEMORY_BACKEND=memory.")

    elif backend == "postgres":
        # TODO: pip install langgraph-checkpoint-postgres
        # from langgraph.checkpoint.postgres import PostgresSaver
        # import os
        # _checkpointer = PostgresSaver.from_conn_string(os.environ["POSTGRES_URL"])
        raise NotImplementedError("Postgres checkpointer not yet configured. Set MEMORY_BACKEND=memory.")

    else:
        raise ValueError(f"Unknown memory backend: {backend!r}. Use 'memory', 'redis', or 'postgres'.")

    return _checkpointer
