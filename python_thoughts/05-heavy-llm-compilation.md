# 05 — Heavy LLM Compilation: Prompt Templates, Response Parsing, Structured Outputs

**Status:** Research Complete | **Owner:** Mnemosyne Python Satellite Layer
**Last Updated:** 2026-05-27

---

## Executive Summary

The 'heavy model' tier (70B+ parameters) is called via HTTP regardless of language. But the ergonomics of constructing prompts, parsing responses, and enforcing structured outputs are overwhelmingly Python-first. The prompt engineering ecosystem — Jinja2 templating, Instructor/Pydantic-AI structured output, DSPy programmatic optimization, and the `openai`/`ollama` SDK streaming abstractions — exists almost entirely in Python. Rust's `reqwest` can make the same HTTP calls, but it cannot replicate the orchestration layer that sits between your application logic and the raw LLM response.

For Mnemosyne's compilation engine — which must generate cross-linked wiki articles, detect contradictions, run adversarial reviews, and produce typed audit scores — Python is not merely convenient. It is the only ecosystem that has solved the full stack: template versioning, structured generation with validation, multi-step agent workflows, and programmatic prompt optimization.

This document breaks down prompt template architecture, structured output libraries, streaming response handling, the compilation pipeline, and integration fit for the heavy model tier.

---

## 1. The Rust Landscape: HTTP-Only, Again

| Approach | Maturity | Streaming | Structured Output | Retry Logic | Prompt Templates | Verdict |
|---|---|---|---|---|---|---|
| `reqwest` + `serde` | Mature | Manual SSE parsing | Manual JSON Schema | Manual | String concat | Building block only |
| `async-openai` | Moderate | Yes | Manual | Manual | None | Good for OpenAI-only |
| `ollama-rs` | Moderate | Yes | Manual | Manual | None | Good for Ollama-only |
| Jinja2 equivalent | None | None | None | None | None | Does not exist |
| Instructor equivalent | None | None | None | None | None | Does not exist |
| DSPy equivalent | None | None | None | None | None | Does not exist |

**The structural problem:** Rust can make HTTP requests. It can parse JSON. It can even stream SSE chunks. But the heavy model tier is not about making HTTP calls — it is about **what you do before and after the call**:
- **Before:** Compose prompts from templates with conditional logic, few-shot examples, and dynamic context injection. Version and A/B test those templates. Optimize them programmatically against metrics.
- **After:** Parse streaming responses into typed objects. Validate against schemas. Retry on validation failure with error feedback. Extract structured data (concepts, citations, contradictions) from free-form text.

These are 3+ years of accumulated Python library development that Rust has not replicated. The gap is not in HTTP capability; it is in the **orchestration layer**.

> **Mnemosyne Decision:** Python satellite for all heavy LLM compilation tasks. Rust core delegates compilation, audit, and structured extraction to the Python satellite via JSON-over-stdout.

---

## 2. Prompt Template Architecture

### 2.1 Why Templates Matter for Compilation

Mnemosyne's compilation engine generates wiki articles from raw notes, PDFs, transcripts, and web pages. The prompts that drive this are not static strings — they are dynamic compositions that vary by:

| Variable | Example |
|---|---|
| **Source type** | Notes vs. paper vs. transcript vs. API docs |
| **Content length** | Short note (500 tokens) vs. long paper (8K tokens) |
| **Maturity stage** | Seed -> refining -> established -> disputed |
| **Namespace** | Self (personal) vs. world (external) vs. synthesis (LLM-generated) |
| **Target audience** | Expert vs. beginner vs. agent consumption |
| **Existing links** | Related pages in the graph to cross-reference |
| **Contradictions** | Flagged conflicts that must be addressed or noted |

A production prompt template system has four subsystems: a **template registry** for storage and versioning, a **rendering engine** for variable substitution, a **validation layer** for constraints, and an **experiment layer** for A/B testing.

### 2.2 Jinja2: The Rendering Engine

**Jinja2** is the standard Python templating engine, adopted by Microsoft Semantic Kernel, Hugging Face chat templates, LangChain, and many custom prompt systems. It supports:

