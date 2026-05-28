# MNEMOSYNE SPEC — v0.1
## Architecture Baseline: Local-First Semantic Memory OS
**Date:** 2026-05-27 | **Status:** Frozen Baseline | **Next:** v0.2 (Integration Roadmap)

---

## 1. Project Identity

| Field | Value |
|---|---|
| **Name** | Mnemosyne / Jarvis Knowledge OS |
| **Repo** | https://github.com/noirblue/IsaacCLupus_mnemosyn_spec |
| **Purpose** | Unified, local-first semantic memory operating system for autonomous agents |
| **Tagline** | One vault. One schema. One API. No glue. |
| **Maintainer** | Non-programmer systems thinker; conceptual architect |
| **Status** | Concept / Architecture Proposal — seeking core contributors for Phase 1 implementation |
| **Named in memory of** | Isaac |

---

## 2. Core Problem

Building a Jarvis-like agent in 2026 requires stitching together four incompatible local-first knowledge tools:

| Tool | Role | Pain Point |
|---|---|---|
| **Synto** | Compile raw notes into structured wiki | Own vault layout, SQLite schema |
| **Synthadoc** | Ingest PDFs/videos/web with audit trails | Own vault layout, SQLite schema |
| **LLM-WIKI-MCP** | Conversational context + token budgets | Own vault layout, SQLite schema |
| **Link** | Agent memory lifecycle + graph context | Own vault layout, SQLite schema |

**Integration tax:** 4 vaults, 4 schemas, Ollama GPU deadlock, wikilink collisions, frontmatter drift, MCP namespace explosions. A 450-line Python glue layer was built and validated the problem — glue is insufficient. Unification at the architecture layer is required.

---

## 3. The Vision

A single knowledge OS treating memory as a **lifecycle**, not a file pile:

```
INGEST → COMPILE → AUDIT → PUBLISH → QUERY → REMEMBER → (loop)
```

One repository. One `config.yaml`. One SQLite `state.db` with six logical tables. Pluggable backends, unified frontend.

---

## 4. Core Principles

1. **Local-first** — knowledge never leaves your machine unless explicitly exported
2. **Schema-unified** — one `state.db` for pages, links, jobs, conversations, audit, contradictions
3. **Agent-native** — MCP + REST + CLI from day one, not bolted on later
4. **Human-in-the-loop** — drafts require approval, hand-edits protected, audits automatic
5. **Incremental** — change one note, recompile only what changed
6. **Provenance-first** — every claim carries citation, every LLM call carries cost log

---

## 5. 7-Layer Architecture

| Layer | Name | Function |
|---|---|---|
| 0 | **The Vault** | Single directory structure: `raw/`, `wiki/`, `memory/`, `packs/` |
| 1 | **Unified Schema** | SQLite: `pages`, `links`, `jobs`, `conversations`, `audit_log`, `contradictions` |
| 2 | **Ingestion Engine** | Pluggable extractors (.md, .pdf, .docx, .pptx, .xlsx, video, audio) |
| 3 | **Compilation Engine** | Two-tier LLM: fast model extracts concepts, heavy model writes cross-linked articles |
| 4 | **Audit Engine** | Three-pass: structural lint → contradiction detection → adversarial review |
| 5 | **Publish Engine** | Atomic promotion `.drafts/` → `wiki/`; rebuilds index, graph, agent packs |
| 6 | **Query & Conversation** | Hybrid BM25+vector search, context budgets, graph context, memory lifecycle |
| 7 | **API Surface** | MCP (`kb_search`, `kb_ask`, `kb_ingest`, `kb_remember`, `kb_compile`, `kb_audit`), REST, CLI |

---

## 6. Unified Schema (SQLite)

### 6.1 `pages` Table

| Column | Type | Purpose |
|---|---|---|
| `id` | TEXT PK | Stable UUID |
| `path` | TEXT UNIQUE | Vault-relative path |
| `namespace` | TEXT | `self`, `world`, `synthesis`, `memory` |
| `stage` | TEXT | `raw`, `draft`, `published`, `archived` |
| `title` | TEXT | Human-readable |
| `content_hash` | TEXT | SHA-256 for hand-edit protection |
| `maturity` | TEXT | `seed`, `refining`, `established`, `disputed` |
| `confidence` | REAL | 0.0–1.0 |
| `source_type` | TEXT | `notes`, `paper`, `textbook`, `api_docs`, `transcript` |
| `provenance` | TEXT | JSON: `[{source_file, line_start, line_end, extractor}]` |
| `compiled_by` | TEXT | Model name |
| `approved_at` | TEXT | ISO timestamp or null |
| `rejected_count` | INTEGER | Accumulated rejections |
| `rejection_feedback` | TEXT | Prompt injection for recompile |

### 6.2 Other Tables

- `links` — graph edges (`wikilink`, `citation`, `semantic`, `memory`)
- `jobs` — priority queue (`query`=1, `compile`=2, `lint/audit/ingest`=3)
- `conversations` — ask history with token budgets
- `audit_log` — every LLM call: cost, latency, hash
- `contradictions` — flagged conflicts between sources

