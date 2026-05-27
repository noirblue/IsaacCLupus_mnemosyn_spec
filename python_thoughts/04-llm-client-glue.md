# 04 — LLM Client Glue: httpx, Streaming, Ollama SDK

**Status:** Research Complete | **Owner:** Mnemosyne Python Satellite Layer
**Last Updated:** 2026-05-27

---

## Executive Summary

The LLM client ecosystem is Python-first by design. OpenAI's official Python SDK (`openai`) is the reference implementation for the `/v1/chat/completions` protocol that every provider now emulates. The Ollama Python SDK (`ollama`) provides native, first-class access to local model serving with tool calling, thinking mode, and cloud model fallback. `httpx` remains the universal HTTP client for everything else. And the structured output ecosystem — `instructor`, `pydantic-ai`, `outlines` — exists almost entirely in Python.

Rust's `reqwest` is technically equivalent for raw HTTP, but it cannot replicate the higher-level abstractions: streaming chunk parsing, Pydantic validation with auto-retry, provider-agnostic client wrappers, and prompt engineering frameworks. For Mnemosyne's compilation and audit engines — which need structured outputs, multi-provider fallback, and token-budget-aware streaming — Python is not a convenience; it is the only ecosystem that has solved these problems.

This document breaks down client architecture, streaming patterns, structured output libraries, Ollama integration, and the satellite CLI contract for LLM glue.

---

## 1. The Rust Landscape: HTTP-Only

| Approach | Maturity | Streaming | Structured Output | Retry Logic | Multi-Provider | Verdict |
|---|---|---|---|---|---|---|
| `reqwest` + `serde` | Mature | Manual SSE parsing | Manual JSON Schema | Manual | Manual | Building block only |
| `async-openai` | Moderate | Yes | Manual | Manual | OpenAI only | Good for OpenAI-only |
| `ollama-rs` | Moderate | Yes | Manual | Manual | Ollama only | Good for Ollama-only |
| `instructor` equivalent | None | None | None | None | None | Does not exist |
| `pydantic-ai` equivalent | None | None | None | None | None | Does not exist |

**The structural problem:** Rust can do HTTP. It can parse JSON. It can even stream SSE. But it has no equivalent to the Python ecosystem's **orchestration layer** — the libraries that sit between your application logic and the raw HTTP response and handle: schema validation, automatic retry with error feedback, partial streaming of typed objects, multi-provider abstraction, and prompt template management. These are 3+ years of accumulated Python library development that Rust has not replicated.

> **Mnemosyne Decision:** Python satellite for all LLM client orchestration. Rust core delegates compilation, audit, and structured extraction tasks to the Python satellite via JSON-over-stdout.

---

## 2. The OpenAI-Compatible Universe

### 2.1 The `/v1/chat/completions` Protocol

Every major LLM provider now supports the OpenAI chat completions API format:

| Provider | Base URL | Notes |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | Reference implementation |
| Anthropic | `https://api.anthropic.com/v1` | Native format differs; OpenAI-compatible via adapter |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta` | OpenAI-compatible mode available |
| Ollama | `http://localhost:11434/v1` | Full OpenAI compatibility from day one |
| vLLM | `http://localhost:8000/v1` | OpenAI-compatible serving |
| SGLang | `http://localhost:30000/v1` | OpenAI-compatible serving |
| DeepSeek | `https://api.deepseek.com/v1` | OpenAI-compatible |
| Mistral | `https://api.mistral.ai/v1` | OpenAI-compatible |
| Groq | `https://api.groq.com/openai/v1` | OpenAI-compatible |
| Cohere | `https://api.cohere.com/v1` | OpenAI-compatible mode |

This means a single `openai` Python client, pointed at different base URLs, can talk to 15+ providers. This is the foundation of Mnemosyne's multi-provider strategy.

### 2.2 `openai` Python SDK: The Reference Client

**Key Capabilities:**

