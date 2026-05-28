mnemosyne/                    # or jarvis-kb-os, omniscience, cortex-mem
├── README.md                 # The pitch — why this must exist
├── MOTIVATION.md             # The pain — screenshots of the 4-repo glue hell
├── ARCHITECTURE.md           # The blueprint — the 7-layer design
├── SPECIFICATION.md          # The contract — data models, APIs, file formats
├── ROADMAP.md                # How to get there without boiling the ocean
├── COMPARISON.md             # How existing tools map to this (Synto, Synthadoc, etc.)
├── CONTRIBUTING.md           # What skills you are looking for
├── LICENSE                   # CC-BY-SA 4.0 for the spec (or MIT if you prefer)
└── assets/
    ├── diagram-overview.png  # (You can draw this in Excalidraw or tldraw)
    └── diagram-layers.png

# Architecture

## The 7 Layers

### Layer 0: The Vault
A single directory structure with namespaces for content origin and lifecycle stage.
~/jarvis-kb/
├── config.yaml
├── state.db                 # unified SQLite
├── raw/                     # immutable sources
│   ├── self/                # personal notes
│   └── world/               # external documents
├── wiki/
│   ├── .drafts/             # compiled, awaiting approval
│   ├── self/                # published personal knowledge
│   ├── world/               # published external knowledge
│   └── synthesis/           # LLM-generated answers, cited
├── memory/
│   ├── inbox/               # proposed memories
│   └── committed/           # approved, linked to graph
└── packs/                   # agent-ready exports


### Layer 1: Unified Schema (SQLite)
Six logical tables replace four separate databases:

- `pages` — every markdown page, regardless of source or stage
- `links` — graph edges (wikilinks, citations, semantic, memory)
- `jobs` — priority queue for all LLM work (ingest, compile, lint, query)
- `conversations` — ask history with token budgets
- `audit_log` — every LLM call, cost, latency, hash
- `contradictions` — flagged conflicts between sources

### Layer 2: Ingestion Engine
Pluggable extractors for `.md`, `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.html`, video/audio.
Each extractor returns a normalized `RawDocument` with heading-aware segments.
A fast LLM (4B–8B) extracts concepts and schedules compile jobs.

### Layer 3: Compilation Engine
Two-tier LLM pipeline (Synto-style):
- **Fast model**: extracts concepts, relationships, summaries
- **Heavy model**: writes cross-linked articles
Features: incremental compilation, hand-edit protection, rejection feedback loops, A/B comparison.

### Layer 4: Audit Engine
Three-pass quality gate (Synthadoc-style):
1. Structural lint (orphans, missing targets)
2. Contradiction detection (blocking vs. warning)
3. Adversarial review (devil's advocate critique)

### Layer 5: Publish Engine
Atomic promotion from `.drafts/` to `wiki/`.
Rebuilds search index, graph, and agent packs in one transaction.

### Layer 6: Query & Conversation Engine
- Hybrid search: BM25 + optional vector re-ranking
- Context budget enforcement: configurable `context_budget`, `history_budget`, `source_budget`
- Graph context retrieval: page + inbound/outbound neighbors (Link-style)
- Memory lifecycle: `propose` → `inbox` → `remember` → `committed`

### Layer 7: API Surface
One server, three interfaces:
- **MCP**: `kb_search`, `kb_ask`, `kb_ingest`, `kb_remember`, `kb_compile`, `kb_audit`
- **REST**: `/api/ingest`, `/api/query`, `/api/remember`, `/api/graph`, `/api/audit`
- **CLI**: `jarvis-kb init|ingest|compile|query|audit|serve`

## Concurrency Model
A priority job queue prevents Ollama deadlock:
1. Chat queries (interactive, latency-sensitive)
2. Compilation (batch, GPU-heavy)
3. Lint/Audit (background, deferrable)

## Diagrams

### System Overview
![System Overview](assets/diagram-overview.png)
*Agents as clients of the OS — three interfaces (MCP, REST, CLI), five agent types, one vault, one schema.*

### 7-Layer Architecture
![7-Layer Architecture](assets/diagram-layers.png)
*Vertical stack from Vault (Layer 0) to API Surface (Layer 7). Data flows upward for queries and downward for ingestion/compilation. Agents interact only at Layer 7.*

### Content Lifecycle
![Content Lifecycle](assets/diagram-content-lifecycle.png)
*The "happy path" of a raw source through Mnemosyne: ingest → compile → audit → publish → query. Rejected drafts loop back for recompilation. Every stage is logged to `audit_log`.*

### Unified Schema
![Unified Schema](assets/diagram-schema-erd.png)
*Six logical tables in `state.db` replacing four separate databases. Foreign keys link `links` and `contradictions` to `pages`, and `audit_log` to `jobs`.*

### Agent Memory Lifecycle
![Agent Memory Lifecycle](assets/diagram-memory-lifecycle.png)
*From agent proposal (`kb_remember`) to committed knowledge: `propose` → `inbox/` → `audit` → `committed/` → `archived/`. Human approval gates at inbox and commit stages. Auto-approve is configurable per namespace.*
