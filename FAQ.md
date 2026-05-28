# Frequently Asked Questions

## General

### Is Mnemosyne agent-free?

**No.** Mnemosyne is **agent-agnostic**, not agent-free. The agent is a **client of the OS** — it consumes the memory substrate through MCP, REST, or CLI interfaces. The OS does not prescribe which agent, how it reasons, or what its goals are. See [`AGENTS.md`](./AGENTS.md) for the full architecture and recommended agents.

### Why build another knowledge tool? Don't Obsidian, Notion, etc. already exist?

Mnemosyne is not a note-taking app. It is a **semantic memory operating system** for autonomous agents. Existing tools optimize for human authoring; Mnemosyne optimizes for **agent consumption, audit, and provenance**. The integration tax of stitching Synto + Synthadoc + LLM-WIKI-MCP + Link together is higher than the value of the tools themselves. Mnemosyne replaces that tax with one vault, one schema, one API.

### Who is this for?

- Developers building Jarvis-like personal agents who are tired of glue code
- Researchers who need auditable, cited knowledge compilation from raw sources
- Anyone who wants their knowledge to stay on their machine unless they explicitly export it

### I am not a programmer. Can I use this?

Not yet. This repository is a **specification and blueprint**. The reference implementation is being built by contributors. If you are a systems thinker who can write clear requirements, open an issue — your perspective is valuable.

---

## Architecture & Design

### Why SQLite and not PostgreSQL?

| SQLite | PostgreSQL |
|--------|------------|
| Zero configuration — no daemon, no ports, no credentials | Requires installation, configuration, and maintenance |
| Single file (`state.db`) — copy, backup, sync trivially | Multi-file cluster, complex backup strategy |
| WAL mode handles concurrent reads + one writer | Better for high-write concurrency, but overkill for local-first |
| Embedded in the Rust core — no network overhead | Network roundtrip even on localhost |
| Sufficient for local-first, single-user knowledge | Better suited for multi-user, high-throughput web apps |

Mnemosyne is **solo-first**. If you outgrow SQLite, the schema is portable. But for a personal knowledge vault on one machine, SQLite is the correct default.

### Why Rust for the core and Python for satellites?

| Layer | Language | Rationale |
|-------|----------|-----------|
| Core engine (schema, queue, graph, API) | **Rust** | Memory safety, zero-cost async (Tokio), single-binary deployment |
| Document extractors (PDF, DOCX, video) | **Python** | Mature libraries (`pymupdf`, `python-docx`, Whisper, `yt-dlp`) with no Rust equivalents |
| LLM client glue | **Rust or Python** | HTTP calls to Ollama; both are sufficient |
| CLI | **Rust** | `clap` + `serde` compiles to one binary with no Python environment |

Python satellites are **permanent**, not transitional. The Rust core spawns them as subprocesses for extraction tasks.

### Can I use this without an LLM?

**Partially.** The vault, schema, and git-native storage work without any LLM. You can ingest markdown files, manage wikilinks, and query pages manually. However, the **compilation engine** (Layer 3) and **audit engine** (Layer 4) require LLM inference for concept extraction, article generation, and quality checking. Without an LLM, Mnemosyne functions as a structured markdown wiki with graph traversal — still useful, but not the full system.

### Why not just use a RAG pipeline?

RAG (Retrieval-Augmented Generation) is a **query-time technique**. Mnemosyne is a **lifecycle system**:

| RAG Pipeline | Mnemosyne |
|-------------|-----------|
| Ingest → chunk → embed → retrieve at query time | Ingest → extract → compile → audit → publish → query |
| No persistent structured knowledge | `wiki/` is a curated, cross-linked, cited knowledge base |
| No provenance tracking | Every claim carries `provenance` JSON |
| No human approval gate | Drafts require explicit approval before publication |
| No audit or contradiction detection | Three-pass quality gate before any page goes live |

RAG is a component Mnemosyne could use for retrieval. Mnemosyne is the system that makes RAG outputs trustworthy enough to publish.

### Why is the vault git-native?

Git provides **free versioning, branching, and sync** for knowledge:

- Hand-edits in `wiki/` are tracked — you can see when an agent overwrote your work
- `packs/` exports are reproducible — checkout a commit, rebuild the pack
- Multi-device sync is `git push` / `git pull`, not a custom protocol
- Audit log gains a second dimension — `git blame` for content, `audit_log` for LLM calls

### What happens if I edit a published page by hand?

Mnemosyne **protects hand-edits** via `content_hash`:

1. You edit `wiki/world/transformers.md` in your editor
2. The `content_hash` no longer matches the stored value
3. The compilation engine sees `write_guard: protected` and **skips** that page during recompile
4. Your edit is preserved. If you want the agent to overwrite it, set `write_guard: open`.

See [`SPECIFICATION.md`](./SPECIFICATION.md) §6.1 for write guard policies.

---

## Agents & Integration

### Which agent should I use?

Depends on your workflow:

