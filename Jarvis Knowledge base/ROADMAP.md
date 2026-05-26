# Roadmap

## Phase 0: Specification (Current)
- [x] Define data models and SQLite schema
- [x] Define API contracts (MCP, REST, CLI)
- [x] Validate problem with working glue prototype (`experiments/v0-glue/`)
- [x] Identify schema, concurrency, and API mismatches from real integration attempt
- [ ] Community review of architecture
- [ ] Reference implementation of `state.db` schema in Python

## Phase 1: Core Engine (MVP)
- [ ] SQLite schema + migration system
- [ ] Vault directory layout + `init` command
- [ ] Markdown ingestion + raw page creation
- [ ] Two-tier compilation engine (fast extract → heavy write)
- [ ] Basic MCP server with `kb_search` and `kb_ask`

## Phase 2: Quality & Scale
- [ ] PDF/DOCX ingestion (pluggable extractors)
- [ ] Audit engine: lint, contradiction detection, adversarial review
- [ ] Job queue with Ollama priority scheduling
- [ ] Pack export system

## Phase 3: Agent-Native Features
- [ ] Conversation history + context budgets
- [ ] Memory lifecycle: propose → inbox → remember
- [ ] Graph context retrieval
- [ ] REST API layer
- [ ] Obsidian plugin compatibility layer

## Phase 4: Ecosystem
- [ ] Import adapters from Synto, Synthadoc, LLM-WIKI-MCP, Link
- [ ] Multi-node sync (Foundry → Frontline)
- [ ] Web UI for review and graph visualization