| Feature | Jinja2 Syntax | Use Case |
|---|---|---|
| **Variable substitution** | `{{ variable }}` | Inject dynamic content |
| **Conditionals** | `{% if condition %}...{% endif %}` | Adapt prompt based on source type |
| **Loops** | `{% for item in items %}...{% endfor %}` | Inject few-shot examples dynamically |
| **Filters** | `{{ text | truncate(1000) }}` | Trim content to fit token budget |
| **Macros** | `{% macro concept_card(c) %}...{% endmacro %}` | Reusable prompt components |
| **Template inheritance** | `{% extends 'base.j2' %}` | Base prompt structure with overrides |

**Example: Mnemosyne Article Compilation Template**

```jinja2
{% extends 'base_compile.j2' %}

{% block system %}
You are Mnemosyne, a knowledge compilation engine.
Generate a wiki article from the provided source material.
Follow these rules:
- Use markdown formatting
- Include inline citations [[source_id]]
- Link to related concepts [[Concept Name]]
- Flag contradictions with {{contradiction_marker}}
- Target audience: {{ audience | default('general') }}
{% endblock %}

{% block context %}
{% if related_pages %}
## Related Pages in Knowledge Graph
{% for page in related_pages %}
- [[{{ page.title }}]] ({{ page.namespace }}): {{ page.summary | truncate(200) }}
{% endfor %}
{% endif %}

{% if contradictions %}
## Flagged Contradictions
{% for c in contradictions %}
- {{ c.claim_a }} vs. {{ c.claim_b }} (severity: {{ c.severity }})
{% endfor %}
{% endif %}
{% endblock %}

{% block source %}
## Source Material
Type: {{ source_type }}
Title: {{ source_title }}
{% if source_type == 'transcript' %}
Speakers: {{ speakers | join(', ') }}
Duration: {{ duration }} minutes
{% endif %}

{{ source_content | truncate(max_tokens - 500) }}
{% endblock %}

{% block instruction %}
Generate a comprehensive wiki article with:
1. A clear title (H1)
2. An executive summary (2-3 paragraphs)
3. Key concepts with definitions (H2 sections)
4. Cross-links to related pages
5. Citations to source material
6. A confidence assessment
{% if maturity == 'seed' %}
7. Note: This is a seed article — mark as draft and flag for review
{% endif %}
{% endblock %}
```

### 2.3 Template Registry and Versioning

For Mnemosyne, prompts should be versioned in the vault alongside code, not hidden in application logic. A minimal registry:

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape
import hashlib
import json

@dataclass
class PromptVersion:
    version: int
    template_path: str
    description: str
    model_tier: str  # 'fast' or 'heavy'
    temperature: float = 0.7
    max_tokens: int = 4096
    is_active: bool = False

@dataclass
class PromptTemplate:
    template_id: str
    name: str
    required_variables: List[str]
    optional_variables: List[str] = field(default_factory=list)
    versions: List[PromptVersion] = field(default_factory=list)

class MnemosynePromptRegistry:
    def __init__(self, templates_dir: str):
        self.env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._templates: Dict[str, PromptTemplate] = {}
    
    def register(self, template: PromptTemplate):
        self._templates[template.template_id] = template
    
    def render(self, template_id: str, variables: dict, version: Optional[int] = None) -> dict:
        tpl = self._templates[template_id]
        
        # Select version
        if version is None:
            active = [v for v in tpl.versions if v.is_active]
            if not active:
                raise ValueError(f'No active version for {template_id}')
            version_obj = active[0]
        else:
            version_obj = next(v for v in tpl.versions if v.version == version)
        
        # Validate required variables
        missing = set(tpl.required_variables) - set(variables.keys())
        if missing:
            raise ValueError(f'Missing required variables: {missing}')
        
        # Render template
        jinja_tpl = self.env.get_template(version_obj.template_path)
        rendered = jinja_tpl.render(**variables)
        
        # Compute prompt hash for audit
        prompt_hash = hashlib.sha256(rendered.encode()).hexdigest()
        
        return {
            'prompt': rendered,
            'template_id': template_id,
            'version': version_obj.version,
            'model_tier': version_obj.model_tier,
            'temperature': version_obj.temperature,
            'max_tokens': version_obj.max_tokens,
            'prompt_hash': f'sha256:{prompt_hash}',
            'variables': {k: v for k, v in variables.items() if k in tpl.required_variables},
        }
