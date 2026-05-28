-- Mnemosyne Unified Schema
-- Version: 001-init
-- Description: Initial schema with six logical tables replacing four separate databases
-- Database: SQLite 3.35+ (WAL mode required)

-- Enable WAL mode for concurrent read/write without locking
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- =============================================================================
-- TABLE: pages
-- Description: Every markdown page, regardless of source or lifecycle stage
-- Replaces: Synto wiki + Synthadoc sources + LLM-WIKI-MCP context + Link graph nodes
-- =============================================================================
CREATE TABLE IF NOT EXISTS pages (
    id                  TEXT PRIMARY KEY,           -- Stable UUID v4
    path                TEXT UNIQUE NOT NULL,       -- Vault-relative path (e.g., "wiki/world/transformers.md")
    namespace           TEXT NOT NULL,              -- "self", "world", "synthesis", "memory"
    stage               TEXT NOT NULL,              -- "raw", "draft", "published", "archived"
    title               TEXT NOT NULL,              -- Human-readable title
    content_hash        TEXT,                     -- SHA-256 of content for hand-edit protection
    maturity            TEXT DEFAULT 'seed',        -- "seed", "refining", "established", "disputed"
    confidence          REAL DEFAULT 0.0,         -- 0.0 to 1.0
    source_type         TEXT,                     -- "notes", "paper", "textbook", "api_docs", "transcript"
    provenance          TEXT,                     -- JSON: [{source_file, line_start, line_end, extractor}]
    compiled_by         TEXT,                     -- Model name that compiled this page
    approved_at         TEXT,                     -- ISO 8601 timestamp or NULL
    rejected_count      INTEGER DEFAULT 0,        -- Accumulated rejections
    rejection_feedback  TEXT,                     -- Prompt injection for recompile
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- Indexes for pages
CREATE INDEX IF NOT EXISTS idx_pages_namespace ON pages(namespace);
CREATE INDEX IF NOT EXISTS idx_pages_stage ON pages(stage);
CREATE INDEX IF NOT EXISTS idx_pages_maturity ON pages(maturity);
CREATE INDEX IF NOT EXISTS idx_pages_source_type ON pages(source_type);
CREATE INDEX IF NOT EXISTS idx_pages_approved_at ON pages(approved_at);

-- =============================================================================
-- TABLE: links
-- Description: Graph edges — wikilinks, citations, semantic relationships, memory links
-- Replaces: Link graph edges + Synto cross-references + manual wikilink tracking
-- =============================================================================
CREATE TABLE IF NOT EXISTS links (
    id          TEXT PRIMARY KEY,                   -- Stable UUID v4
    source_id   TEXT NOT NULL,                      -- FK → pages.id (origin page)
    target_id   TEXT NOT NULL,                      -- FK → pages.id (destination page)
    link_type   TEXT NOT NULL,                      -- "wikilink", "citation", "semantic", "memory"
    context     TEXT,                               -- Surrounding text or relationship description
    created_at  TEXT DEFAULT (datetime('now')),

    FOREIGN KEY (source_id) REFERENCES pages(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES pages(id) ON DELETE CASCADE
);

-- Indexes for links
CREATE INDEX IF NOT EXISTS idx_links_source ON links(source_id);
CREATE INDEX IF NOT EXISTS idx_links_target ON links(target_id);
CREATE INDEX IF NOT EXISTS idx_links_type ON links(link_type);

-- Prevent duplicate links between same source-target-type
CREATE UNIQUE INDEX IF NOT EXISTS idx_links_unique 
    ON links(source_id, target_id, link_type);

-- =============================================================================
-- TABLE: jobs
-- Description: Priority queue for all LLM work — ingest, compile, lint, audit, query
-- Replaces: Ad-hoc script scheduling + Ollama contention management
-- =============================================================================
CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,               -- Stable UUID v4
    job_type        TEXT NOT NULL,                  -- "ingest", "compile", "lint", "audit", "query"
    priority        INTEGER NOT NULL DEFAULT 3,    -- 1=query (highest), 2=compile, 3=lint/audit/ingest
    status          TEXT NOT NULL DEFAULT 'pending', -- "pending", "running", "completed", "failed", "cancelled"
    payload         TEXT,                           -- JSON: job-specific parameters
    result          TEXT,                           -- JSON: job output or error details
    created_at      TEXT DEFAULT (datetime('now')),
    started_at      TEXT,                           -- When worker picked up the job
    completed_at    TEXT,                           -- When job finished or failed
    worker_id       TEXT                            -- Identifier for the worker process
);

-- Indexes for jobs
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(priority);
CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);

-- Query to fetch next pending job by priority (used by job queue worker)
-- SELECT * FROM jobs WHERE status = 'pending' ORDER BY priority ASC, created_at ASC LIMIT 1;

-- =============================================================================
-- TABLE: conversations
-- Description: Query/ask history with token budgets and cost tracking
-- Replaces: LLM-WIKI-MCP conversation history + ad-hoc chat logs
-- =============================================================================
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,                   -- Stable UUID v4
    session_id  TEXT NOT NULL,                      -- Grouping ID for multi-turn conversations
    role        TEXT NOT NULL,                      -- "user", "assistant", "system", "tool"
    content     TEXT NOT NULL,                      -- Message content
    model       TEXT,                               -- Model used for this turn
    tokens_used INTEGER DEFAULT 0,                  -- Token count for this message
    cost        REAL DEFAULT 0.0,                   -- Estimated cost in USD
    timestamp   TEXT DEFAULT (datetime('now'))
);

