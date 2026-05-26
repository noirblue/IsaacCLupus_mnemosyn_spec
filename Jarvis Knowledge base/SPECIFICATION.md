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

## kb_ask

**JSON**

{
  "question": "string",
  "session_id": "string (optional)",
  "context_budget": 24000,
  "history_budget": 3000
}

## kb_ingest

**JSON**

{
  "path": "/abs/path/to/file",
  "doc_type": "auto | notes | paper | textbook | api_docs | transcript"
}

## kb_remember

**JSON**

{
  "content": "string",
  "tags": ["string"],
  "project": "string (default: default)"
}

## kb_compile

**JSON**

{
  "scope": ["all", "self", "world"],
  "auto_approve": false
}

## kb_audit

**JSON**

{
  "scope": ["all", "self", "world"]
}