```

### 2.4 Prompt Template File Layout

```
mnemosyne_py/prompts/
├── base_compile.j2          # Base template for article compilation
├── base_audit.j2            # Base template for adversarial review
├── base_extract.j2          # Base template for concept extraction
├── compile/
│   ├── notes_to_wiki.j2     # Personal notes -> wiki article
│   ├── paper_to_wiki.j2     # Academic paper -> wiki article
│   ├── transcript_to_wiki.j2 # Video/audio transcript -> wiki article
│   └── synthesis.j2         # Multi-source synthesis article
├── audit/
│   ├── structural_lint.j2   # Check markdown structure, links, citations
│   ├── contradiction_check.j2 # Detect contradictions with existing pages
│   └── adversarial_review.j2 # Red-team the article for errors
├── extract/
│   ├── concepts.j2          # Extract concepts from raw text
│   ├── links.j2             # Extract link opportunities
│   └── citations.j2         # Extract and format citations
└── registry.yaml            # Template metadata and versioning
```

---

## 3. Structured Output: The Compilation Engine's Core

### 3.1 Why Structured Output is Non-Negotiable

Mnemosyne's compilation engine produces typed artifacts that the Rust core stores in `state.db`. These are not free-form text blobs — they are structured objects with validation rules:

| Artifact | Pydantic Model | Stored In |
|---|---|---|
| **Wiki article** | `ArticleOutput` | `pages` table |
| **Concept extraction** | `ConceptExtraction` | `pages` + `links` tables |
| **Contradiction report** | `ContradictionReport` | `contradictions` table |
| **Audit score** | `AuditResult` | `audit_log` table |
| **Link graph update** | `LinkGraphUpdate` | `links` table |
| **Citation list** | `CitationList` | `pages.provenance` |

Raw string parsing is fragile. JSON mode helps but does not validate. The Python ecosystem has solved this with Pydantic-based libraries.

### 3.2 Instructor: The Default for Mnemosyne

**Instructor** is the most popular structured output library: 12K+ GitHub stars, 3M+ monthly PyPI downloads, 15+ provider integrations. It patches any OpenAI-compatible client and adds:

| Feature | Detail | Mnemosyne Use |
|---|---|---|
| **Schema validation** | Pydantic models enforce types, ranges, enums | Article structure, concept confidence scores |
| **Auto-retry** | On validation failure, sends errors back to LLM | Self-correcting extraction on malformed output |
| **Partial streaming** | `Partial[Model]` streams partially-filled objects | Real-time compilation progress for UI |
| **Multi-provider** | OpenAI, Anthropic, Gemini, Ollama, Mistral, etc. | Multi-provider fallback chain |
| **Mode selection** | JSON mode, Tools mode, Markdown mode | JSON mode for extraction, Tools mode for agentic tasks |
| **License** | MIT | Zero friction |

**Example: Article Compilation with Instructor**

```python
import instructor
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List, Optional

class Citation(BaseModel):
    source_id: str = Field(description='Stable source identifier')
    quote: str = Field(description='Verbatim quote from source')
    page_or_timestamp: Optional[str] = Field(description='Page number or timestamp')

class Section(BaseModel):
    heading: str = Field(description='Section heading (H2)')
    content: str = Field(description='Section body in markdown')
    citations: List[Citation] = Field(default_factory=list)

class ArticleOutput(BaseModel):
    title: str = Field(description='Article title (H1)')
    summary: str = Field(description='Executive summary (2-3 paragraphs)')
    sections: List[Section] = Field(description='Article sections')
    cross_links: List[str] = Field(description='Wikilink targets to related pages')
    confidence: float = Field(ge=0.0, le=1.0, description='Overall confidence')
    maturity: str = Field(description='seed | refining | established | disputed')
    contradictions_noted: List[str] = Field(default_factory=list, description='Noted contradictions')

