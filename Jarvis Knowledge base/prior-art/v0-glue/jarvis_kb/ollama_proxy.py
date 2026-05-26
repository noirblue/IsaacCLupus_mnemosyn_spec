import asyncio
from collections import deque
from typing import Dict

import httpx
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
PROXY_CONFIG: Dict = {}


class PriorityQueueProxy:
    """Single-node Ollama with priority scheduling."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.queues = {
            "chat": deque(),
            "compile": deque(),
            "lint": deque(),
        }
        self.sem = asyncio.Semaphore(1)  # one Ollama job at a time
        self._worker = asyncio.create_task(self._loop())

    async def _loop(self):
        while True:
            fut, payload = await self._next_job()
            async with self.sem:
                try:
                    result = await self._forward(payload)
                    fut.set_result(result)
                except Exception as e:
                    fut.set_exception(e)

    async def _next_job(self):
        while True:
            if self.queues["chat"]:
                return self.queues["chat"].popleft()
            if self.queues["compile"]:
                return self.queues["compile"].popleft()
            if self.queues["lint"]:
                return self.queues["lint"].popleft()
            await asyncio.sleep(0.05)

    async def _forward(self, payload: Dict):
        async with httpx.AsyncClient() as client:
            # Support both /api/generate and /api/chat
            endpoint = payload.pop("_endpoint", "/api/generate")
            resp = await client.post(
                f"{self.base_url}{endpoint}",
                json=payload,
                timeout=600,
            )
            return resp.json()

    async def submit(self, priority: str, payload: Dict):
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        q = self.queues.get(priority, self.queues["compile"])
        q.append((fut, payload))
        return await fut


class RouterProxy:
    """Dual-node: route by priority header to Foundry or Frontline Ollama."""

    def __init__(self, foundry_url: str, frontline_url: str):
        self.foundry = foundry_url.rstrip("/")
        self.frontline = frontline_url.rstrip("/")

    async def submit(self, priority: str, payload: Dict):
        target = self.frontline if priority == "chat" else self.foundry
        async with httpx.AsyncClient() as client:
            endpoint = payload.pop("_endpoint", "/api/generate")
            resp = await client.post(
                f"{target}{endpoint}",
                json=payload,
                timeout=600,
            )
            return resp.json()


_proxy_instance = None


@app.on_event("startup")
async def startup():
    global _proxy_instance
    cfg = PROXY_CONFIG
    mode = cfg.get("proxy", {}).get("mode", "queue")
    if mode == "router":
        _proxy_instance = RouterProxy(
            cfg["foundry"]["ollama_url"],
            cfg["frontline"]["ollama_url"],
        )
    else:
        _proxy_instance = PriorityQueueProxy(cfg["foundry"]["ollama_url"])


@app.post("/api/generate")
@app.post("/api/chat")
async def proxy_generate(request: Request, x_priority: str = Header("compile")):
    body = await request.json()
    body["_endpoint"] = request.url.path
    result = await _proxy_instance.submit(x_priority, body)
    return JSONResponse(content=result)


@app.get("/api/tags")
async def proxy_tags():
    """Expose available models from the primary (foundry) Ollama."""
    url = PROXY_CONFIG["foundry"]["ollama_url"].rstrip("/")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{url}/api/tags", timeout=30)
        return JSONResponse(content=r.json())
