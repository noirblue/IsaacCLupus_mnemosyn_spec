# 02: Tokio Job Queue with Ollama Priority Scheduling

## Question

How do we build a priority job queue in Rust with Tokio that prevents Ollama GPU deadlock, handles crash recovery, and integrates cleanly with Mnemosyne's unified SQLite `state.db`?

## Answer

There are three viable approaches. Each solves a different slice of the problem. The recommended architecture combines Option 2 (SQLite-backed queue) with Option 3 (dual Tokio runtimes) to achieve both persistence and latency isolation without external infrastructure.

---

## Why This Matters for Mnemosyne

The Python glue layer failed on concurrency because:

- Four tools hit `localhost:11434` simultaneously
- A 70B compile job pegged the GPU for 10 minutes
- Chat queries queued behind it and timed out
- SQLite `database is locked` errors under concurrent writes

A Rust core must solve this at the architecture layer, not with better duct tape.

---

## Option 1: `async-priority-channel` (In-Memory Only)

A drop-in replacement for `async_channel` with native priority ordering.

### How It Works

```rust
use async_priority_channel::{bounded, Sender, Receiver};

// Lower u32 = higher priority (configurable)
let (tx, rx) = bounded::<Job, u32>(100);

// Chat query: priority 1 (highest)
tx.send(chat_job, 1).await?;

// Compile job: priority 2
tx.send(compile_job, 2).await?;

// Lint job: priority 3 (lowest)
tx.send(lint_job, 3).await?;

// Receiver always yields highest priority first
let (job, priority) = rx.recv().await?;
```

### What It Gives You

| Feature | Status |
|---|---|
| Priority ordering | Native, zero boilerplate |
| Async/await | First-class |
| Backpressure | Bounded channel capacity |

### What It Does NOT Give You

| Feature | Status | Why It Matters |
|---|---|---|
| Persistence | None | Crash loses all queued jobs |
| Crash recovery | None | `running` jobs vanish |
| Multi-process | No | Single consumer only |
| Audit trail | No | No record of what ran when |

### Verdict

Useful for **in-process routing only** — e.g., prioritizing which handler gets a job first inside the MCP server. Not sufficient for Mnemosyne's core queue.

---

## Option 2: SQLite-Backed Queue (Recommended Core)

Use `state.db` itself as the job queue. This is what `ollama-queue` does, and what the Python glue attempted unsuccessfully.

### Schema Extension

```sql
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    job_type TEXT,           -- 'query', 'compile', 'lint', 'ingest', 'audit'
    priority INTEGER,        -- 1=chat, 2=compile, 3=lint/audit/ingest
    payload TEXT,            -- JSON: model, prompt, temperature, etc.
    status TEXT,             -- 'pending', 'running', 'done', 'failed', 'cancelled'
    model_request TEXT,      -- 'ollama:11434/qwen3:30b' or 'ollama:11435/llama3.3:70b'
    result TEXT,             -- JSON response or error
    error_message TEXT,      -- human-readable on failure
    cost_ms INTEGER,         -- actual wall time
    tokens_in INTEGER,
    tokens_out INTEGER,
    created_at TEXT,         -- ISO 8601
    started_at TEXT,
    finished_at TEXT,
    worker_id TEXT,          -- which runtime/process claimed it
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3
);

-- Index for fast dequeue
CREATE INDEX idx_jobs_dequeue 
ON jobs(status, priority ASC, created_at ASC) 
WHERE status = 'pending';
```

### Dequeue Implementation

```rust
use tokio::sync::Semaphore;
use tokio_rusqlite::Connection;
use std::time::Duration;

struct JobQueue {
    db: Connection,
    // Limits concurrent Ollama calls to prevent GPU OOM
    ollama_sem: Semaphore,
}

impl JobQueue {
    async fn dequeue(&self, worker_id: &str) -> Option<Job> {
        self.db.call(|conn| {
            // Atomic claim: find highest-priority pending job, mark running
            let mut stmt = conn.prepare(
                "UPDATE jobs 
                 SET status = 'running', started_at = datetime('now'), worker_id = ?
                 WHERE id = (
                     SELECT id FROM jobs 
                     WHERE status = 'pending' 
                     ORDER BY priority ASC, created_at ASC 
                     LIMIT 1
                 )
                 RETURNING id, job_type, priority, payload, model_request"
            )?;

            stmt.query_row([worker_id], |row| {
                Ok(Job {
                    id: row.get(0)?,
                    job_type: row.get(1)?,
                    priority: row.get(2)?,
                    payload: row.get(3)?,
                    model_request: row.get(4)?,
                })
            }).optional()
        }).await.ok().flatten()
    }

    async fn run_job(&self, job: Job) -> Result<(), Error> {
        // Acquire Ollama slot (prevents GPU contention)
        let _permit = self.ollama_sem.acquire().await?;

        // Call Ollama via HTTP
        let result = call_ollama(&job.model_request, &job.payload).await;

        // Record result
        self.db.call(move |conn| {
            match result {
                Ok(response) => {
                    conn.execute(
                        "UPDATE jobs SET status='done', finished_at=datetime('now'), 
                         result=?, cost_ms=?, tokens_in=?, tokens_out=?
                         WHERE id=?",
                        params![
                            response.text,
                            response.latency_ms,
                            response.tokens_in,
                            response.tokens_out,
                            job.id
                        ]
                    )?;
                }
                Err(e) => {
                    if job.retry_count < job.max_retries {
                        conn.execute(
                            "UPDATE jobs SET status='pending', retry_count=retry_count+1 
                             WHERE id=?",
                            [job.id]
                        )?;
                    } else {
                        conn.execute(
                            "UPDATE jobs SET status='failed', finished_at=datetime('now'), 
                             error_message=? WHERE id=?",
                            params![e.to_string(), job.id]
                        )?;
                    }
                }
            }
            Ok(())
        }).await?;

        Ok(())
    }
}
```