# Patch the client
client = instructor.from_openai(
    OpenAI(base_url='http://localhost:11434/v1', api_key='ollama')
)

def compile_article(prompt: str, model: str = 'llama3.3:70b') -> ArticleOutput:
    return client.chat.completions.create(
        model=model,
        messages=[{'role': 'user', 'content': prompt}],
        response_model=ArticleOutput,
        max_retries=3,
        max_tokens=8192,
        temperature=0.7,
    )
```

### 3.3 Pydantic AI: The Agent Framework Alternative

**Pydantic AI** (16K+ GitHub stars, from the Pydantic team) is an agent framework where structured output is a built-in primitive. It offers:

| Feature | Detail | When to Use |
|---|---|---|
| **Agents** | Typed agents with system prompts, tools, result types | Multi-step compilation workflows |
| **Dependency injection** | Testable, mockable tool calls | Unit testing compilation logic |
| **Graph workflows** | Multi-agent graphs with state persistence | Complex audit pipelines |
| **Streaming** | Native async + structured streaming | Real-time compilation UI |
| **Observability** | Optional Logfire integration | Production monitoring |
| **License** | MIT | Zero friction |

**Mnemosyne Recommendation:** Use **Instructor** for the compilation engine's extraction tasks (concept extraction, contradiction detection, audit scoring) where the pattern is 'define model, get typed output.' Use **Pydantic AI** if/when Mnemosyne builds multi-step agentic workflows that need tool calling, dependency injection, and graph execution.

### 3.4 DSPy: Programmatic Prompt Optimization

**DSPy** (Stanford NLP) is a paradigm shift: instead of manually writing prompts, you define task signatures and let an optimizer generate and refine prompts against a metric. It is the right tool when prompts are part of a multi-step pipeline and you want systematic optimization rather than artisanal prompt engineering.

| Optimizer | What It Does | Best For |
|---|---|---|
| `BootstrapFewShot` | Synthesizes few-shot examples from training data | Entry-level optimization |
| `MIPROv2` | Optimizes instructions + few-shot examples jointly | Production RAG/agent pipelines |
| `COPRO` | Instruction-only optimization | When examples are scarce |
| `BootstrapFinetune` | Fine-tunes model weights on collected data | Maximum accuracy, cost-tolerant |

**When to use DSPy in Mnemosyne:**
- After Phase 1, when the compilation pipeline is stable and you have evaluation data
- For optimizing the contradiction detection prompt against a labeled dataset
- For tuning the adversarial review prompt to catch specific error patterns
- Not for Phase 1 — requires training data and metric definition upfront

---

## 4. Streaming Response Handling

### 4.1 Why Streaming Matters for Heavy Models

A 70B model generating 8K tokens at 30 tokens/second takes ~4.5 minutes. Without streaming, the user (or the Rust core) waits in silence. With streaming:
- **Progress visibility:** The satellite emits partial content as it generates
- **Timeout safety:** If generation stalls, the partial result is not lost
- **UI responsiveness:** The web UI can show 'Compiling...' with live preview
- **Early termination:** Stop if the output diverges from expected structure

### 4.2 Streaming Patterns

**Pattern A: Raw Token Streaming (for conversation layer)**

```python
async def stream_response(prompt: str, model: str):
    client = AsyncOpenAI(base_url='http://localhost:11434/v1', api_key='ollama')
    stream = await client.chat.completions.create(
        model=model,
        messages=[{'role': 'user', 'content': prompt}],
        stream=True,
        max_tokens=4096,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield json.dumps({
                'type': 'token',
                'content': delta.content,
                'finish_reason': chunk.choices[0].finish_reason,
            })
```

**Pattern B: Structured Streaming with Instructor (for compilation layer)**

```python
from instructor import Partial

def stream_compile(prompt: str, model: str):
    client = instructor.from_openai(
        OpenAI(base_url='http://localhost:11434/v1', api_key='ollama')
    )
    
    stream = client.chat.completions.create(
        model=model,
        messages=[{'role': 'user', 'content': prompt}],
        response_model=Partial[ArticleOutput],
        stream=True,
        max_tokens=8192,
    )
    
    for partial in stream:
        # partial is a partially-filled ArticleOutput
        yield json.dumps({
            'type': 'partial',
            'title': partial.title if hasattr(partial, 'title') else None,
            'section_count': len(partial.sections) if partial.sections else 0,
            'confidence': partial.confidence if hasattr(partial, 'confidence') else None,
        })
```

### 4.3 Python vs Rust Streaming Ergonomics

| Aspect | Python (`openai` SDK + `instructor`) | Rust (`reqwest` + `serde`) |
|---|---|---|
| **SSE parsing** | Built-in (`Stream` / `AsyncStream`) | Manual (`eventsource-client` or custom) |
| **JSON extraction** | Automatic per-chunk | Manual string buffering + `serde_json` |
| **Type validation** | Pydantic models per chunk | Manual struct matching |
| **Partial object streaming** | `Partial[Model]` — typed partials | Not available |
| **Error recovery** | Built-in retry + validation feedback | Manual retry logic |
| **Async ergonomics** | `async for` — native | `Stream` + `while let Some` — workable but verbose |
| **Code for 8K token stream** | ~10 lines | ~50+ lines |

The Python advantage is not speed — both languages can parse SSE at wire speed. The advantage is **developer velocity and reliability**: the Python ecosystem has already solved the edge cases (malformed chunks, mid-JSON splits, retry on parse failure, partial validation) that you would have to re-implement in Rust.

---

## 5. The Compilation Pipeline

### 5.1 Pipeline Stages

```
Raw Source (notes, PDF, transcript, web)
    |
    v
[Stage 1: Fast Extract]  <- 30B MoE model
    - Extract concepts, entities, key claims
    - Identify link opportunities
    - Score source reliability
    |
    v
[Stage 2: Heavy Compile]  <- 70B MoE model
    - Generate structured article (Instructor -> ArticleOutput)
    - Write cross-linked markdown with citations
    - Assess confidence and maturity
    |
    v
[Stage 3: Audit]  <- 70B MoE model
    - Structural lint (markdown validity, link syntax)
    - Contradiction detection vs. existing pages
    - Adversarial review (red-team for errors)
    - Output: AuditResult with score, issues, recommendations
    |
    v
[Stage 4: Publish or Reject]
    - Score >= threshold: promote to wiki/
    - Score < threshold: return to drafts/ with feedback
    - Human approval gate (if configured)
```

### 5.2 Satellite CLI Contract for Compilation

```bash
# Stage 1: Fast extraction
python -m mnemosyne_py.compile extract \
    --source-file /tmp/raw.json \
    --template extract/concepts \
    --model-tier fast \
    --output /tmp/concepts.json

# Stage 2: Heavy compilation
python -m mnemosyne_py.compile compile \
    --source-file /tmp/raw.json \
    --concepts-file /tmp/concepts.json \
    --template compile/notes_to_wiki \
    --model-tier heavy \
    --output /tmp/article.json

# Stage 3: Audit
python -m mnemosyne_py.compile audit \
    --article-file /tmp/article.json \
    --template audit/adversarial_review \
    --model-tier heavy \
    --output /tmp/audit.json

# Stage 4: Publish (Rust core handles this, but satellite can prepare)
python -m mnemosyne_py.compile finalize \
    --article-file /tmp/article.json \
    --audit-file /tmp/audit.json \
    --output /tmp/final.json
```

---

## 6. Response Parsing and Post-Processing

### 6.1 Markdown Normalization

LLMs are inconsistent with markdown formatting. The satellite normalizes:

```python
import re

def normalize_markdown(text: str) -> str:
    # Normalize heading levels (ensure single # for H1, etc.)
    text = re.sub(r'^#{2,}\s+(.+)$', lambda m: f'## {m.group(1)}', text, flags=re.MULTILINE)
    
    # Ensure wikilinks use [[Page Name]] format
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'[[\1]]', text)
    
    # Normalize citation markers
    text = re.sub(r'\(cite:\s*([^)]+)\)', r'[[cite:\1]]', text)
    
    # Remove excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()
