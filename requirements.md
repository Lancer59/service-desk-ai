# Service Desk AI — Requirements

> Standalone, improved, plug-and-play reimplementation of the existing platform Service Desk module.  
> Stack: FastAPI · LangGraph · LangChain v1 · Python 3.11+  
> Philosophy: **simple, flat, working** — no needless abstractions, no dummy modes, real code with TODOs where integration is pending.

---

## 1. What we are building

A self-contained FastAPI service that accepts a user message, routes it to the right Azure OpenAI deployment through a configurable model router, loads only the skills relevant to that message, runs a LangGraph agent that calls tools, evaluates the response quality fire-and-forget, and returns a structured answer — runnable locally with a single `uvicorn` command.

Two domains implemented at launch: **Ticket Management** and **Knowledge Base / Solution lookup**. All other domains follow the same pattern and drop in without code changes.

---

## 2. Project structure

```
service-desk-ai/
├── main.py                        # FastAPI app entry point
├── config.py                      # Loads config.yaml + env var overrides
├── config.yaml                    # All non-secret config
├── requirements.txt               # Pinned dependencies
├── requirements.in                # Unpinned source deps (pip-compile input)
│
├── agent/
│   ├── graph.py                   # LangGraph agent (create_agent + StateGraph)
│   ├── router.py                  # Multi-model router: select_model()
│   └── memory.py                  # Checkpointer factory (InMemorySaver now, swappable)
│
├── skills/
│   ├── loader.py                  # Parses .md front-matter, scores against query
│   ├── ticket_skill.md
│   └── knowledge_skill.md
│
├── tools/
│   ├── registry.py                # Returns tool list based on loaded skills
│   ├── ticket_tools.py            # 4 ticket tools (real impl, TODO for integration)
│   └── knowledge_tools.py        # 2 KB tools (real impl, TODO for integration)
│
├── evaluation/
│   ├── evaluator.py               # asyncio.create_task() fire-and-forget runner
│   └── scorers/
│       ├── answer_relevance.py
│       ├── faithfulness.py
│       ├── intent_recognition.py
│       └── drift.py
│
└── api/
    ├── models.py                  # Pydantic request/response schemas
    └── routes.py                  # /chat, /health, /models, /skills
```

Each file does one job. No circular imports.

---

## 3. Agent: `langchain.agents.create_agent`

**File:** `agent/graph.py`

The current LangChain v1 API uses `langchain.agents.create_agent()`, which supersedes the now-deprecated `langgraph.prebuilt.create_react_agent`. The new API returns a compiled LangGraph graph with a built-in ReAct loop, checkpointer support, and optional middleware.

```python
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

agent = create_agent(
    model=llm,                  # AzureChatOpenAI instance from router
    tools=tools,                # tools selected by skill loader for this request
    system_prompt=system_prompt, # base prompt + injected skill markdown
    checkpointer=InMemorySaver(),
)

result = await agent.ainvoke(
    {"messages": [{"role": "user", "content": query}]},
    config={"configurable": {"thread_id": conversation_id}},
)
```

- `thread_id = conversation_id` — LangGraph handles multi-turn memory natively via checkpointer.
- No custom serialization or memory juggling. The agent state is the conversation.
- System prompt is assembled per-request: base instructions + skill content for matched skills only.
- Recursion limit set at invoke time (default: 10).

---

## 4. Multi-model router

**File:** `agent/router.py`

Single function: `select_model(query: str, preference: str) -> AzureChatOpenAI`

All Azure OpenAI deployments. Multiple deployments within the same Azure endpoint, differentiated by capability, cost, and speed.

### Routing strategies

| Strategy | Logic |
|---|---|
| `auto` | Estimate query complexity (token length + keyword signals for reasoning/coding/analysis); route to strong model if above threshold, cheap model otherwise |
| `cost` | Always pick deployment with lowest `cost_rank` |
| `performance` | Always pick deployment with lowest `perf_rank` (best quality) |
| `fast` | Always pick deployment with lowest `latency_rank` |
| `<deployment_id>` | Pin to that exact deployment name |

Fallback: if the selected model call fails, cascade through `fallback_chain` in order.

### Model config in `config.yaml`

```yaml
models:
  - id: gpt-4o-mini
    deployment: gpt-4o-mini          # Azure deployment name
    cost_rank: 1
    perf_rank: 3
    latency_rank: 1
    max_tokens: 16000
    tags: [fast, cheap, eval_judge]

  - id: gpt-4o
    deployment: gpt-4o
    cost_rank: 3
    perf_rank: 1
    latency_rank: 2
    max_tokens: 128000
    tags: [complex, reasoning]

  - id: o3-mini
    deployment: o3-mini
    cost_rank: 2
    perf_rank: 2
    latency_rank: 2
    max_tokens: 65000
    tags: [reasoning, balanced]

fallback_chain: [gpt-4o, gpt-4o-mini]

model_router:
  default_strategy: auto
  complexity_threshold: 150          # estimated tokens; above = complex
```

