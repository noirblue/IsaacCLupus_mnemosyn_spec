# Contributing

## Project Origin

This began as a personal attempt to unify four local knowledge tools into a single Jarvis memory stack. After writing ~450 lines of integration glue and hitting fundamental schema, concurrency, and API mismatches, it became clear that the problem required a unified architecture, not better glue.

The maintainer of this spec is a systems thinker, not a software engineer. We need core developers to turn this architecture into a reference implementation.

This project needs contributors in the following areas:

- **Core Architect**: Python/SQLite schema design, job queue, transaction safety
- **Ingestion Engineer**: Document extractors (PDF, DOCX, PPTX, video transcripts)
- **LLM Pipeline Engineer**: Two-tier compilation, prompt engineering, model routing
- **API / MCP Developer**: FastAPI, MCP SDK, CLI design
- **Obsidian / UI Developer**: Plugin compatibility, web visualization
- **Technical Writer**: Documentation, examples, tutorials

## Skills that would help

### Core Engine (Rust)
- Rust 1.78+ with Tokio async
- `rusqlite` (WAL mode, connection pooling)
- `axum` or `actix-web` (MCP + REST server)
- `petgraph` or similar (in-memory graph traversal)
- `clap` + `serde` (CLI and pack export)

### Document Extraction (Python)
- Python 3.11+
- `pymupdf`, `pdfplumber`, or `unstructured` (PDF)
- `python-docx`, `python-pptx` (Office formats)
- `openai-whisper`, `yt-dlp` (audio/video transcripts)

### Integration
- Ollama or local LLM tooling
- MCP SDK (any language)
- SQLite schema design and migration systems

## How to contribute at this stage

1. **Review the spec**: Open an issue if a data model or API feels wrong.
2. **Prototype**: If you want to start coding, open a draft PR against Phase 1.
3. **Spread the word**: If you know a developer who hates glue code, send them here.
4. **Rust developers**: the core engine (SQLite, job queue, graph, API) is an ideal Rust problem. We are open to a Rust-core implementation if you are willing to build the FFI bridge to Python extractors.
   
## Governance (for now)

- noirblue maintains the spec and roadmap.
- Major architectural changes require discussion in GitHub Issues.
- Code contributions fall under MIT license.