```

### 6.2 Link Graph Extraction

```python
import re
from typing import List, Tuple

def extract_wikilinks(text: str) -> List[Tuple[str, int, int]]:
    # Returns: [(target, line_start, line_end), ...]
    links = []
    for match in re.finditer(r'\[\[([^\]]+)\]\]', text):
        # Calculate line numbers
        line_start = text[:match.start()].count('\n') + 1
        line_end = text[:match.end()].count('\n') + 1
        links.append((match.group(1), line_start, line_end))
    return links
```

### 6.3 Contradiction Detection Prompt

```python
from pydantic import BaseModel, Field
from typing import List

class Contradiction(BaseModel):
    claim_a: str = Field(description='First conflicting claim')
    claim_b: str = Field(description='Second conflicting claim')
    severity: str = Field(description='low | medium | high | critical')
    resolution: str = Field(description='Suggested resolution or note')

class ContradictionReport(BaseModel):
    contradictions: List[Contradiction] = Field(default_factory=list)
    overall_assessment: str = Field(description='Summary of contradiction analysis')
    confidence: float = Field(ge=0.0, le=1.0)

def detect_contradictions(new_article: str, existing_pages: List[str]) -> ContradictionReport:
    prompt = f"""
Compare the following new article against existing pages in the knowledge base.
Identify any contradictions, conflicts, or inconsistencies.

New Article:
{new_article}

Existing Pages:
{'\n\n---\n\n'.join(existing_pages)}
"""
    
    client = instructor.from_openai(
        OpenAI(base_url='http://localhost:11434/v1', api_key='ollama')
    )
    
    return client.chat.completions.create(
        model='llama3.3:70b',
        messages=[{'role': 'user', 'content': prompt}],
        response_model=ContradictionReport,
        max_retries=3,
    )