### Crash Recovery

```rust
impl JobQueue {
    async fn reclaim_orphans(&self, worker_id: &str, timeout_secs: u64) -> usize {
        self.db.call(move |conn| {
            let mut stmt = conn.prepare(
                "UPDATE jobs 
                 SET status = 'pending', worker_id = NULL, retry_count = retry_count + 1
                 WHERE status = 'running' 
                 AND worker_id = ?
                 AND datetime(started_at) < datetime('now', ? || ' seconds')
                 RETURNING id"
            )?;

            let rows: Vec<i64> = stmt
                .query_map(params![worker_id, format!("-{}", timeout_secs)], |row| row.get(0))?
                .collect::<Result<Vec<_>, _>>()?;

            Ok(rows.len())
        }).await.unwrap_or(0)
    }
}
```

On startup, each worker reclaims jobs from crashed workers:

```rust
// Reclaim jobs from workers that died >5 minutes ago
queue.reclaim_orphans("foundry-1", 300).await;
```

### What It Gives You

| Feature | Status | Implementation |
|---|---|---|
| Persistence | Yes | SQLite `jobs` table |
| Crash recovery | Yes | `reclaim_orphans()` + `retry_count` |
| Priority ordering | Yes | `ORDER BY priority ASC, created_at ASC` |
| Audit trail | Yes | Every job logged with cost, tokens, latency |
| Multi-worker | Yes | `worker_id` column for distributed claims |
| Backpressure | Yes | `Semaphore` limits concurrent Ollama calls |
| Job cancellation | Yes | `status = 'cancelled'` update |
| Progress tracking | Yes | `status` transitions visible in real-time |

### What It Costs You

| Cost | Mitigation |
|---|---|
| SQLite write on every dequeue | WAL mode + `synchronous=NORMAL` |
| Polling loop for new jobs | `NOTIFY` equivalent: check every 100ms, or use `tokio::sync::Notify` for in-process signal |
| Schema complexity | Already needed for audit trail — no extra table |

### Verdict

**This is Mnemosyne's core queue.** It uses the same database as everything else, provides full auditability, and survives crashes. The `ollama_sem` prevents GPU contention without external orchestration.

---

## Option 3: Dual Tokio Runtimes (Latency Isolation)

The DatenLord approach: separate thread pools so heavy jobs cannot starve interactive ones.

### Architecture

```rust
use tokio::runtime::{Builder, Runtime};

// FRONTLINE: low-latency chat queries
// 4 threads, high OS priority, never blocked by compilation
let frontline = Builder::new_multi_thread()
    .worker_threads(4)
    .thread_name("frontline")
    .on_thread_start(|| {
        // Optional: boost OS priority for these threads
        set_thread_priority(ThreadPriority::Max);
    })
    .build()
    .unwrap();

// FOUNDRY: heavy compilation, lint, audit
// 8 threads, background priority, can peg CPU without hurting frontline
let foundry = Builder::new_multi_thread()
    .worker_threads(8)
    .thread_name("foundry")
    .on_thread_start(|| {
        set_thread_priority(ThreadPriority::Min);
    })
    .build()
    .unwrap();
```

### Communication Between Runtimes

Two runtimes cannot share `tokio::sync` primitives. Use SQLite as the bridge:

```rust
// Frontline receives MCP request, writes job to SQLite
frontline.spawn(async {
    let job = Job::new_chat(query);
    db.call(|conn| job.insert(conn)).await?;
    // Signal foundry that work is available
    foundry_notify.notify_one();
});

// Foundry polls SQLite for compile/lint jobs
foundry.spawn(async {
    loop {
        foundry_notify.notified().await;
        while let Some(job) = queue.dequeue("foundry-1").await {
            queue.run_job(job).await;
        }
    }
});
```

### What It Gives You

