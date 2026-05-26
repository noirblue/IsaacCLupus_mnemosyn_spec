import asyncio
import json
import subprocess
import sys
from typing import Any, Dict, List

import httpx


class McpGateway:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.tools = self._build_tool_schema()

    def _build_tool_schema(self) -> List[Dict]:
        return [
            {
                "name": "kb_search",
                "description": "Search across all knowledge sources (Synto, Synthadoc, LLM-WIKI-MCP, Link).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "source": {"type": "string", "enum": ["self", "world", "all"], "default": "all"},
                        "top_k": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "kb_ask",
                "description": "Ask a question using the conversational knowledge bridge with history and token budgets.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "context_budget": {"type": "integer", "default": 24000},
                        "history_budget": {"type": "integer", "default": 3000},
                    },
                    "required": ["question"],
                },
            },
            {
                "name": "kb_ingest",
                "description": "Ingest a file or directory into the Foundry. PDF/DOCX -> Synthadoc; MD/TXT -> Synto.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "doc_type": {"type": "string", "default": "auto"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "kb_remember",
                "description": "Commit a memory to Link with optional tags.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}, "default": []},
                        "project": {"type": "string", "default": "jarvis"},
                    },
                    "required": ["content"],
                },
            },
            {
                "name": "kb_compile",
                "description": "Run the Synto compilation pipeline on the Foundry vault.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "vault": {"type": "string", "default": "synto"},
                        "auto_approve": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "kb_audit",
                "description": "Run validation and lint across the knowledge base.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "scope": {"type": "string", "enum": ["self", "world", "all"], "default": "all"},
                    },
                },
            },
        ]

    async def run(self):
        while True:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            try:
                req = json.loads(line)
                resp = await self._handle(req)
            except json.JSONDecodeError as e:
                resp = {"jsonrpc": "2.0", "error": {"code": -32700, "message": str(e)}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

    async def _handle(self, req: Dict) -> Dict:
        id_ = req.get("id")
        method = req.get("method", "")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": id_,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {"name": "jarvis-kb-gateway", "version": "0.1.0"},
                },
            }

        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": id_, "result": {"tools": self.tools}}

        if method == "tools/call":
            return await self._call_tool(req["params"]["name"], req["params"].get("arguments", {}), id_)

        return {"jsonrpc": "2.0", "id": id_, "error": {"code": -32601, "message": f"Method {method} not found"}}

    async def _call_tool(self, name: str, args: Dict, id_) -> Dict:
        try:
            handler = {
                "kb_search": self._tool_search,
                "kb_ask": self._tool_ask,
                "kb_ingest": self._tool_ingest,
                "kb_remember": self._tool_remember,
                "kb_compile": self._tool_compile,
                "kb_audit": self._tool_audit,
            }.get(name)
            if not handler:
                raise ValueError(f"Unknown tool: {name}")
            result = await handler(args)
            return {
                "jsonrpc": "2.0",
                "id": id_,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": id_,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {e}"}],
                    "isError": True,
                },
            }

    # --- Tool implementations ---

    async def _tool_search(self, args: Dict) -> Dict:
        q = args["query"]
        source = args.get("source", "all")
        results = []

        # LLM-WIKI-MCP search via CLI
        vault = self.cfg["frontline"]["llm_wiki_vault"]
        r = subprocess.run(
            ["llm-wiki", "--vault", vault, "search", q],
            capture_output=True, text=True, timeout=30
        )
        results.append({"backend": "llm-wiki-mcp", "output": r.stdout, "stderr": r.stderr})

        # Link query via HTTP if available
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "http://localhost:3000/api/query",  # adjust Link port
                    json={"q": q, "limit": args.get("top_k", 5)},
                    timeout=10,
                )
                results.append({"backend": "link", "output": resp.json()})
        except Exception as e:
            results.append({"backend": "link", "error": str(e)})

        return {"query": q, "source": source, "results": results}

    async def _tool_ask(self, args: Dict) -> Dict:
        vault = self.cfg["frontline"]["llm_wiki_vault"]
        # Set context budgets via CLI if supported, otherwise rely on defaults
        r = subprocess.run(
            ["llm-wiki", "--vault", vault, "ask", args["question"]],
            capture_output=True, text=True, timeout=120
        )
        return {
            "question": args["question"],
            "answer": r.stdout,
            "stderr": r.stderr,
            "context_budget": args.get("context_budget", 24000),
        }

    async def _tool_ingest(self, args: Dict) -> Dict:
        path = args["path"]
        doc_type = args.get("doc_type", "auto")
        ext = path.lower().split(".")[-1] if "." in path else ""

        if ext in {"pdf", "docx", "pptx", "xlsx"} or doc_type != "auto":
            # Route to Synthadoc Foundry
            r = subprocess.run(
                ["synthadoc", "ingest", path, "--type", doc_type],
                capture_output=True, text=True, timeout=300
            )
            backend = "synthadoc"
        else:
            # Route to Synto Foundry
            vault = self.cfg["foundry"]["synto_vault"]
            r = subprocess.run(
                ["synto", "add", path, "--vault", vault],
                capture_output=True, text=True, timeout=60
            )
            backend = "synto"

        return {"backend": backend, "path": path, "stdout": r.stdout, "stderr": r.stderr}

    async def _tool_remember(self, args: Dict) -> Dict:
        # Link: remember_memory via HTTP or CLI
        payload = {
            "content": args["content"],
            "tags": args.get("tags", []),
            "project": args.get("project", "jarvis"),
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "http://localhost:3000/api/remember",
                    json=payload,
                    timeout=30,
                )
                return {"backend": "link", "result": resp.json()}
        except Exception:
            # Fallback to CLI
            r = subprocess.run(
                ["link", "remember", args["content"], "--tags", ",".join(args.get("tags", []))],
                capture_output=True, text=True, timeout=30
            )
            return {"backend": "link-cli", "stdout": r.stdout, "stderr": r.stderr}

    async def _tool_compile(self, args: Dict) -> Dict:
        vault = self.cfg["foundry"]["synto_vault"]
        cmd = ["synto", "run", "--vault", vault]
        if args.get("auto_approve"):
            cmd.append("--auto-approve")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return {"backend": "synto", "stdout": r.stdout, "stderr": r.stderr}

    async def _tool_audit(self, args: Dict) -> Dict:
        scope = args.get("scope", "all")
        results = []

        if scope in {"self", "all"}:
            vault = self.cfg["foundry"]["synto_vault"]
            r = subprocess.run(["synto", "eval", "--vault", vault], capture_output=True, text=True, timeout=120)
            results.append({"backend": "synto-eval", "output": r.stdout})

        if scope in {"world", "all"}:
            r = subprocess.run(["synthadoc", "lint"], capture_output=True, text=True, timeout=300)
            results.append({"backend": "synthadoc-lint", "output": r.stdout})

        # Link validate
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post("http://localhost:3000/api/validate", timeout=60)
                results.append({"backend": "link-validate", "output": resp.json()})
        except Exception as e:
            results.append({"backend": "link-validate", "error": str(e)})

        return {"scope": scope, "results": results}