```

---

## 7. Provenance and Audit Integration

### 7.1 Compilation Audit Log

Every compilation stage logs to the `audit_log` table:

```json
{
  "id": "audit-uuid",
  "job_id": "compile-job-uuid",
  "timestamp": "2026-05-27T10:00:00Z",
  "stage": "heavy_compile",
  "model": "llama3.3:70b",
  "provider": "ollama",
  "host": "http://localhost:11434",
  "template_id": "compile/notes_to_wiki",
  "template_version": 3,
  "prompt_hash": "sha256:abc123...",
  "response_hash": "sha256:def456...",
  "prompt_tokens": 2048,
  "completion_tokens": 4096,
  "total_tokens": 6144,
  "latency_ms": 180000,
  "cost_estimate_usd": 0.0,
  "structured": true,
  "schema_name": "ArticleOutput",
  "validation_passed": true,
  "retries": 1,
  "output_maturity": "seed",
  "output_confidence": 0.85,
  "error": null
}
```

### 7.2 Content Hashing for Hand-Edit Protection

The `pages` table's `content_hash` field protects hand-edited wiki pages from being overwritten by recompilation:

```python
import hashlib

def compute_content_hash(content: str) -> str:
    return 'sha256:' + hashlib.sha256(content.encode('utf-8')).hexdigest()

def should_recompile(page: dict, new_content: str) -> bool:
    current_hash = page.get('content_hash')
    new_hash = compute_content_hash(new_content)
    if current_hash == new_hash:
        return False  # Content unchanged
    if page.get('stage') == 'published' and page.get('approved_at'):
        # Hand-edited published page — require explicit approval to overwrite
        return False
    return True
