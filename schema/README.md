# Mnemosyne Schema

This directory contains the database schema migrations for Mnemosyne's unified SQLite database (`state.db`).

## Philosophy

One `state.db` replaces four separate databases (Synto + Synthadoc + LLM-WIKI-MCP + Link). Six logical tables handle all knowledge lifecycle stages.

## Migration Naming

```
NNN-description.sql
```

- `001-init.sql` — Initial schema creation
- `002-fts-index.sql` — Full-text search indexing (future)
- `003-vector-extension.sql` — Vector embedding support (future)

## Applying Migrations

```bash
# Create or update state.db
sqlite3 ~/jarvis-kb/state.db < schema/001-init.sql
```

## Schema Overview

| Table | Purpose | Replaces |
|-------|---------|----------|
| `pages` | Every markdown page, all stages | Synto wiki + Synthadoc sources |
| `links` | Graph edges (wikilinks, citations, semantic) | Link graph edges |
| `jobs` | Priority queue for all LLM work | Ad-hoc scheduling |
| `conversations` | Query history with token budgets | LLM-WIKI-MCP history |
| `audit_log` | Every LLM call, cost, latency | Synthadoc audit trail |
| `contradictions` | Flagged conflicts between sources | Manual conflict tracking |

## Views

- `v_published_pages` — Agent-consumable knowledge
- `v_pending_jobs` — Next work for the job queue
- `v_open_contradictions` — Unresolved conflicts needing human attention
- `v_audit_summary` — Cost and latency rollup by operation

## Indexes

All foreign keys are indexed. Additional indexes cover:
- Namespace + stage queries (common for vault browsing)
- Job status + priority (queue worker lookups)
- Session ID + timestamp (conversation history)
- Audit operation + timestamp (cost reporting)
