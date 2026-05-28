# Getting Started with Mnemosyne

> **Status:** This project is currently a **concept / architecture proposal** with a `v0` glue prototype in `prior-art/v0-glue/`. The steps below describe the intended workflow for the reference implementation. If you are a contributor, the v0 prototype is the best place to start experimenting.

---

## Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| **Ollama** | Latest | Local LLM inference for all compilation, audit, and query operations |
| **SQLite** | 3.35+ | `state.db` requires WAL mode and window functions |
| **Python** | 3.11+ | Document extractors and LLM client glue (Phase 1) |
| **Rust** | 1.78+ | Core engine, job queue, API surface (Phase 1, optional for now) |
| **Git** | Any | Vault is a git-native repository |

### Install Ollama

```bash
# macOS/Linux
curl -fsSL https://ollama.com/install.sh | sh

# Verify
ollama --version
```

### Pull the required models

```bash
# Fast extraction model (4B–8B)
ollama pull gemma4:e4b

# Heavy compilation model (14B+)
ollama pull qwen2.5:14b

# Chat / query model
ollama pull qwen3:30b-a3b

# Audit / judge model (largest, used sparingly)
ollama pull llama3.3:70b

# Embedding model
ollama pull nomic-embed-text
```

> **Note:** Model names in `config.sample.yaml` are suggestions. Adjust to your hardware. A 30B model requires ~20GB VRAM. If you lack GPU memory, use smaller variants and expect lower compilation quality.

---

## 1. Clone the Repository

```bash
git clone https://github.com/noirblue/IsaacCLupus_mnemosyn_spec.git
cd IsaacCLupus_mnemosyn_spec
```

---

## 2. Configure Your Vault

```bash
# Copy the sample configuration
cp config.sample.yaml config.yaml

# Edit paths and model names
nano config.yaml   # or vim, code, etc.
```

### Minimum required changes

```yaml
jarvis_kb:
  vault_path: ~/jarvis-kb        # Where your knowledge lives
  ollama_url: http://localhost:11434

  models:
    ingest_fast: gemma4:e4b        # Must be pulled in Ollama
    compile_heavy: qwen2.5:14b     # Must be pulled in Ollama
    chat: qwen3:30b-a3b            # Must be pulled in Ollama
    judge: llama3.3:70b            # Must be pulled in Ollama
    embedding: nomic-embed-text    # Must be pulled in Ollama
```

### What the other settings mean

| Setting | Default | What it controls |
|---------|---------|------------------|
| `compile.auto_approve_threshold` | `0.8` | Audit score above which drafts auto-publish without human review |
| `compile.incremental` | `true` | Only recompile pages that changed |
| `compile.preserve_hand_edits` | `true` | Hand-edited files in `wiki/` are protected from overwrites |
| `query.context_budget` | `24000` | Max tokens from sources injected into a query context |
| `query.history_budget` | `3000` | Max tokens from conversation history |
| `query.source_budget` | `6000` | Max tokens per individual source |
| `query.max_sources` | `8` | Max number of sources cited in a single answer |
| `audit.auto_publish_after_audit` | `false` | If `true`, audit-passed drafts publish automatically |

---

## 3. Initialize the Vault

```bash
# Create the vault directory structure
mkdir -p ~/jarvis-kb/{raw/{self,world},wiki/{.drafts,self,world,synthesis},memory/{inbox,committed},packs}

# Initialize git (vault is git-native)
cd ~/jarvis-kb
git init
git add .
git commit -m "init: empty mnemosyne vault"
```

### Expected vault layout

```
~/jarvis-kb/
├── config.yaml              # Your edited config
├── state.db                 # Will be created on first run
├── raw/
│   ├── self/                # Your own notes, markdown files
│   └── world/               # External sources: PDFs, articles, transcripts
├── wiki/
│   ├── .drafts/             # Compiled pages awaiting approval
│   ├── self/                # Published personal knowledge
│   ├── world/               # Published external knowledge
│   └── synthesis/           # LLM-generated answers with citations
├── memory/
│   ├── inbox/               # Proposed memories from agents
│   └── committed/           # Human-approved, linked to graph
└── packs/                   # Agent-ready exports (INDEX.json, links.json)
```

---

## 4. First Ingestion

### Option A: Ingest a Markdown note

```bash
# Place a file in the raw intake
cp ~/Documents/my-notes.md ~/jarvis-kb/raw/self/

# Trigger ingestion (via CLI — when implemented)
mnemosyne ingest ~/jarvis-kb/raw/self/my-notes.md --namespace self
```

### Option B: Ingest a PDF

```bash
# Place the PDF
cp ~/Downloads/paper.pdf ~/jarvis-kb/raw/world/

# Trigger ingestion
mnemosyne ingest ~/jarvis-kb/raw/world/paper.pdf --namespace world
```

### What happens during ingestion

1. **Document extractor** (Python satellite) parses the file into heading-aware segments
2. **Fast LLM** (`ingest_fast` model) extracts concepts, entities, and claims
3. A `RawDocument` with provenance metadata is stored in `state.db`
4. A **compile job** is queued for the heavy model

