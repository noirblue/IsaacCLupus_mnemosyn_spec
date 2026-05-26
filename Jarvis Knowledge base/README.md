# Mnemosyne / Jarvis Knowledge OS

&gt; A unified, local-first semantic memory operating system for autonomous agents.
&gt; One vault. One schema. One API. No glue.

## About This Project

I am not a programmer. I am someone who spent weeks trying to make four excellent local-first knowledge tools — **Synto**, **Synthadoc**, **LLM-WIKI-MCP**, and **Link** — work together for a personal Jarvis setup, and failed. The integration tax was higher than the value of the tools themselves.

I wrote the glue code. I ran the proxy. I normalized the schemas. I debugged Ollama deadlocks and SQLite lock collisions across four different vault layouts. And I realized the problem wasn't my integration skills — it was that no one had designed the system layer these tools deserve.

This repository is that design.

If you are a developer who has also felt this friction, you are the target contributor. This spec is the blueprint; the code is what we build together.

## The Problem

Building a Jarvis-like agent in 2026 requires stitching together four incompatible tools:

- **Synto** to compile raw notes into a structured wiki
- **Synthadoc** to ingest PDFs, videos, and web articles with audit trails
- **LLM-WIKI-MCP** to maintain conversational context and token budgets
- **Link** to manage agent memory lifecycles and graph context

Each is brilliant alone. Together, they are a **full-time integration job**:
- Four different vault layouts
- Four different SQLite schemas
- Ollama contention and GPU deadlock
- Wikilink collisions and frontmatter drift
- MCP namespace explosions requiring custom proxy layers

We are building the airplane while flying it. This fragmentation will not solve itself.

## The Vision

A single, local-first knowledge OS that treats memory as a **lifecycle**, not a file pile:


One repository. One configuration file. One SQLite database with six logical tables.
Pluggable backends, but a unified frontend for the agent.

## Core Principles

1. **Local-first**: Your knowledge never leaves your machine unless you explicitly export it.
2. **Schema-unified**: One `state.db` for pages, links, jobs, conversations, audit, and contradictions.
3. **Agent-native**: Built for MCP, REST, and CLI from day one — not bolted on later.
4. **Human-in-the-loop**: Drafts require approval. Hand-edits are protected. Audits are automatic.
5. **Incremental**: Change one note, recompile only what changed. No full rebuilds.
6. **Provenance-first**: Every claim carries a citation. Every LLM call carries a cost log.

## Status

**Concept / Architecture Proposal.**
This repository contains the specification, data models, and roadmap.
We are seeking core contributors to begin implementation.

## Quick Links

- [Why this is necessary](MOTIVATION.md)
- [System Architecture](ARCHITECTURE.md)
- [Technical Specification](SPECIFICATION.md)
- [Development Roadmap](ROADMAP.md)
- [Comparison with existing tools](COMPARISON.md)
- [Prior experiment: v0 glue layer](experiments/v0-glue/)

## License

The specification and architecture documents are licensed under [CC-BY-SA 4.0](LICENSE).
Any future code will be MIT.

Note -  "Copy config.sample.yaml to config.yaml and adjust paths."