| Feature | Detail |
|---|---|
| **Sync / Async** | `OpenAI()` for sync; `AsyncOpenAI()` for async (asyncio) |
| **Streaming** | `stream=True` returns `Stream` (sync) or `AsyncStream` (async); SSE under the hood |
| **Structured output** | `response_format={"type": "json_object"}` or `response_format={"type": "json_schema", "json_schema": {...}}` |
| **Tool calling** | `tools=[{"type": "function", "function": {...}}]` with auto-parsed `tool_calls` |
| **Retries** | Built-in exponential backoff with `max_retries` parameter |
| **Timeout** | Configurable `timeout` per request |
| **Custom headers** | `default_headers` for auth, routing, etc. |
| **License** | Apache-2.0 |

**Streaming Example:**

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(base_url='http://localhost:11434/v1', api_key='ollama')

async def stream_compile(prompt: str):
    stream = await client.chat.completions.create(
        model='llama3.3:70b',
        messages=[{'role': 'user', 'content': prompt}],
        stream=True,
        max_tokens=4096,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
        if chunk.choices[0].finish_reason:
            break
```

**Tool Calling Example:**

```python
from openai import OpenAI

client = OpenAI(base_url='http://localhost:11434/v1', api_key='ollama')

response = client.chat.completions.create(
    model='qwen2.5:32b',
    messages=[{'role': 'user', 'content': 'What is the weather in Tokyo?'}],
    tools=[{
        'type': 'function',
        'function': {
            'name': 'get_weather',
            'description': 'Get current weather for a city',
            'parameters': {
                'type': 'object',
                'properties': {
                    'city': {'type': 'string'}
                },
                'required': ['city']
            }
        }
    }],
    tool_choice='auto',
)

if response.choices[0].message.tool_calls:
    for tool_call in response.choices[0].message.tool_calls:
        print(f"Tool: {tool_call.function.name}")
        print(f"Args: {tool_call.function.arguments}")
```

### 2.3 `httpx`: The Universal Fallback

When you need lower-level control — custom auth schemes, non-standard endpoints, or providers that don't fully conform to the OpenAI format — `httpx` is the tool.

| Feature | `httpx` | `openai` SDK |
|---|---|---|
| **HTTP/2** | Yes | No (HTTP/1.1 only) |
| **Connection pooling** | Yes | Yes (via `urllib3`) |
| **Async** | `AsyncClient` | `AsyncOpenAI` |
| **Streaming** | `response.iter_lines()` | Built-in SSE parsing |
| **JSON parsing** | Manual | Automatic |
| **Retry logic** | Manual | Built-in |
| **Type safety** | None | Pydantic models |
| **Best for** | Custom protocols, debugging | Standard OpenAI-compatible APIs |

**Mnemosyne uses `httpx` for:**
- Non-standard provider endpoints (e.g., custom vLLM deployments with extra parameters)
- Health check pings to Ollama (`GET /api/tags`)
- Direct model list fetching with custom parsing
- Debugging: capturing raw request/response bodies for the audit log

---

## 3. Ollama Python SDK: The Local-First Client

### 3.1 Why a Separate Ollama SDK?

While Ollama exposes an OpenAI-compatible `/v1/chat/completions` endpoint, the native Ollama API (`/api/chat`, `/api/generate`, `/api/pull`, `/api/ps`) provides capabilities that the OpenAI format cannot express:

| Native Ollama Feature | OpenAI-Compatible Equivalent | Notes |
|---|---|---|
| **Model pull** | None | `ollama.pull('llama3.3:70b')` — download models programmatically |
| **Model list** | `GET /v1/models` | Native `/api/tags` returns richer metadata (size, parameter count, quantization) |
| **Running models** | None | `ollama.ps()` — list loaded models and VRAM usage |
| **Thinking mode** | None | Native streaming exposes `thinking` field per chunk (Qwen3, etc.) |
| **Cloud model fallback** | None | `-cloud` suffix routes to Ollama cloud for models too large for local hardware |
| **Image input** | Multimodal chat | Native API is simpler for single-image prompts |
| **Tool calling** | OpenAI `tools` parameter | Ollama SDK auto-parses function docstrings |

### 3.2 Ollama SDK Architecture

```python
from ollama import Client, AsyncClient

# Sync client
client = Client(host='http://localhost:11434')

# Async client
async_client = AsyncClient(host='http://localhost:11434')

# Basic chat
response = client.chat(
    model='llama3.3:70b',
    messages=[{'role': 'user', 'content': 'Explain quantum computing'}]
)
print(response.message.content)

# Streaming chat
stream = client.chat(
    model='llama3.3:70b',
    messages=[{'role': 'user', 'content': 'Write a poem'}],
    stream=True,
)
for chunk in stream:
    print(chunk['message']['content'], end='', flush=True)

# Thinking mode (Qwen3, etc.)
stream = client.chat(
    model='qwen3:32b',
    messages=[{'role': 'user', 'content': 'Solve this logic puzzle'}],
    stream=True,
)
thinking = []
answer = []
for chunk in stream:
    if chunk['message'].get('thinking'):
        thinking.append(chunk['message']['thinking'])
    elif chunk['message'].get('content'):
        answer.append(chunk['message']['content'])
```

### 3.3 Ollama SDK vs OpenAI SDK for Ollama

| Factor | Ollama SDK | OpenAI SDK (pointed at Ollama) |
|---|---|---|
| **Model management** | Native pull/list/ps/delete | None |
| **Thinking mode** | Native `thinking` field | Not exposed |
| **Cloud fallback** | `-cloud` suffix | Not supported |
| **Tool docstring parsing** | Auto-parses Python docstrings | Manual schema definition |
| **Streaming type** | Dict | Pydantic object |
| **Ecosystem** | Ollama-specific | Universal (15+ providers) |
| **Best for** | Local-first, Ollama-specific features | Multi-provider portability |

**Mnemosyne Recommendation:** Use the **Ollama SDK** for Ollama-specific operations (model management, health checks, thinking mode). Use the **OpenAI SDK** for generic chat completions when multi-provider fallback is needed. The satellite can import both and route based on the task.

---

## 4. Structured Output: The Python-Only Ecosystem

### 4.1 Why Structured Output Matters for Mnemosyne

Mnemosyne's compilation engine needs LLMs to produce typed, validated outputs:
- **Concept extraction** from raw notes -> list of `Concept` objects with `name`, `definition`, `confidence`
- **Contradiction detection** -> list of `Contradiction` objects with `claim_a`, `claim_b`, `severity`
- **Article generation** -> structured markdown with `title`, `sections`, `citations`
- **Audit scoring** -> `AuditResult` with `score`, `issues`, `recommendations`

Raw string parsing is fragile. JSON mode helps but doesn't validate. The Python ecosystem has solved this with Pydantic-based libraries.

### 4.2 The Landscape: 2026 Rankings

| Rank | Library | Approach | Best For | License |
|---|---|---|---|---|
| 1 | **Instructor** | Post-gen validation + retry | Most Python teams | MIT |
| 2 | **Pydantic AI** | Agent framework with typed output | Python agent pipelines | MIT |
| 3 | **BAML** | Schema-Aligned Parsing (SAP) | Cross-language teams | Apache-2.0 |
| 4 | **Outlines** | Pre-gen constraint (FSM) | Self-hosted prototyping | Apache-2.0 |
| 5 | **XGrammar** | Pre-gen constraint (vLLM/SGLang) | Self-hosted production | Apache-2.0 |
| 6 | **Marvin** | Simple cast/extract/classify | Quick prototyping | Apache-2.0 |

### 4.3 Instructor: The Default Choice

**What it is:** A thin wrapper around any LLM client that adds Pydantic validation, JSON Schema generation, and automatic retry with validation error feedback.

**Key Capabilities:**

| Feature | Detail |
|---|---|
| **Providers** | 15+ direct: OpenAI, Anthropic, Gemini, Ollama, Mistral, Cohere, DeepSeek, etc. 100+ via LiteLLM |
| **Validation** | Pydantic models enforce types, ranges, enums, nested structures |
| **Auto-retry** | On validation failure, sends errors back to LLM for self-correction (usually fixes on 2nd try) |
| **Partial streaming** | `Partial[Model]` streams partially-filled Pydantic objects as tokens arrive |
| **Mode support** | JSON mode, Tools mode, Markdown mode, Plain text mode |
| **License** | MIT |

**Example: Concept Extraction for Mnemosyne:**

```python
import instructor
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List

class Concept(BaseModel):
    name: str = Field(description='The concept name')
    definition: str = Field(description='A concise definition')
    confidence: float = Field(ge=0.0, le=1.0, description='Extraction confidence')
    source_quotes: List[str] = Field(description='Verbatim quotes supporting this concept')

class ConceptExtraction(BaseModel):
    concepts: List[Concept] = Field(description='Extracted concepts from the text')
    summary: str = Field(description='Brief summary of the text')

# Patch any OpenAI-compatible client
client = instructor.from_openai(
    OpenAI(base_url='http://localhost:11434/v1', api_key='ollama')
)

result = client.chat.completions.create(
    model='llama3.3:70b',
    messages=[{
        'role': 'user',
        'content': 'Extract concepts from: "Attention Is All You Need introduces the Transformer..."'
    }],
    response_model=ConceptExtraction,
    max_retries=3,
)

for concept in result.concepts:
    print(f'{concept.name} ({concept.confidence:.2f}): {concept.definition}')
```

**Partial Streaming for Real-Time UI:**

```python
from instructor import Partial

stream = client.chat.completions.create(
    model='llama3.3:70b',
    messages=[{'role': 'user', 'content': 'Extract concepts...'}],
    response_model=Partial[ConceptExtraction],
    stream=True,
)

for partial in stream:
    # partial.concepts may be partially filled as tokens arrive
    print(f"Progress: {len(partial.concepts or [])} concepts found")
```

### 4.4 Pydantic AI: The Agent Framework

**What it is:** The official agent framework from the Pydantic team. Structured output is a core primitive, not an add-on.

| Feature | Detail |
|---|---|
| **Agents** | Typed agents with tool calling, dependency injection, graph workflows |
| **Structured output** | Every agent run returns a Pydantic model with validation |
| **Providers** | 20+ via unified interface |
| **Testing** | Built-in test fixtures and dataset replays |
| **Observability** | Optional Logfire integration for production dashboards |
| **License** | MIT |

**When to use Pydantic AI over Instructor:**
- Building multi-step agent workflows (not just extraction)
- Need tool calling with dependency injection
- Want built-in observability and tracing
- Already using Pydantic ecosystem heavily

**Mnemosyne Recommendation:** Use **Instructor** for the compilation engine's extraction tasks (concept extraction, contradiction detection, audit scoring). Use **Pydantic AI** if/when Mnemosyne builds agentic workflows that need tool calling and multi-step reasoning.

---

## 5. Mnemosyne's LLM Client Architecture

### 5.1 Two-Tier Model Strategy

Mnemosyne's compilation engine uses a two-tier approach:

```
Fast Model (30B MoE)          Heavy Model (70B-235B MoE)
     |                                |
     v                                v
[Concept Extraction]          [Article Generation]
[Contradiction Detection]     [Adversarial Review]
[Summarization]               [Cross-link Synthesis]
[Linting]                     [Quality Scoring]
     |                                |
     +------------+    +--------------+
                  |    |
                  v    v
            [Python Satellite]
                  |
                  v
            [Ollama :11434 / :11435]
```

The satellite abstracts away which model is running where. The Rust core sends a job with `model_tier: fast` or `model_tier: heavy`, and the satellite routes to the appropriate Ollama instance.

### 5.2 Satellite CLI Contract

```bash
# Single completion
python -m mnemosyne_py.llm complete \
    --model llama3.3:70b \
    --prompt-file /tmp/prompt.txt \
    --output /tmp/response.json \
    --max-tokens 4096 \
    --temperature 0.7

# Structured extraction
python -m mnemosyne_py.llm extract \
    --model llama3.3:70b \
    --prompt-file /tmp/prompt.txt \
    --schema-file /tmp/schema.json \
    --output /tmp/result.json \
    --max-retries 3

# Streaming completion (for conversation layer)
python -m mnemosyne_py.llm stream \
    --model qwen2.5:32b \
    --prompt-file /tmp/prompt.txt \
    --temperature 0.8
# Outputs JSON lines to stdout, one chunk per line

# Tool call
python -m mnemosyne_py.llm tool \
    --model qwen2.5:32b \
    --prompt-file /tmp/prompt.txt \
    --tools-file /tmp/tools.json \
    --output /tmp/tool_result.json

# Health check
python -m mnemosyne_py.llm health \
    --host http://localhost:11434
# Returns: {"status": "ok", "models": [...], "vram_used_mb": 8192}

# Model management
python -m mnemosyne_py.llm models \
    --host http://localhost:11434 \
    --action list  # or pull, ps, rm
```

### 5.3 Response JSON Schemas

**Complete response:**

```json
{
  "job_id": "job-uuid",
  "model": "llama3.3:70b",
  "prompt_tokens": 512,
  "completion_tokens": 2048,
  "total_tokens": 2560,
  "latency_ms": 45000,
  "finish_reason": "stop",
  "content": "# Attention Is All You Need\n\nThe Transformer architecture...",
  "usage": {
    "prompt_tokens": 512,
    "completion_tokens": 2048,
    "total_tokens": 2560
  },
  "metadata": {
    "provider": "ollama",
    "host": "http://localhost:11434",
    "timestamp": "2026-05-27T10:00:00Z"
  }
}
```

**Structured extraction response:**

```json
{
  "job_id": "job-uuid",
  "model": "llama3.3:70b",
  "schema_name": "ConceptExtraction",
  "validated": true,
  "retries": 0,
  "data": {
    "concepts": [
      {
        "name": "Transformer",
        "definition": "A neural network architecture based on self-attention...",
        "confidence": 0.95,
        "source_quotes": ["Attention Is All You Need introduces the Transformer"]
      }
    ],
    "summary": "This paper introduces the Transformer architecture..."
  },
  "usage": {
    "prompt_tokens": 1024,
    "completion_tokens": 512,
    "total_tokens": 1536
  },
  "latency_ms": 12000,
  "metadata": {
    "provider": "ollama",
    "extractor": "instructor",
    "timestamp": "2026-05-27T10:00:00Z"
  }
}
```

**Streaming chunk (JSON line):**

```json
{"chunk_index": 0, "content": "The", "finish_reason": null}
{"chunk_index": 1, "content": " Transformer", "finish_reason": null}
{"chunk_index": 2, "content": " architecture", "finish_reason": "stop"}
```

---

## 6. Audit Log Integration

Every LLM call in Mnemosyne is logged to the `audit_log` table. The Python satellite is responsible for capturing and formatting this data.

### 6.1 Audit Log Schema

The `audit_log` table stores:

```json
{
  "id": "audit-uuid",
  "job_id": "job-uuid",
  "timestamp": "2026-05-27T10:00:00Z",
  "model": "llama3.3:70b",
  "provider": "ollama",
  "host": "http://localhost:11434",
  "operation": "compile_article",
  "prompt_hash": "sha256:abc123...",
  "response_hash": "sha256:def456...",
  "prompt_tokens": 512,
  "completion_tokens": 2048,
  "total_tokens": 2560,
  "latency_ms": 45000,
  "cost_estimate_usd": 0.0,
  "finish_reason": "stop",
  "structured": true,
  "schema_name": "ArticleOutput",
  "validation_passed": true,
  "retries": 0,
  "error": null
}
```

### 6.2 Prompt Hashing for Reproducibility

```python
import hashlib
import json

def hash_prompt(messages: list, model: str, temperature: float) -> str:
    # Normalize and hash the complete prompt context
    normalized = json.dumps({
        'messages': messages,
        'model': model,
        'temperature': temperature,
    }, sort_keys=True, ensure_ascii=False)
    return 'sha256:' + hashlib.sha256(normalized.encode()).hexdigest()
```

This enables:
- **Reproducibility:** Re-run the exact same prompt and compare outputs
- **Caching:** Skip LLM calls when prompt hash matches cached result
- **Audit:** Prove what was asked and what was returned

---

## 7. Token Budget Management

Mnemosyne's conversation layer enforces token budgets. The Python satellite implements this.

### 7.1 Budget Rules

| Tier | Max Input Tokens | Max Output Tokens | Model |
|---|---|---|---|
| Fast extract | 8,192 | 2,048 | 30B MoE |
| Heavy compile | 16,384 | 8,192 | 70B MoE |
| Adversarial review | 32,768 | 4,096 | 70B MoE |
| Conversation | 4,096 | 2,048 | 30B MoE |
| Memory propose | 2,048 | 512 | 30B MoE |

### 7.2 Budget Enforcement

```python
import tiktoken

def enforce_budget(messages: list, max_tokens: int, model: str = 'gpt-4') -> list:
    encoder = tiktoken.encoding_for_model(model)
    total = sum(len(encoder.encode(m['content'])) for m in messages)
    
    if total > max_tokens:
        # Truncate from the middle (preserve system prompt and recent context)
        system_msg = [m for m in messages if m['role'] == 'system']
        user_msgs = [m for m in messages if m['role'] != 'system']
        
        # Keep first and last N messages, drop middle
        while total > max_tokens and len(user_msgs) > 2:
            # Drop oldest non-system message
            dropped = user_msgs.pop(0)
            total -= len(encoder.encode(dropped['content']))
    
    return system_msg + user_msgs
```

Note: For local models without exact tokenizer matches, use `tiktoken` as approximation or the model's native tokenizer via `transformers`.

---

## 8. Multi-Provider Fallback Strategy

Mnemosyne should not be locked to a single provider. The satellite implements a fallback chain:

```python
PROVIDERS = {
    'primary': {
        'name': 'ollama-foundry',
        'host': 'http://localhost:11434',
        'models': ['llama3.3:70b', 'qwen2.5:32b', 'gemma3:27b'],
    },
    'secondary': {
        'name': 'ollama-frontline',
        'host': 'http://localhost:11435',
        'models': ['qwen2.5:32b', 'gemma3:27b'],
    },
    'tertiary': {
        'name': 'groq-cloud',
        'host': 'https://api.groq.com/openai/v1',
        'api_key': '${GROQ_API_KEY}',
        'models': ['llama-3.3-70b-versatile', 'mixtral-8x7b-32768'],
    },
}

def call_with_fallback(prompt: str, model_tier: str, response_model=None):
    for provider_name, config in PROVIDERS.items():
        try:
            client = build_client(config)
            model = select_model(config['models'], model_tier)
            
            if response_model:
                return instructor.from_openai(client).chat.completions.create(
                    model=model,
                    messages=[{'role': 'user', 'content': prompt}],
                    response_model=response_model,
                )
            else:
                return client.chat.completions.create(
                    model=model,
                    messages=[{'role': 'user', 'content': prompt}],
                )
        except Exception as e:
            logger.warning(f'{provider_name} failed: {e}')
            continue
    
    raise RuntimeError('All providers failed')
```

---

## 9. Licensing & Compliance

| Component | License | Mnemosyne Impact |
|---|---|---|
| `openai` Python SDK | Apache-2.0 | Zero friction |
| `ollama` Python SDK | MIT | Zero friction |
| `httpx` | BSD-3-Clause | Zero friction |
| `instructor` | MIT | Zero friction |
| `pydantic-ai` | MIT | Zero friction |
| `pydantic` | MIT | Zero friction |
| `tiktoken` | MIT | Zero friction |
| `litellm` | MIT | Zero friction |

**All LLM client stack components are permissively licensed.** No AGPL concerns.

---

## 10. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Ollama model unload mid-job | Medium | High | Pre-load models; check `ollama ps` before job; retry with model pull |
| GPU OOM during heavy generation | Medium | High | Token budget enforcement; reduce batch size; fallback to smaller model |
| Provider timeout (slow model) | Medium | Medium | Configurable timeout per tier; fallback to faster model |
| Structured output validation fails repeatedly | Low | Medium | Max 3 retries; fall back to plain text with manual parsing flag |
| Prompt injection in user content | Medium | High | Input sanitization; separate system/user prompts; audit all inputs |
| Token count mismatch (tiktoken vs model) | Medium | Low | Use model-native tokenizer when available; over-budget by 10% |
| Python satellite startup latency | Low | Low | Warm pool or long-running daemon |
| Network partition between Rust core and satellite | Low | High | Timeout + retry; satellite health checks; local-only mode |

---

## 11. Decision Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-27 | Python satellite for all LLM client orchestration | Rust lacks structured output, retry, and multi-provider ecosystem |
| 2026-05-27 | `openai` SDK as primary client | Universal OpenAI-compatible protocol; 15+ providers |
| 2026-05-27 | `ollama` SDK for local-specific features | Model management, thinking mode, cloud fallback |
| 2026-05-27 | `httpx` for custom/debugging endpoints | HTTP/2, raw access, health checks |
| 2026-05-27 | `instructor` as structured output default | Best ecosystem, auto-retry, partial streaming, MIT license |
| 2026-05-27 | `pydantic-ai` for future agent workflows | Agent framework with typed tools and observability |
| 2026-05-27 | Token budgets enforced in satellite | Python has `tiktoken` and `transformers` tokenizers |
| 2026-05-27 | Multi-provider fallback chain | Resilience: Foundry -> Frontline -> Cloud |
| 2026-05-27 | Prompt hashing for audit reproducibility | `state.db` audit_log requires deterministic tracking |

---

## 12. Open Questions

1. **Should Mnemosyne support OpenAI/Anthropic cloud APIs directly?** The current design is local-first (Ollama). Cloud fallback is configured but not primary. Should cloud be a first-class citizen?
2. **Thinking mode exposure:** Should the compilation engine expose reasoning traces (Qwen3 thinking mode) to users for transparency, or keep them internal?
3. **Prompt versioning:** Should prompts be versioned in git and referenced by hash, or stored in `state.db`?
4. **Caching strategy:** Should identical prompt hashes return cached responses? For how long? Does temperature=0 make caching safe?
5. **Batch compilation:** Should the satellite support batching multiple extraction jobs into a single LLM call for efficiency?
6. **Model quantization tradeoffs:** Q4_K_M vs Q5_K_M vs Q8_0 — should the satellite auto-select based on available VRAM?

---

## 13. References

- [OpenAI Python SDK Documentation](https://github.com/openai/openai-python) — Official client
- [Ollama Python SDK Documentation](https://github.com/ollama/ollama-python) — Official client
- [Ollama Streaming Docs](https://docs.ollama.com/capabilities/streaming) — Streaming capabilities
- [Instructor Documentation](https://python.useinstructor.com/) — Structured output library
- [Pydantic AI Documentation](https://ai.pydantic.dev/) — Agent framework
- [httpx Documentation](https://www.python-httpx.org/) — HTTP client
- [LiteLLM Documentation](https://docs.litellm.ai/) — Multi-provider abstraction
- [8 Best Structured Output Libraries 2026](https://techsy.io/en/blog/best-llm-structured-output-libraries) — Comparative ranking
- [Top 5 Structured Output Libraries 2026](https://dev.to/thedailyagent/top-5-structured-output-libraries-for-llms-in-2026-48g0) — Feature comparison
- [Ollama API Practice Guide 2026](https://eastondev.com/blog/en/posts/ai/20260418-ollama-api-practice/) — Python SDK tutorial