---

## 5. First Compilation

```bash
# Compile all pending drafts
mnemosyne compile --scope all

# Or compile only a specific namespace
mnemosyne compile --scope world
```

### What happens during compilation

1. **Fast model** extracts concepts, relationships, and summaries from the `RawDocument`
2. **Heavy model** writes a cross-linked markdown article with citations
3. Output lands in `wiki/.drafts/` — **not yet published**
4. `content_hash` is recorded to detect future hand-edits

---

## 6. Audit & Publish

```bash
# Run the audit pipeline on all drafts
mnemosyne audit --scope all

# Review results (when implemented)
mnemosyne status
```

### Audit passes

| Pass | Checks | Failure Action |
|------|--------|--------------|
| **1. Structural lint** | Orphan pages, missing wikilink targets, broken frontmatter | Block publication |
| **2. Contradiction detection** | Claims that conflict with existing `wiki/` pages | Block or warn (configurable) |
| **3. Adversarial review** | Devil's advocate critique of argument structure | Block if critical flaws found |

### Approve and publish

```bash
# Approve a specific draft
mnemosyne approve wiki/.drafts/transformers-overview.md

# Or approve all passing drafts
mnemosyne approve --all-passing

# Publish atomically promotes .drafts/ → wiki/
mnemosyne publish
```

---

## 7. First Query

### Via CLI

```bash
mnemosyne ask "What did that paper say about attention mechanisms?"
```

### Via MCP (from an agent)

```json
{
  "tool": "kb_ask",
  "arguments": {
    "question": "What did that paper say about attention mechanisms?",
    "context_budget": 24000,
    "history_budget": 3000
  }
}
```

### What happens during a query

1. **Hybrid search** (BM25 + optional vector re-ranking) finds relevant pages
2. **Graph context** retrieval adds inbound/outbound neighbors
3. **Context budget** enforcement trims sources to fit `context_budget`
4. **Chat model** generates a cited, cross-linked answer stored in `wiki/synthesis/`

---

## 8. Agent Integration

Mnemosyne is **agent-agnostic**. Here is the minimal setup for three common agents.

### Aider (coding agent)

```bash
# Aider supports MCP servers
# Add Mnemosyne's MCP server to your agent config
aider --mcp-server ./mcp-server.py

# In chat:
# /kb "What did the paper say about transformers?"
```

### CrewAI (research agent)

```python
from crewai import Agent, Task
from mnemosyne_client import MnemosyneTool

researcher = Agent(
    role="Researcher",
    tools=[MnemosyneTool.kb_ingest, MnemosyneTool.kb_compile],
    ...
)
```

### Jan.ai (personal assistant)

```bash
# Jan.ai exposes an MCP server
# Configure it to call Mnemosyne's kb_remember after each conversation
# Memories land in memory/inbox/ for human approval
```

See [`AGENTS.md`](./AGENTS.md) for the full agent compatibility matrix.

---

## 9. Daily Workflow

```bash
# Morning: ingest overnight reading
mnemosyne ingest ~/Downloads/*.pdf --namespace world --compile

# Afternoon: review and approve drafts
mnemosyne audit
mnemosyne approve --all-passing
mnemosyne publish

# Evening: query your knowledge
mnemosyne ask "Summarize everything I read this week about LLM architectures"
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `ollama connection refused` | Ollama not running | `ollama serve` or `sudo systemctl start ollama` |
| `SQLite database is locked` | Multiple processes accessing `state.db` | Enable WAL mode: `PRAGMA journal_mode=WAL;` |
| Compilation is very slow | Heavy model too large for your GPU | Use a smaller `compile_heavy` model or enable CPU offloading |
| Drafts are empty or garbled | Fast model failed to extract concepts | Check Ollama logs; try a different `ingest_fast` model |
| Wikilinks are broken | Target page not yet compiled or published | Run `mnemosyne compile` and `mnemosyne publish` |
| Agent cannot connect via MCP | MCP server not running | Start the server: `mnemosyne serve --mcp` |

---

## Next Steps

- Read [`ARCHITECTURE.md`](./ARCHITECTURE.md) to understand the 7-layer design
- Read [`SPECIFICATION.md`](./SPECIFICATION.md) for the data model and API contracts
- Read [`AGENTS.md`](./AGENTS.md) to choose and configure your agent
- Review [`ROADMAP.md`](./ROADMAP.md) to see what is being built and where you can contribute
- Open an issue if you hit a schema mismatch, API friction, or agent integration problem

---

## Contributing to the Reference Implementation

This repository is a **specification and blueprint**. The code is what we build together.

If you want to start coding:

1. Review the `python_thoughts/` and `rust_thoughts/` directories for implementation sketches
2. Open a draft PR against **Phase 1: Core Engine** in [`ROADMAP.md`](./ROADMAP.md)
3. Join the discussion on whether the core engine should be Rust-first or Python-first

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for skill requirements and governance.
