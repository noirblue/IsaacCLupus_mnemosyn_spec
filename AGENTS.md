# Mnemosyne and Agents: Architecture & Recommendations

## Is Mnemosyne Agent-Free?

**No** — Mnemosyne is **not** agent-free. But the agent relationship is **architecturally different** from other projects.

In Mnemosyne, the **agent is a client of the OS**, not a component inside it. The OS provides the memory substrate; the agent consumes it. This is the inverse of MemoryOS (agent lives inside the memory system) and KnowledgeOS (OS governs the agent's behavior).

---

## The Three Interfaces

The agent interacts with Mnemosyne through three interfaces:

| Interface | What the agent does | Example |
|-----------|---------------------|---------|
| **MCP** | `kb_search`, `kb_ask`, `kb_ingest`, `kb_remember`, `kb_compile` | "Find me everything about transformers" → returns cited, cross-linked pages |
| **REST** | Direct API calls for batch operations, job status, graph queries | "Ingest this PDF and compile it when done" |
| **CLI** | Scripted workflows, CI integration, automation | `mnemosyne ingest paper.pdf --namespace world --compile` |

---

## Agent Roles in the Memory Lifecycle

The agent proposes → OS stores in `memory/inbox/` → Audit engine checks → Human approves → Committed to graph.

The `memory/` directory is explicitly designed for **agent memory**:

| Stage | Location | Who triggers | What happens |
|-------|----------|--------------|--------------|
| **Proposed** | `memory/inbox/` | Agent (via `kb_remember`) | Raw memory stored, flagged for review |
| **Committed** | `memory/committed/` | Human approval or auto-approve (configurable) | Linked to graph, searchable, cited |
| **Archived** | `wiki/archived/` | System (stale threshold) | Retained for provenance, not active search |

---

## The Agent is Also the Compiler

The two-tier compilation engine is essentially an **agent workflow**:

- **Fast model (30B)** acts as extraction agent — pulls concepts, entities, claims from raw sources
- **Heavy model (70B+)** acts as writing agent — generates cross-linked articles with citations
- **Audit model (70B+)** acts as review agent — checks for contradictions, structural errors, adversarial weaknesses

These are not human roles. They are **agent roles** that the OS orchestrates.

---

## But Mnemosyne is Agent-Agnostic

The spec does not specify *which* agent uses the OS. It could be:

- A coding agent (like Codex or Gemini CLI) querying knowledge via MCP
- A research agent autonomously ingesting papers and compiling articles
- A personal assistant remembering conversations and filing them as memory
- A multi-agent system where different agents handle ingestion, compilation, and audit

The OS provides the **substrate**. The agent provides the **intent**.

---

## Contrast with Other Projects

| Project | Agent relationship |
|---------|-------------------|
| **MemoryOS** | Agent is the *user* — the system remembers the agent's conversations |
| **KnowledgeOS** | Agent is *governed* — the OS controls what the agent can do |
| **OriginTrail DKG** | Agents are *peers* — they publish and verify knowledge on a network |
| **llm-wiki-compiler** | Agent is the *compiler* — single tool, single workflow |
| **Mnemosyne** | Agent is a *client* — the OS serves knowledge, the agent decides what to do with it |

---

## Recommended Agents by Use Case

### 1. Coding Agent (queries knowledge via MCP)

**Recommended: [opencode](https://github.com/sst/opencode) (SST) or [Aider](https://github.com/paul-gauthier/aider)**

| | opencode | Aider |
|--|----------|-------|
| **License** | Open source | Open source |
| **Model** | BYOK — Ollama, Claude, GPT, DeepSeek, Qwen | BYOK — any OpenAI-compatible |
| **Form** | Terminal TUI / desktop app | CLI, git-native |
| **MCP** | Yes | Limited |
| **Best for** | Terminal-first devs who want Claude Code features with any model | Git-diff workflows, code review |

**Why for Mnemosyne:** Both are BYOK, so they can point at local Ollama models. opencode has MCP support, so it can call Mnemosyne's `kb_search` and `kb_ask` directly. Aider is git-native, which aligns with Mnemosyne's vault-as-git-repo model.

**Integration:** The coding agent queries Mnemosyne via MCP when it needs context — "What did that paper say about transformers?" → Mnemosyne returns cited, cross-linked pages.

---

### 2. Research Agent (autonomous ingestion and compilation)

**Recommended: [CrewAI](https://github.com/crewAIInc/crewAI) with custom tools**

**Why for Mnemosyne:** CrewAI's role-based design maps naturally to Mnemosyne's pipeline:

| CrewAI Role | Mnemosyne Function |
|-------------|-------------------|
| Researcher | Ingests PDFs, extracts concepts via fast model |
| Writer | Compiles articles via heavy model |
| Reviewer | Runs audit pipeline (lint, contradiction, adversarial) |
| Editor | Human-in-the-loop approval gate |

**Integration:** CrewAI agents call Mnemosyne's REST API or MCP server to ingest sources, trigger compilation jobs, and query results. The jobs table tracks progress.

**Alternative:** [LangGraph](https://github.com/langchain-ai/langgraph) for more complex branching workflows — e.g., "if contradiction detected, route to human review; if audit passes, auto-publish."

---

### 3. Personal Assistant (conversation memory and proactive filing)

**Recommended: [Jan.ai](https://jan.ai/) or [AnythingLLM](https://anythingllm.com/)**

| | Jan.ai | AnythingLLM |
|--|--------|-------------|
| **License** | MIT | MIT |
| **Local models** | Native Ollama integration | Requires Ollama pairing |
| **MCP** | Yes | Yes |
| **Memory** | Per-session (not persistent identity) | Workspace-based |
| **Best for** | Pure local LLM running | Document RAG with agent builder |

**Why for Mnemosyne:** Both expose MCP servers that can call Mnemosyne's `kb_remember` to file conversation snippets as proposed memories. Jan.ai is cleaner for pure local operation; AnythingLLM has better document RAG if the assistant needs to query existing knowledge.

**Integration:** Conversation → assistant extracts key facts → calls `kb_remember` → Mnemosyne stores in `memory/inbox/` → human approves → committed to graph.

**Note:** Neither has true persistent identity across sessions. For that, you'd need to build a thin wrapper that maintains a user profile in Mnemosyne's `memory/committed/` and injects it into the system prompt.

---

### 4. Multi-Agent Orchestration (ingestion + compilation + audit)

**Recommended: [Pydantic AI](https://github.com/pydantic/pydantic-ai) or [CrewAI](https://github.com/crewAIInc/crewAI)**

| | Pydantic AI | CrewAI |
|--|-------------|--------|
| **License** | MIT | MIT |
| **Typing** | Strict Pydantic models | Dynamic, role-based |
| **Observability** | Logfire integration | Limited |
| **Best for** | Type-safe agent workflows, dependency injection | Rapid prototyping, role-based teams |

**Why for Mnemosyne:** Pydantic AI aligns with Mnemosyne's structured output philosophy — every agent run returns a typed model. The dependency injection makes testing the compilation pipeline easier. CrewAI is faster to prototype if you want to spin up a research crew in an afternoon.

**Integration:** The multi-agent system is the **compilation pipeline itself**:

- **Agent A (Extractor):** `kb_ingest` → fast model concept extraction
- **Agent B (Compiler):** `kb_compile` → heavy model article generation
- **Agent C (Auditor):** `kb_audit` → contradiction detection + adversarial review
- **Human:** approval gate → `kb_publish`

---

### 5. Agent Gateway / Governance (MCP access control)

**Recommended: [MCPX](https://github.com/lunardev/mcpx) (Lunar.dev)**

**Why for Mnemosyne:** If you have multiple agents accessing Mnemosyne's MCP server, MCPX provides:

- Tool-level access control (which agents can call `kb_ingest` vs. `kb_search`)
- Audit logging of all agent-to-OS interactions
- Credential isolation
- Rate limiting and policy gating

**Integration:** Agents → MCPX gateway → Mnemosyne MCP server. Every `kb_ask`, `kb_remember`, `kb_compile` is logged and governed.

---

## Summary Table

| Mnemosyne Area | Recommended Agent | Why | Integration Point |
|----------------|-------------------|-----|-------------------|
| **Coding / querying** | opencode / Aider | BYOK, MCP support, git-native | MCP: `kb_search`, `kb_ask` |
| **Research / ingestion** | CrewAI / LangGraph | Role-based pipeline, task delegation | REST/MCP: `kb_ingest`, `kb_compile` |
| **Personal assistant** | Jan.ai / AnythingLLM | Local-first, MCP support | MCP: `kb_remember` |
| **Multi-agent orchestration** | Pydantic AI / CrewAI | Type-safe or rapid prototyping | REST: job queue, compilation pipeline |
| **Gateway / governance** | MCPX | Access control, audit, policy | MCP proxy layer |

---

## One Important Caveat

Most of these "agents" are actually **agent frameworks** or **agent interfaces** — they provide the loop, tool integration, and orchestration, but the *intelligence* comes from the LLM underneath (Ollama, Claude, GPT). Mnemosyne's job is not to replace these frameworks. It is to be the **memory layer they all share** — so when opencode needs context, CrewAI needs to file a compilation result, or Jan.ai needs to remember a conversation, they all talk to the same `state.db` through the same MCP/REST surface.

**The agent is the client. Mnemosyne is the substrate.**