Azure credentials are env vars only — never in `config.yaml`:
```
AZURE_OPENAI_API_KEY
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_API_VERSION
```

Adding a new Azure deployment = one new entry in `config.yaml`, zero code changes.

---

## 5. Skills system (progressive loading)

**Files:** `skills/loader.py` + `skills/*.md`

### Skill file format

```markdown
---
name: ticket_skill
domain: tickets
trigger_keywords: [ticket, incident, INC, raise, create, update, close, status]
tools: [create_ticket, get_ticket_status, update_ticket, close_ticket]
---

# Ticket Skill

## Behavior
When the user wants to create, check, update, or close a ticket...

## create_ticket
Use this tool when the user reports an issue and wants it logged formally.
Always collect: short summary, detailed description, and priority.
...
```

### Loading logic

1. At startup, parse all `skills/*.md` front-matter into an in-memory dict (fast, no I/O per request).
2. On each request, score each skill against the user query using keyword overlap ratio.
3. Skills above `relevance_threshold` (default: 0.3) are loaded.
4. Their markdown body is concatenated and injected into the system prompt.
5. Only tools named in loaded skills' `tools:` list are passed to the agent.

A ticket query loads ticket tools and ticket instructions. A KB query loads KB tools only. Neither sees the other's tools or prompt text.

### Modular / swappable skill source

The loader is designed so the skill source can be swapped without touching `graph.py` or any other file. The interface is:

```python
# skills/loader.py

def load_skills(query: str) -> tuple[str, list[str]]:
    """
    Returns (system_prompt_addition, list_of_tool_names).
    Current implementation: reads from skills/*.md files.
    Future: could call llmpivot.PromptManager or any other source.
    """
```

When you're ready to plug in `llmpivot`, only `loader.py` changes. Everything else stays the same.

### Adding a new skill domain

Drop a new `.md` file in `skills/`. No code change required.

---

## 6. Memory

**File:** `agent/memory.py`

```python
from langgraph.checkpoint.memory import InMemorySaver

def get_checkpointer(backend: str = "memory"):
    if backend == "memory":
        return InMemorySaver()
    # TODO: RedisSaver when MEMORY_BACKEND=redis
    # TODO: PostgresSaver when MEMORY_BACKEND=postgres
    raise ValueError(f"Unknown memory backend: {backend}")
```

Default: `InMemorySaver` — in-process, no external dependencies, works locally.  
Controlled by `MEMORY_BACKEND` env var (default: `memory`).

---

## 7. Evaluation (fire-and-forget)

**File:** `evaluation/evaluator.py`

Called via `asyncio.create_task()` after the response is returned to the client. Never blocks `/chat`.

Results go to structured JSON logs. Can be written to a DB later with a TODO stub.

```python
async def run_evaluation(query, answer, context, conversation_id):
    results = await asyncio.gather(
        answer_relevance.score(query, answer, context),
        faithfulness.score(query, answer, context),
        intent_recognition.score(query, answer),
        drift.score(query, conversation_id),
        return_exceptions=True,
    )
    log.info("eval", conversation_id=conversation_id, scores=results)
    # TODO: persist to DB
```

### Scorers

| Scorer | Method | Measures |
|---|---|---|
| `answer_relevance` | LLM-as-judge using `eval_judge` model | Does the answer address the question? |
| `faithfulness` | LLM-as-judge using `eval_judge` model | Is the answer grounded in tool output / retrieved content? |
| `intent_recognition` | Keyword heuristic | Was the correct skill/domain loaded? |
| `drift` | Cosine similarity between consecutive user turns | Is the conversation going off-topic? |

### Scorer interface

```python
# Each scorer file exports exactly this:
async def score(query: str, answer: str, context: str = "", **kwargs) -> float | bool:
    ...
```

To add a scorer: create `evaluation/scorers/my_scorer.py` with `score()`, add it to the list in `evaluator.py`. That's all.

The evaluation module is self-contained and can be extracted as a standalone package later with no refactoring.

---

## 8. Tools

**Files:** `tools/ticket_tools.py`, `tools/knowledge_tools.py`

Every tool is a `@tool`-decorated LangChain function with a Pydantic input schema. Real implementation with TODOs for the actual integration calls.

### Tool contract

- Typed Pydantic input schema (LLM sees this as the call spec)
- Docstring = tool description shown to LLM
- Returns structured dict
- Never raises silently — catches and returns error dict
- Logs tool name + non-sensitive input summary

### Ticket tools (`ticket_tools.py`)