```

---

## 8. Licensing & Compliance

| Component | License | Mnemosyne Impact |
|---|---|---|
| `openai` Python SDK | Apache-2.0 | Zero friction |
| `ollama` Python SDK | MIT | Zero friction |
| `instructor` | MIT | Zero friction |
| `pydantic-ai` | MIT | Zero friction |
| `pydantic` | MIT | Zero friction |
| `jinja2` | BSD-3-Clause | Zero friction |
| `dspy` | Apache-2.0 | Zero friction |
| `tiktoken` | MIT | Zero friction |

**All compilation stack components are permissively licensed.** No AGPL concerns.

---

## 9. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Template drift (accumulated conditionals) | Medium | Medium | Regular template audits; limit nesting depth; version control |
| Structured output validation fails repeatedly | Low | High | Max 3 retries; fallback to plain text with manual parsing flag |
| LLM hallucinates citations | Medium | High | Validate citation source_ids against `state.db`; flag unverified |
| Contradiction detection misses subtle conflicts | Medium | Medium | Multi-pass audit; human review gate for high-severity claims |
| Compilation timeout on very long sources | Medium | Medium | Token budget enforcement; chunk long sources; parallel extraction |
| Prompt injection in source content | Medium | High | Structural isolation (source in user message, instructions in system); input sanitization |
| Model version drift (Ollama tag updates) | Medium | Medium | Pin model tags in config; test compilation on model updates |
| Python satellite startup latency | Low | Low | Warm pool or long-running daemon |

---

## 10. Decision Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-27 | Python satellite for all heavy LLM compilation | Rust lacks prompt template, structured output, and optimization ecosystems |
| 2026-05-27 | Jinja2 as prompt templating engine | Standard Python templating; conditional logic, loops, filters, inheritance |
| 2026-05-27 | Template registry in vault (YAML + Jinja2 files) | Version control alongside code; audit trail; A/B testing capability |
| 2026-05-27 | Instructor as structured output default | Best ecosystem, auto-retry, partial streaming, 15+ providers, MIT license |
| 2026-05-27 | Pydantic AI for future agent workflows | Agent framework with typed tools, dependency injection, graph support |
| 2026-05-27 | DSPy for Phase 2+ prompt optimization | Requires training data and metrics; not needed for MVP |
| 2026-05-27 | Streaming for all heavy compilation tasks | Progress visibility, timeout safety, UI responsiveness |
| 2026-05-27 | Content hash for hand-edit protection | Prevents accidental overwrite of approved/published pages |
| 2026-05-27 | Multi-stage pipeline: extract -> compile -> audit -> publish | Separation of concerns; retry per stage; incremental processing |

---

## 11. Open Questions

1. **Should compilation prompts be editable by non-programmers?** A web UI for prompt editing would empower domain experts but risks template drift.
2. **How do we handle model-specific prompt tuning?** `llama3.3:70b` and `qwen2.5:32b` may respond differently to the same prompt. Do we maintain per-model template variants?
3. **Should the satellite cache compilation results?** Identical source + template + model could return cached output. TTL? Invalidation strategy?
4. **Contradiction resolution workflow:** When contradictions are detected, should the satellite auto-recompile with contradiction context, or flag for human review?
5. **Batch compilation efficiency:** Should multiple small sources be batched into a single LLM call for extraction, or kept separate for provenance?
6. **Fine-tuning vs. prompt optimization:** At what scale does fine-tuning a local model on Mnemosyne's output become more efficient than DSPy prompt optimization?

---

## 12. References

- [Instructor Documentation](https://python.useinstructor.com/) — Structured output library
- [Pydantic AI Documentation](https://ai.pydantic.dev/) — Agent framework
- [Pydantic AI GitHub](https://github.com/pydantic/pydantic-ai) — Source code (16K+ stars)
- [DSPy Documentation](https://dspy.ai/) — Programmatic prompt optimization
- [DSPy GitHub](https://github.com/stanfordnlp/dspy) — Stanford NLP framework
- [Jinja2 Documentation](https://jinja.palletsprojects.com/) — Templating engine
- [Prompt Template Guide 2026](https://123ofai.com/qnalab/system-design/blocks/prompt-template) — Production prompt systems
- [Top 5 Prompt Engineering Tools 2026](https://www.getmaxim.ai/articles/top-5-prompt-engineering-tools-in-2026-2/) — Framework comparison
- [8 Best Structured Output Libraries 2026](https://techsy.io/en/blog/best-llm-structured-output-libraries) — Ranked comparison
- [Instructor vs Pydantic AI](https://www.respan.ai/market-map/compare/instructor-vs-pydantic-ai) — Feature comparison
- [Prompt Optimization with DSPy](https://haystack.deepset.ai/cookbook/prompt_optimization_with_dspy) — Haystack integration tutorial