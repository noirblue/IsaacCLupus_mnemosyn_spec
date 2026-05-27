# Rust Implementation Thoughts

This folder contains language-specific research and feasibility studies for a potential Rust core implementation of Mnemosyne. These documents are **exploratory** — they inform architecture decisions but do not mandate them.

## Status

The Mnemosyne specification is **language-agnostic**. A Python reference implementation is equally valid. This folder exists because the core engine (schema, job queue, graph, API surface) maps naturally to Rust's strengths, and several potential contributors have expressed interest.

## Investigations

| # | Topic | Status | File |
|---|---|---|---|
| 01 | SQLite: WAL mode, pooling, async | Complete | [01-rusqlite-wal-pooling.md](01-rusqlite-wal-pooling.md) |
| 02 | Tokio job queue for Ollama | Complete | [02-tokio-job-queue.md](02-tokio-job-queue.md) |
| 03 | Axum/Actix for MCP + REST | Complete | [03-axum-mcp-rest.md](03-axum-mcp-rest.md) |
| 04 | File watcher + incremental compile | Complete | [04-file-watcher-incremental-compile.md](04-file-watcher-incremental-compile.md) |
| 05 | Graph traversal engine | Complete | [05-graph-traversal.md](05-graph-traversal.md) |
| 06 | Pack export + CLI deployment | Complete | [06-pack-export-cli.md](06-pack-export-cli.md) |
| 07 | Python FFI / subprocess strategies | Pending | 07-python-ffi-strategies.md |
| 08 | Rust PDF extraction feasibility | Pending | 08-rust-pdf-extraction.md |

## Summary of Findings

All six completed investigations conclude that a **Rust core + Python satellite** architecture is viable and recommended:

- **01:** `rusqlite` + `r2d2` + `tokio-rusqlite` is production-ready for SQLite
- **02:** SQLite-backed job queue with Tokio `Semaphore` prevents Ollama deadlock
- **03:** Axum + `rmcp` serves unified MCP + REST with sub-millisecond latency
- **04:** `notify` crate + incremental compile responds to file changes in &lt;20ms
- **05:** `petgraph` provides safe, fast graph traversal with zero memory leaks
- **06:** `clap` + `serde` compiles to single binary, eliminating Python environment hell

## Remaining Open Questions

| # | Question | Why It Matters |
|---|---|---|
| 07 | How does Rust spawn Python extractors and receive JSON results? | Defines the Rust/Python boundary |
| 08 | Can Rust replace Python for PDF/DOCX extraction long-term? | Determines if satellites are permanent or transitional |

## How to Contribute

If you have Rust expertise and want to investigate a topic:
1. Open an issue on the main repo to claim the topic
2. Write your findings as a markdown file in this folder
3. Submit a PR updating this README with your document