| Tool | Description |
|---|---|
| `create_ticket` | Create an incident — summary, description, priority. TODO: ServiceNow API call |
| `get_ticket_status` | Get ticket status by number. TODO: ServiceNow API call |
| `update_ticket` | Add work notes or change priority. TODO: ServiceNow API call |
| `close_ticket` | Close a ticket with closing notes. TODO: ServiceNow API call |

### Knowledge tools (`knowledge_tools.py`)

| Tool | Description |
|---|---|
| `search_knowledge_base` | Search KB by keywords, return top N article summaries. TODO: FAISS/vector search |
| `get_article_detail` | Fetch full KB article content by ID. TODO: KB API call |

---

## 9. API

**Files:** `api/routes.py`, `api/models.py`

### `POST /chat`

**Request**
```json
{
  "query": "Create a ticket for VPN not working",
  "conversation_id": "uuid-string",
  "user_email": "user@company.com",
  "model_preference": "auto"
}
```
`model_preference` accepts: `auto`, `cost`, `performance`, `fast`, or a deployment id.

**Response**
```json
{
  "answer": "I have created incident INC0012345...",
  "conversation_id": "uuid-string",
  "model_used": "gpt-4o-mini",
  "skills_loaded": ["ticket_skill"],
  "tools_called": ["create_ticket"],
  "token_usage": {"input": 420, "output": 180, "total": 600},
  "latency_ms": 1840
}
```

Evaluation scores are not in the response — they run async and go to logs.

### `GET /health`
Returns service status + which Azure deployments are reachable.

### `GET /skills`
Lists all registered skills with their name, domain, trigger keywords, and tools.

### `GET /models`
Lists configured deployments and their routing metadata.

---

## 10. Configuration

**File:** `config.py` — reads `config.yaml`, then overrides with matching env vars.

```yaml
# config.yaml

model_router:
  default_strategy: auto
  complexity_threshold: 150

memory:
  backend: memory

skills:
  relevance_threshold: 0.3
  path: skills/

evaluation:
  enabled: true
  judge_model: gpt-4o-mini

logging:
  level: INFO
  format: json
```

**Env vars** (secrets and runtime overrides):
```
AZURE_OPENAI_API_KEY        # required
AZURE_OPENAI_ENDPOINT       # required
AZURE_OPENAI_API_VERSION    # required
MEMORY_BACKEND              # optional, overrides config.yaml
LOG_LEVEL                   # optional, overrides config.yaml
```

---

## 11. Dependencies (`requirements.in` → `requirements.txt`)

```
fastapi
uvicorn[standard]
langchain>=1.0.0
langgraph>=1.2.0
langchain-openai
pydantic>=2.0
pyyaml
python-dotenv
structlog
scikit-learn           # cosine similarity for drift scorer
tiktoken               # token counting for router complexity estimate
```

`requirements.txt` is generated via `pip-compile requirements.in` with pinned versions.

---

## 12. Running locally

```bash
# 1. Create and activate venv
python -m venv .venv
.venv\Scripts\Activate.ps1       # Windows PowerShell

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set env vars (or create .env file)
$env:AZURE_OPENAI_API_KEY="..."
$env:AZURE_OPENAI_ENDPOINT="..."
$env:AZURE_OPENAI_API_VERSION="2024-02-01"

# 4. Run
uvicorn main:app --reload --port 8000
```

---

## 13. What is out of scope for v1

Each item has a clear extension point — nothing is architecturally blocked.

| Feature | Extension point |
|---|---|
| Auth | Middleware in `main.py` |
| Real ServiceNow integration | TODO stubs in `ticket_tools.py` |
| Real FAISS / vector search | TODO stubs in `knowledge_tools.py` |
| Redis / Postgres memory | `agent/memory.py` `get_checkpointer()` |
| Non-Azure LLM providers | New model entry in `config.yaml`, LiteLLM optional |
| llmpivot skill source | Swap `skills/loader.py` internals only |
| Embedding-based skill matching | `skills/loader.py`, behind `match_mode: embedding` config |
| Streaming responses | `agent/graph.py` `.astream()` |
| Docker / container | Add `Dockerfile` + `docker-compose.yml` later |
| Eval score persistence | TODO in `evaluation/evaluator.py` |
| Human-in-the-loop escalation | New skill + tool |

---

## 14. Deliverables (v1)

| Item | Status |
|---|---|
| FastAPI service with 4 routes | Build |
| `langchain.agents.create_agent` based agent | Build |
| Multi-model router (5 strategies, Azure OpenAI) | Build |
| Skills loader (`skills/*.md` + keyword scoring) | Build |
| `ticket_skill.md` + `knowledge_skill.md` | Build |
| 4 ticket tools + 2 KB tools (real impl + TODOs) | Build |
| Evaluation module (4 scorers, fire-and-forget) | Build |
| `config.yaml` + env var config system | Build |
| `requirements.in` + `requirements.txt` | Build |
| README (setup + how to extend) | Build |