| Use Case | Recommended Agent | Integration Point |
|----------|-----------------|-------------------|
| Coding with knowledge queries | [opencode](https://github.com/sst/opencode) or [Aider](https://github.com/paul-gauthier/aider) | MCP: `kb_search`, `kb_ask` |
| Autonomous research & compilation | [CrewAI](https://github.com/crewAIInc/crewAI) | REST/MCP: `kb_ingest`, `kb_compile` |
| Personal assistant with memory | [Jan.ai](https://jan.ai/) or [AnythingLLM](https://anythingllm.com/) | MCP: `kb_remember` |
| Multi-agent orchestration | [Pydantic AI](https://github.com/pydantic/pydantic-ai) | REST: job queue, compilation pipeline |
| Gateway / access control | [MCPX](https://github.com/lunardev/mcpx) | MCP proxy layer |

See [`AGENTS.md`](./AGENTS.md) for the full compatibility matrix.

### Can multiple agents share one Mnemosyne instance?

Yes — that is the design. Multiple agents call the same `state.db` through the same MCP/REST surface. If you need access control (e.g., Agent A can only `kb_search`, Agent B can `kb_ingest`), use [MCPX](https://github.com/lunardev/mcpx) as a gateway.

### My agent doesn't support MCP. Can it still use Mnemosyne?

Yes — use the **REST API** or **CLI**. Any agent that can make HTTP calls or spawn shell commands can interact with Mnemosyne. MCP is the native interface, not the only one.

### Does Mnemosyne replace my agent framework?

**No.** Mnemosyne is the **memory layer** underneath. Your agent framework (CrewAI, Pydantic AI, etc.) provides the loop, tool integration, and orchestration. Mnemosyne provides the structured, audited, provenance-rich knowledge they all share.

---

## Usage & Operations

### How much GPU memory do I need?

| Model Size | VRAM Required | Role |
|------------|-------------|------|
| 4B–8B | 4–8 GB | Fast extraction (`ingest_fast`) |
| 14B | 10–14 GB | Heavy compilation (`compile_heavy`) |
| 30B | 20–24 GB | Chat / query (`chat`) |
| 70B | 40–48 GB | Audit / judge (`judge`) — used sparingly |

You can run smaller models with reduced quality. CPU inference works but is slow for compilation. The fast model is the only one that runs continuously; heavy and judge models are queued and run as jobs.

### Can I run this on a laptop without a GPU?

Yes, with compromises:
- Use smaller models (e.g., `qwen2.5:7b` instead of `14b`)
- Enable CPU offloading in Ollama
- Compilation will be slower (minutes per article instead of seconds)
- Query latency is acceptable even on CPU

### How do I back up my knowledge vault?

```bash
# The vault is a git repo + one SQLite file
cd ~/jarvis-kb
git add -A
git commit -m "backup: $(date -Iseconds)"

# Push to your private remote
git push origin main

# Or copy the directory
cp -r ~/jarvis-kb /backup/location/
```

`state.db` is a single file — copy it like any other document. WAL mode creates `-wal` and `-shm` files; copy all three for consistency.

### What happens if Ollama crashes during compilation?

The **job queue** handles failures:
1. Job status changes to `failed`
2. `receipts.phase_log` records the failure point
3. `audit_log` logs the error with latency and model info
4. You can retry: `mnemosyne retry --job-id <id>`
5. If the draft was partially written, `content_hash` mismatch triggers cleanup

### Can I import my existing Obsidian vault?

Planned for Phase 4. The schema is designed to absorb standard Markdown with YAML frontmatter. Wikilinks (`[[Concept]]`) are native to Mnemosyne. A migration tool will map Obsidian folders to `raw/self/` and run ingestion.

---

## Governance & Trust

### Who controls what the agent can do?

**You do.** Mnemosyne defaults to **human-in-the-loop**:
- Drafts require approval before publication (`auto_approve_threshold: 0.8` is configurable)
- Hand-edits are protected by `write_guard`
- Agent memory proposals land in `memory/inbox/` — they do not enter the graph until you approve them
- The audit engine flags contradictions and adversarial weaknesses for your review

### Can an agent lie to me through Mnemosyne?

An agent can propose false information, but Mnemosyne makes it **detectable**:
- Every claim carries `provenance` — you can trace it to the original source
- The audit engine runs contradiction detection against existing `wiki/`
- The adversarial review pass critiques argument structure
- `rejected_count` accumulates — patterns of bad proposals are visible

Mnemosyne does not prevent bad inputs. It makes them **auditable**.

### Is my knowledge sent to the cloud?

**No.** Mnemosyne is **local-first**:
- Ollama runs on your machine
- `state.db` is a local SQLite file
- The vault is a local directory
- Optional DKG anchoring (Phase 4) is **opt-in** and per-pack, not automatic

The only network calls are to your local Ollama instance (`http://localhost:11434`).

---

## Contributing

### I want to help build this. Where do I start?

1. Read [`ARCHITECTURE.md`](./ARCHITECTURE.md) and [`SPECIFICATION.md`](./SPECIFICATION.md)
2. Review the `python_thoughts/` and `rust_thoughts/` directories for implementation sketches
3. Open a draft PR against **Phase 1: Core Engine** in [`ROADMAP.md`](./ROADMAP.md)
4. Join the discussion on Rust-vs-Python core in GitHub Issues

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for skill requirements.

### Why is the maintainer not a programmer?

The maintainer spent weeks trying to make four excellent tools work together, wrote ~450 lines of glue, and realized the problem was architectural. This spec is the **systems thinking**; the code is what the community builds. The maintainer's role is to protect the design principles (one vault, one schema, local-first, human-curated) while contributors handle implementation.

### Can I fork this and build a commercial product?

The specification is **CC-BY-SA 4.0** — share alike. Any future code will be **MIT**. Fork, build, sell — but if you improve the spec, share it back.

---

*Have a question not covered here? Open an issue with the `question` label.*
