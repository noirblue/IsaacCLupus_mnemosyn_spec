# Motivation: Why Glue Is Not Good Enough

## Scenario: A User Tries to Build a Jarvis Memory Stack

1. Installs **Synto** for note compilation. Works great for Markdown.
2. Discovers **Synthadoc** for PDF ingest. Now has two vaults.
3. Adds **LLM-WIKI-MCP** for conversation history. Now has three SQLite files.
4. Discovers **Link** for agent memory lifecycle. Now has four MCP servers.

## The Integration Tax

| Task | Effort with 4 tools | Effort with unified OS |
|---|---|---|
| Ingest a PDF and ask about it | 4 commands across 3 directories | `kb ingest paper.pdf && kb ask "summary?"` |
| Prevent GPU deadlock | Write a custom Ollama proxy (150 LOC) | Built-in job queue with priorities |
| Fix a broken wikilink | Guess which tool owns the file | Single `doctor` command |
| Audit knowledge quality | Run 3 separate lint commands | Single `kb audit` with unified report |
| Move from laptop to desktop | Rebuild 4 toolchains | Copy one vault directory |

## The Deeper Issue

The current ecosystem optimizes for **tool authors**, not **system architects**.
Each tool owns its own data model. None can see the others' state.
We are building knowledge silos inside a single machine.

This specification proposes the **layered unification** that the ecosystem needs.
