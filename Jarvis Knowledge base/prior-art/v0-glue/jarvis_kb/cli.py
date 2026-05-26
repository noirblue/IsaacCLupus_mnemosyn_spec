import argparse
import asyncio
import os
import subprocess
from pathlib import Path

import uvicorn

from .config import load_config
from .mcp_gateway import McpGateway
from .ollama_proxy import app as proxy_app
from .vault_sync import VaultSync


def main():
    parser = argparse.ArgumentParser("jarvis-kb")
    parser.add_argument("--config", default=os.environ.get("JARVIS_KB_CONFIG", "config.yaml"))
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("init", help="Initialize all vault directories and git repos")
    sub.add_parser("publish", help="Run Foundry -> Frontline publish pipeline")
    p_proxy = sub.add_parser("serve-proxy", help="Start the Ollama priority proxy")
    p_proxy.add_argument("--host", default="127.0.0.1")
    p_proxy.add_argument("--port", type=int, default=11436)
    sub.add_parser("serve-mcp", help="Start the unified MCP gateway (stdio)")
    sub.add_parser("status", help="Check tool availability and vault sizes")

    args = parser.parse_args()
    cfg = load_config(args.config)

    if args.cmd == "init":
        _cmd_init(cfg)
    elif args.cmd == "publish":
        VaultSync(cfg).run()
    elif args.cmd == "serve-proxy":
        # Inject config into FastAPI app state
        proxy_app.state.cfg = cfg
        from .ollama_proxy import PROXY_CONFIG
        PROXY_CONFIG.update(cfg)
        uvicorn.run(proxy_app, host=args.host, port=args.port, log_level="info")
    elif args.cmd == "serve-mcp":
        asyncio.run(McpGateway(cfg).run())
    elif args.cmd == "status":
        _cmd_status(cfg)
    else:
        parser.print_help()


def _cmd_init(cfg):
    dirs = [
        cfg["foundry"]["synto_vault"],
        cfg["foundry"]["synthadoc_vault"],
        cfg["frontline"]["unified_vault"],
        cfg["frontline"]["llm_wiki_vault"],
        cfg["frontline"]["link_vault"],
    ]
    for d in dirs:
        Path(d).expanduser().mkdir(parents=True, exist_ok=True)
        print(f"[init] Ensured: {d}")

    # Init git in unified vault if strategy is git
    if cfg["sync"]["strategy"] == "git":
        unified = Path(cfg["frontline"]["unified_vault"]).expanduser()
        if not (unified / ".git").exists():
            subprocess.run(["git", "-C", str(unified), "init"], check=False)
            print(f"[init] Git init in {unified}")

    print("[init] Done. Now run 'synto init', 'llm-wiki init', and 'link init' manually for each tool.")


def _cmd_status(cfg):
    tools = ["synto", "llm-wiki", "synthadoc", "link"]
    print("--- Tool Availability ---")
    for t in tools:
        r = subprocess.run(["which", t], capture_output=True)
        status = "OK" if r.returncode == 0 else "MISSING"
        print(f"  {t}: {status}")

    print("\n--- Vault Sizes ---")
    for name, path in [
        ("synto-foundry", cfg["foundry"]["synto_vault"]),
        ("synthadoc-foundry", cfg["foundry"]["synthadoc_vault"]),
        ("unified-frontline", cfg["frontline"]["unified_vault"]),
        ("llm-wiki-frontline", cfg["frontline"]["llm_wiki_vault"]),
    ]:
        p = Path(path).expanduser()
        if p.exists():
            size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            print(f"  {name}: {size / 1_048_576:.1f} MB")
        else:
            print(f"  {name}: not found")

    print("\n--- Ollama ---")
    r = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    print(r.stdout if r.returncode == 0 else "Ollama not responding")
