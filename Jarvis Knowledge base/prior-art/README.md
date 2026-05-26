# Experiment: v0 Glue Layer

## What this is

This is a working ~450-line Python integration layer that attempts to unify Synto, Synthadoc, LLM-WIKI-MCP, and Link behind a single Ollama proxy and MCP gateway.

It works. It is also why this specification exists.

## What it proved

- **Schema translation is fragile.** Frontmatter normalization between four tools breaks on edge cases.
- **Ollama contention is unsolvable at the glue layer.** A proxy helps, but the root issue is that four tools compete for the same GPU without a shared job queue.
- **Vault sync is a hack.** rsyncing between four directory layouts is not a data model.
- **MCP aggregation is a workaround, not a design.** Six unified tools wrapping twenty underlying tools is complexity hiding complexity.

## What it does not prove

That glue is the right answer. It proves that **unification at the application layer** is the only sustainable path.

## Status

Functional proof-of-concept. Not maintained. Superseded by the [Unified Architecture](../ARCHITECTURE.md).

Project layouts

~/jarvis-kb-bridge/
├── config.yaml
├── pyproject.toml
├── jarvis_kb/
│   ├── __init__.py
│   ├── config.py
│   ├── vault_sync.py
│   ├── ollama_proxy.py
│   ├── mcp_gateway.py
│   └── cli.py
└── systemd/
    ├── jarvis-kb-proxy.service
    └── jarvis-kb-mcp.service


 Glue Instructions

1. pyproject.toml               Install with: pip install -e .

2. config.yaml                  Place this in the project root (or ~/.config/jarvis-kb/
                                config.yaml). It declares both your Foundry and Frontline.

3. jarvis_kb/config.py

4. jarvis_kb/vault_sync.py      This is the publish pipeline. It normalizes frontmatter,
                                resolves wikilink collisions, rebuilds indexes, and snapshots Link

5. jarvis_kb/ollama_proxy.py    This solves the contention problem. It exposes
                                http://127.0.0.1:11436 and either routes by priority (queue mode) or forwards to the correct node (router mode).

6. jarvis_kb/mcp_gateway.py     A single MCP server that exposes six unified tools. Your
                                Jarvis orchestrator connects to this one endpoint instead of four.

7. jarvis_kb/cli.py

8. systemd/jarvis-kb-proxy.service - For your Kubuntu box, install as a user service (systemctl --user).

9. systemd/jarvis-kb-mcp.service

10. Quickstart Commands

# 1. Install the bridge
cd ~/jarvis-kb-bridge
pip install -e .

# 2. Initialize directories
jarvis-kb --config ~/.config/jarvis-kb/config.yaml init

# 3. Start the proxy (so your Jarvis apps talk to :11436, not :11434 directly)
jarvis-kb serve-proxy &

# 4. Ingest something
jarvis-kb publish   # after running synto/synthadoc on the foundry

# 5. Connect your orchestrator to the MCP gateway
# In Claude Code / Cursor / Cline:
#   "command": "jarvis-kb", "args": ["serve-mcp"]