-- Indexes for conversations
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations(timestamp);
CREATE INDEX IF NOT EXISTS idx_conversations_model ON conversations(model);

-- =============================================================================
-- TABLE: audit_log
-- Description: Every LLM call, cost, latency, and content hash for provenance
-- Replaces: Synthadoc audit trail + manual cost tracking
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id          TEXT PRIMARY KEY,                   -- Stable UUID v4
    job_id      TEXT,                               -- FK → jobs.id (optional, links to triggering job)
    operation   TEXT NOT NULL,                      -- "ingest", "compile", "audit", "query", "publish"
    model       TEXT NOT NULL,                      -- Model name and version
    input_hash  TEXT,                               -- SHA-256 of input prompt/content
    output_hash TEXT,                               -- SHA-256 of output content
    latency_ms  INTEGER,                            -- Wall-clock milliseconds
    cost        REAL DEFAULT 0.0,                   -- Estimated cost in USD
    timestamp   TEXT DEFAULT (datetime('now')),

    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL
);

-- Indexes for audit_log
CREATE INDEX IF NOT EXISTS idx_audit_job ON audit_log(job_id);
CREATE INDEX IF NOT EXISTS idx_audit_operation ON audit_log(operation);
CREATE INDEX IF NOT EXISTS idx_audit_model ON audit_log(model);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);

-- =============================================================================
-- TABLE: contradictions
-- Description: Flagged conflicts between sources for human resolution
-- Replaces: Manual contradiction tracking + Synthadoc conflict detection
-- =============================================================================
CREATE TABLE IF NOT EXISTS contradictions (
    id          TEXT PRIMARY KEY,                   -- Stable UUID v4
    page_a_id   TEXT NOT NULL,                      -- FK → pages.id (first conflicting page)
    page_b_id   TEXT NOT NULL,                      -- FK → pages.id (second conflicting page)
    severity    TEXT NOT NULL DEFAULT 'warning',   -- "blocking", "warning", "info"
    description TEXT NOT NULL,                      -- Human-readable explanation of the conflict
    detected_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT,                               -- NULL until human resolves
    resolved_by TEXT,                               -- Human or agent that resolved it

    FOREIGN KEY (page_a_id) REFERENCES pages(id) ON DELETE CASCADE,
    FOREIGN KEY (page_b_id) REFERENCES pages(id) ON DELETE CASCADE
);

-- Indexes for contradictions
CREATE INDEX IF NOT EXISTS idx_contr_a ON contradictions(page_a_id);
CREATE INDEX IF NOT EXISTS idx_contr_b ON contradictions(page_b_id);
CREATE INDEX IF NOT EXISTS idx_contr_severity ON contradictions(severity);
CREATE INDEX IF NOT EXISTS idx_contr_resolved ON contradictions(resolved_at);

-- Prevent duplicate contradiction pairs (undirected)
CREATE UNIQUE INDEX IF NOT EXISTS idx_contr_unique 
    ON contradictions(
        CASE WHEN page_a_id < page_b_id THEN page_a_id ELSE page_b_id END,
        CASE WHEN page_a_id < page_b_id THEN page_b_id ELSE page_a_id END
    );

-- =============================================================================
-- VIEWS
-- =============================================================================

-- Published pages ready for agent consumption
CREATE VIEW IF NOT EXISTS v_published_pages AS
SELECT * FROM pages WHERE stage = 'published' ORDER BY namespace, title;

-- Pending jobs ordered by priority
CREATE VIEW IF NOT EXISTS v_pending_jobs AS
SELECT * FROM jobs WHERE status = 'pending' ORDER BY priority ASC, created_at ASC;

-- Unresolved contradictions
CREATE VIEW IF NOT EXISTS v_open_contradictions AS
SELECT 
    c.*,
    pa.title as page_a_title,
    pb.title as page_b_title
FROM contradictions c
JOIN pages pa ON c.page_a_id = pa.id
JOIN pages pb ON c.page_b_id = pb.id
WHERE c.resolved_at IS NULL
ORDER BY c.severity, c.detected_at;

-- Recent audit summary
CREATE VIEW IF NOT EXISTS v_audit_summary AS
SELECT 
    operation,
    model,
    COUNT(*) as call_count,
    SUM(latency_ms) as total_latency_ms,
    SUM(cost) as total_cost,
    MAX(timestamp) as last_call
FROM audit_log
GROUP BY operation, model
ORDER BY last_call DESC;

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Auto-update updated_at on pages modification
CREATE TRIGGER IF NOT EXISTS trg_pages_updated
AFTER UPDATE ON pages
BEGIN
    UPDATE pages SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- =============================================================================
-- INITIAL DATA (optional seed values)
-- =============================================================================

-- Insert a root configuration page
INSERT OR IGNORE INTO pages (id, path, namespace, stage, title, source_type, maturity)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'wiki/self/mnemosyne-config.md',
    'self',
    'published',
    'Mnemosyne Configuration',
    'notes',
    'established'
);
