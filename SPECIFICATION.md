> **Canonical Specification — v0.1+ (Current)**
> This document is the maintained technical specification for Mnemosyne's current architecture.
> For future integration roadmaps (epistemic governance, agent hooks, conversation memory, DKG),
> see `MNEMOSYNE_SPEC_v0.2.md` (draft for review).
> For the original v0.1 architecture, see `MNEMOSYNE_SPEC_v0.1.md` (superseded).

---

pack/
├── articles/          # symlink or copy of wiki/*.md
├── index/
│   └── INDEX.json     # machine-readable: {id, title, path, namespace, maturity}
├── graph/
│   └── links.json     # adjacency list for agent traversal
├── audit/
│   └── audit.jsonl    # recent audit entries
└── AGENTS.md          # human-readable entrypoint



# Technical Specification

## 1. Data Model: `pages` Table

| Column | Type | Description |
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
| `write_guard` | TEXT | `open`, `protected`, `frozen` — see §6 |

## 2. Wikilink Resolution
- Format: `[[Concept Name]]`
- Resolution order:
  1. Exact title match in same namespace
  2. Exact title match in `self/` namespace
  3. Alias match from `links` table
  4. Create stub page with `maturity: seed` if `auto_stub: true`

## 3. Job Queue Priorities

| Priority | Job Type | Max Concurrent | Preemptible |
|---|---|---|---|
| 1 | `query` | 2 | Yes |
| 2 | `compile` | 1 | No |
| 3 | `lint`, `audit`, `ingest` | 2 | No |

## 4. MCP Tool Schema

### `kb_search`
```json
{
  "query": "string",
  "source": ["all", "self", "world"],
  "top_k": 5
}
```

### `kb_ask`
```json
{
  "question": "string",
  "session_id": "string (optional)",
  "context_budget": 24000,
  "history_budget": 3000
}
```

### `kb_ingest`
```json
{
  "path": "/abs/path/to/file",
  "doc_type": "auto | notes | paper | textbook | api_docs | transcript"
}
```

### `kb_remember`
```json
{
  "content": "string",
  "tags": ["string"],
  "project": "string (default: default)"
}
```

### `kb_compile`
```json
{
  "scope": ["all", "self", "world"],
  "auto_approve": false
}
```

### `kb_audit`
```json
{
  "scope": ["all", "self", "world"]
}
```

## 5. REST Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/ingest` | Ingest a file, return job ID |
| POST | `/api/query` | Ask a question, return synthesis |
| POST | `/api/remember` | Propose a memory |
| GET | `/api/graph` | Return adjacency list for a page |
| GET | `/api/audit` | Return recent audit entries |
| GET | `/api/jobs/{id}` | Check job status and result |
| POST | `/api/approve` | Approve a draft for publication |

## 6. Schema Additions (Phase 2 — Approved)

The following additions from v0.2 draft are approved for Phase 2 implementation:

### 6.1 Write Guards (`pages.write_guard`)

Extends `content_hash` protection with agent-access policy:

- `open`: any agent can write (default for new pages)
- `protected`: agent can write only if `content_hash` matches expected (prevents overwrites of compiled content)
- `frozen`: only human can write (hand-edit protection)

### 6.2 Receipts Table

Observability for the jobs queue — every dispatched job creates a receipt:

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | Stable UUID |
| `job_id` | TEXT FK | → `jobs.id` |
| `agent_id` | TEXT | Agent or user that submitted the intent |
| `intent` | TEXT | `ingest`, `compile`, `audit`, `publish` |
| `route` | TEXT | Which satellite/tool was invoked |
| `dispatch_at` | TEXT | ISO timestamp |
| `completion_at` | TEXT | ISO timestamp |
| `status` | TEXT | `dispatched`, `running`, `succeeded`, `failed`, `timeout` |
| `artifacts` | TEXT | JSON: `{output_files, hashes, metrics}` |
| `phase_log` | TEXT | JSON: `[{phase, timestamp, duration_ms, status}]` |

### 6.3 Conversation Memory Tiers

Extended `conversations` table for heat-decay retention:

| Column | Type | Description |
|---|---|---|
| `tier` | TEXT | `short` (7 turns), `mid` (heat-decay), `long` (committed memory) |
| `heat_score` | REAL | 0.0–1.0, updated on each reference |
| `last_referenced_at` | TEXT | ISO timestamp |
| `decay_rate` | REAL | Per-day decay (default 0.1) |
| `promoted_to_memory_id` | TEXT FK | → `pages.id` if promoted to `memory/committed/` |

### 6.4 User Profiles Table

Implicit facts extracted from conversations by the fast model:

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | Stable UUID |
| `key` | TEXT | `job_title`, `location`, `interest`, etc. |
| `value` | TEXT | Extracted value |
| `confidence` | REAL | 0.0–1.0 |
| `source_conversation_ids` | TEXT | JSON: `[conversation_id, ...]` |
| `extracted_at` | TEXT | ISO timestamp |
| `last_verified_at` | TEXT | ISO timestamp |
| `status` | TEXT | `active`, `stale`, `superseded` |

## 7. Document Versioning

| Spec Version | Status | File |
|---|---|---|
| v0.1 | Superseded | `MNEMOSYNE_SPEC_v0.1.md` |
| v0.1+ (current) | **Canonical** | `SPECIFICATION.md` (this file) |
| v0.2 | Draft for review | `MNEMOSYNE_SPEC_v0.2.md` |

---

*This specification is maintained. Open an issue for schema changes or API additions.*
