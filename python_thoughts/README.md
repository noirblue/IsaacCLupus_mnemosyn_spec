# Python Implementation Thoughts

This folder contains research and feasibility studies for the **Python satellite layer** of Mnemosyne. These are not second-class components — they are the specialized tools that the Rust core delegates to when the Python ecosystem has no equal.

## Why Python Satellites Exist

The Rust core handles schema, job queue, graph traversal, API surface, and CLI. But Rust cannot yet match Python's dominance in:

| Domain | Python Libraries | Rust Equivalent | Verdict |
|---|---|---|---|
| PDF extraction | `pymupdf`, `pdfplumber`, `unstructured` | `pdf-extract`, `lopdf` | Python wins by 5+ years of development |
| Office documents | `python-docx`, `python-pptx`, `openpyxl` | None mature | Python only viable path |
| Video/audio transcripts | `openai-whisper`, `faster-whisper`, `yt-dlp` | `whisper-rs` (bindings) | Python native, Rust bindings exist but lag |
| LLM client ecosystem | `httpx`, `openai`, `ollama-python` | `reqwest` | Equivalent for HTTP; Python SDKs more ergonomic |
| Prompt engineering | `instructor`, `pydantic-ai`, `jinja2` | None | Python-only ecosystem |

These are **permanent satellites**, not transitional code. The Rust core spawns them as subprocesses, receives JSON results, and integrates them into the unified system.

---

## Investigations

| # | Topic | Status | File | Key Decision |
|---|---|---|---|---|
| 01 | PDF extraction: `pymupdf` vs `pdfplumber` vs `unstructured` | **Complete** | [01-pdf-extraction.md](01-pdf-extraction.md) | Tiered strategy: PyMuPDF4LLM default, pdfplumber for tables, Unstructured for complex layouts |
| 02 | Office documents: `python-docx`, `python-pptx`, `openpyxl` | **Complete** | [02-office-documents.md](02-office-documents.md) | python-docx primary (style-native headings), python-pptx only viable path, openpyxl primary for XLSX |
| 03 | Video/audio transcripts: Whisper, yt-dlp, ffmpeg | **Complete** | [03-video-audio-transcripts.md](03-video-audio-transcripts.md) | whisperx default (alignment + diarization), yt-dlp for metadata/audio, ffmpeg subprocess for preprocessing |
| 04 | LLM client glue: `httpx`, streaming, Ollama SDK | **Complete** | [04-llm-client-glue.md](04-llm-client-glue.md) | openai SDK for universal chat, ollama SDK for local features, instructor for structured output |
| 05 | Heavy LLM compilation: prompt templates, response parsing | **Complete** | [05-heavy-llm-compilation.md](05-heavy-llm-compilation.md) | Jinja2 templates + Instructor structured output + 4-stage pipeline (extract -> compile -> audit -> publish) |
| 06 | Rust-Python FFI: subprocess vs `pyo3` vs `maturin` | Pending | 06-rust-python-ffi.md | — |

---

## Cross-Cutting Themes

### Licensing
All Python satellite libraries are permissively licensed (MIT, Apache-2.0, BSD, Unlicense) with one exception: **PyMuPDF/PyMuPDF4LLM is AGPL-3.0**. Subprocess isolation means no linking contamination, but distributed builds should consider PyMuPDF Pro (commercial) or the pure-MIT fallback path (pdfplumber + pypdf).

### Communication Contract
All satellites use the same interface: **JSON over stdout** or **temporary files**.

```bash
# Extraction satellites
python -m mnemosyne_py.extract pdf file.pdf --output /tmp/result.json
python -m mnemosyne_py.extract docx report.docx --output /tmp/result.json
python -m mnemosyne_py.extract xlsx data.xlsx --output /tmp/result.json
python -m mnemosyne_py.extract pptx deck.pptx --output /tmp/result.json

# Transcription satellite
python -m mnemosyne_py.extract video https://youtube.com/watch?v=abc --output /tmp/result.json

# LLM satellites
python -m mnemosyne_py.llm complete --model llama3.3:70b --prompt-file /tmp/prompt.txt --output /tmp/response.json
python -m mnemosyne_py.llm extract --model llama3.3:70b --prompt-file /tmp/prompt.txt --schema-file /tmp/schema.json --output /tmp/result.json
python -m mnemosyne_py.llm stream --model qwen2.5:32b --prompt-file /tmp/prompt.txt

# Compilation satellites
python -m mnemosyne_py.compile extract --source-file /tmp/raw.json --template extract/concepts --model-tier fast --output /tmp/concepts.json
python -m mnemosyne_py.compile compile --source-file /tmp/raw.json --template compile/notes_to_wiki --model-tier heavy --output /tmp/article.json
python -m mnemosyne_py.compile audit --article-file /tmp/article.json --template audit/adversarial_review --model-tier heavy --output /tmp/audit.json
```

### Unified `RawDocument` Schema
All extraction satellites return a unified JSON schema that the Rust core consumes regardless of source format. See individual documents for format-specific schema definitions.

### Provenance-First Design
Every satellite captures extraction metadata (tool version, processing time, configuration) and maps it to the `pages` table's `provenance` JSON field and the `audit_log` table.

---

## Integration Model

The Rust core communicates with Python satellites via **JSON over stdout/stdin** or **temporary files**:

```bash
# Rust spawns, Python executes, JSON returns
python -m mnemosyne_py.extract pdf file.pdf --output /tmp/result.json
# Rust reads /tmp/result.json, inserts into state.db
```

The satellite layer is a **permanent architectural component**, not a temporary bridge. As the Rust ecosystem matures, individual satellites may be reimplemented in Rust if and only if the Rust equivalent matches or exceeds Python's capabilities in that domain. The decision to reimplement is data-driven: equivalent accuracy, equivalent speed, equivalent feature coverage.

---

## Next Steps

1. Complete **06-rust-python-ffi.md** — compare subprocess, `pyo3`, and `maturin` as integration mechanisms
2. Draft `mnemosyne_py` package structure — `pyproject.toml`, module layout, shared utilities
3. Implement reference satellite for one domain (e.g., PDF extraction) as a working prototype
4. Define shared JSON schema definitions in code (Pydantic models for `RawDocument`, `AuditLog`, etc.)
5. Design satellite lifecycle management — warm pools, health checks, timeout handling