---

## 7. Vault Directory Layout

```
~/jarvis-kb/
├── config.yaml              # unified configuration
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
    └── latest/
```

---

## 8. Implementation Strategy: Rust Core + Python Satellites

| Component | Language | Rationale |
|---|---|---|
| Core engine (schema, job queue, graph, API) | **Rust** | Memory safety, Tokio async, type-safe APIs, single binary |
| Document extractors (PDF, DOCX, video) | **Python** | Mature libraries: `pymupdf`, `python-docx`, Whisper, yt-dlp |
| LLM client glue | Rust or Python | HTTP to Ollama; Rust `reqwest` is sufficient |
| CLI | **Rust** | `clap` + `serde`, compiles to single binary |

**Communication:** Rust spawns Python subprocesses for extraction:
```bash
python -m mnemosyne_py.extract pdf file.pdf --output json
```
Python returns JSON `RawDocument` via stdout. Rust ingests into `state.db`.

---

## 9. Dual-Node Deployment (Optional)

| | **Node A: Foundry** | **Node B: Frontline** |
|---|---|---|
| Role | Ingest, compile, audit, validate | Serve, converse, remember, act |
| Workload | Batch, bursty, GPU-hungry | Interactive, latency-sensitive, always-on |
| Models | Heavy compilation (70B–235B MoE) | Conversational (30B MoE) |
| Ollama | `:11434` | `:11435` |
| Tools | Synto compile, Synthadoc ingest+lint, Link validate | LLM-WIKI-MCP serve, Link MCP, Jarvis orchestrator |
| State | "Dirty" drafts, audit logs, raw sources | "Published" approved articles, stable graph |

**Sync:** Git for markdown wikis + Synto packs; rsync for SQLite state. Publish pipeline is the only write window on Frontline.

**Hardware target:** Strix Halo + Ryzen AI Max+ 395, 128 GB unified LPDDR5X. Supports 70B models locally. ROCm for RDNA 3.5 may need vLLM/SGLang fallback.

---

## 10. Roadmap

### Phase 0: Specification (Current)
- [x] Define data models and SQLite schema
- [x] Define API contracts (MCP, REST, CLI)
- [x] Validate problem with working glue prototype (`prior-art/v0-glue/`)
- [x] Identify schema, concurrency, API mismatches from real integration
- [ ] Community review of architecture
- [ ] Reference implementation of `state.db` schema in Python or Rust

### Phase 1: Core Engine (MVP)
- [ ] SQLite schema + migration system
- [ ] Vault directory layout + `init` command
- [ ] Markdown ingestion + raw page creation
- [ ] Two-tier compilation engine (fast extract → heavy write)
- [ ] Basic MCP server with `kb_search` and `kb_ask`

### Phase 2: Quality & Scale
- [ ] PDF/DOCX ingestion (pluggable extractors)
- [ ] Audit engine: lint, contradiction detection, adversarial review
- [ ] Job queue with Ollama priority scheduling
- [ ] Pack export system

### Phase 3: Agent-Native Features
- [ ] Conversation history + context budgets
- [ ] Memory lifecycle: propose → inbox → remember
- [ ] Graph context retrieval
- [ ] REST API layer
- [ ] Obsidian plugin compatibility layer

### Phase 4: Ecosystem
- [ ] Import adapters from Synto, Synthadoc, LLM-WIKI-MCP, Link
- [ ] Multi-node sync (Foundry → Frontline)
- [ ] Web UI for review and graph visualization

---

## 11. Key Decisions Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-22 | Spec-first approach | Integration glue proved insufficient; architecture layer needed |
| 2026-05-22 | CC-BY-SA 4.0 for spec, MIT for future code | Protects architecture documents; welcomes code contributions |
| 2026-05-22 | Include v0 glue in `prior-art/` | Proves problem was validated through real attempt, not armchair theory |
| 2026-05-23 | Repo named `mnemosyne-spec` | In memory of Isaac; "spec" signals architecture-first status |
| 2026-05-24 | Rust core + Python satellites | Rust for performance/safety where it matters; Python for document extraction ecosystem |
| 2026-05-24 | Dual-node Foundry/Frontline optional | Latency isolation for production deployments; single-node works for hobbyists |
| 2026-05-27 | v0.1 spec published | Frozen baseline for architecture |

---

## 12. References

- Session Brief: `MNEMOSYNE_SESSION_BRIEF.md` (living reference for continuity)
- Architecture Deep-Dive: `ARCHITECTURE.md`
- Motivation: `MOTIVATION.md` (Why glue is not good enough)
- Comparison Matrix: `COMPARISON.md` (Feature matrix vs Synto/Synthadoc/LLM-WIKI-MCP/Link)
- Contributing: `CONTRIBUTING.md` (Skills needed, how to contribute)
- Roadmap: `ROADMAP.md` (Phase 0–4 timeline)
- v0 Glue Experiment: `prior-art/v0-glue/` (Working Python integration layer)

---

*This document is frozen as the v0.1 baseline. For the integration roadmap, see `MNEMOSYNE_SPEC_v0.2.md`.*