| Feature | Status |
|---|---|
| OS-level isolation | Yes — different thread pools, different priorities |
| Compile job cannot starve chat | Yes — separate CPU scheduling |
| Chat latency predictable | Yes — frontline threads never blocked |

### What It Costs You

| Cost | Mitigation |
|---|---|
| Cannot share `tokio::sync::Mutex` across runtimes | Use SQLite as single source of truth |
| Cannot share `tokio::sync::Notify` across runtimes | Use `std::sync::Arc<std::sync::Condvar>` or polling |
| Higher memory (two thread pools) | Negligible on 128 GB Strix Halo |
| More complex deployment | Optional — single runtime works for hobbyists |

### Verdict

**Use this for production deployments on high-end hardware** (Strix Halo, dual-node setups). For single-machine hobbyists, Option 2 alone is sufficient. The dual-runtime is an **optimization**, not a requirement.

---

## Recommended Architecture: Combined

For Mnemosyne's reference implementation, combine Option 2 and Option 3:

```
┌─────────────────────────────────────────┐
│  FRONTLINE RUNTIME (4 threads, max priority)  │
│  • MCP/REST API handlers                │
│  • Chat query dequeue (priority 1)     │
│  • Fast SQLite reads                    │
│  • `kb_ask`, `kb_search` tools          │
│  • Never blocked by compilation          │
└─────────────┬───────────────────────────┘
              │ SQLite WAL (reads)
┌─────────────▼───────────────────────────┐
│  SHARED state.db                          │
│  • jobs table: priority, status, payload  │
│  • pages, links, conversations, audit      │
│  • WAL mode: readers don't block writers  │
└─────────────┬───────────────────────────┘
              │ SQLite WAL (writes)
┌─────────────▼───────────────────────────┐
│  FOUNDRY RUNTIME (8 threads, min priority)  │
│  • Compile jobs (priority 2)             │
│  • Lint/audit jobs (priority 3)          │
│  • Ingest jobs (priority 3)            │
│  • Heavy SQLite writes                   │
│  • `ollama_sem` = 1 (GPU serialized)     │
└─────────────────────────────────────────┘
```

### Why This Works

| Problem | Solution |
|---|---|
| Ollama GPU deadlock | `Semaphore(1)` in Foundry runtime serializes GPU access |
| Chat query starvation | Frontline runtime never runs compile jobs |
| SQLite locking | WAL mode allows concurrent readers + single writer |
| Crash recovery | `reclaim_orphans()` + `retry_count` in `jobs` table |
| Audit trail | Every job, every cost, every token logged automatically |
| Multi-node sync | SQLite file syncs via rsync/git; job queue reclaims on startup |

---

## Priority Levels

| Priority | Job Type | Max Concurrent | Preemptible | Runtime |
|---|---|---|---|---|
| 1 | `query` (chat) | 2 | Yes | Frontline |
| 2 | `compile` | 1 | No | Foundry |
| 3 | `lint`, `audit`, `ingest` | 2 | No | Foundry |

Preemptible means a new priority-1 job can cancel a running priority-1 job if it exceeds timeout. Compile jobs are never preempted — they run to completion or failure.

---

## What About External Queues?

| Tool | Why Not Use It |
|---|---|
| Redis | Adds external dependency; violates local-first principle |
| RabbitMQ | Same; also overkill for single-machine deployment |
| `pg-boss` | Requires PostgreSQL; SQLite is sufficient |
| `beanstalkd` | External process; more moving parts |

SQLite with WAL mode is **faster than Redis for local workloads** under 10K ops/sec. Mnemosyne's job queue will see hundreds of jobs per day, not millions per second. External queues are premature optimization.

---

## Production Precedents

| Tool | Pattern | Scale |
|---|---|---|
| `atuin` | SQLite WAL + async queue | Millions of shell histories |
| `sccache` | SQLite + job queue for compiler artifacts | CI/CD scale |
| `ruff` | SQLite cache + parallel workers | Python ecosystem scale |
| `ollama-queue` | SQLite-backed LLM job queue | Proven in production |

---

## Conclusion

A production-ready priority job queue for Mnemosyne requires **no external infrastructure**:

- **SQLite `jobs` table** provides persistence, priority ordering, crash recovery, and audit trail
- **`tokio::sync::Semaphore`** prevents Ollama GPU contention
- **Optional dual runtimes** isolate latency-critical chat from batch compilation
- **WAL mode** allows concurrent readers (Frontline) during writes (Foundry)

The Rust implementation is not just viable — it is **cleaner than the Python equivalent** because Rust's ownership model eliminates the SQLite locking deadlocks that plagued the 450-line glue layer. The entire queue fits in ~200 lines of Rust with `rusqlite` + `tokio`.

This is not theoretical. The `ollama-queue` project proves SQLite-backed LLM job queues work in production today. Mnemosyne's queue is that pattern, unified into `state.db`.
