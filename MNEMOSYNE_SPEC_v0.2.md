# MNEMOSYNE SPEC — v0.2 DRAFT
## Integration Roadmap: External Concepts from Knowledge-OS Ecosystem
**Date:** 2026-05-28 | **Status:** Draft for Review | **Previous:** v0.1 (2026-05-27)

---

## Executive Summary

v0.1 established Mnemosyne as a local-first semantic memory OS with a Rust core and Python satellites. After reviewing four adjacent projects in the knowledge-OS ecosystem, v0.2 identifies specific concepts worth integrating as **additive layers** — not architectural pivots. The core remains: one vault, one schema, one API, Rust core + Python satellites, local-first, human-curated.

The four external concepts are:
1. **Epistemic governance** (aminglab/knowledge-os) — claim/verdict/dissent lifecycle
2. **Agent governance hooks** (Fly-Carrot/KnowledgeOS) — write guards, receipts, observability
3. **Hierarchical conversation memory** (BAI-LAB/MemoryOS) — heat-decay tiers, implicit profiling
4. **Cryptographic provenance** (OriginTrail/DKG) — optional Merkle anchoring for external verification

Each is mapped to a Phase, scoped to a subsystem, and bounded by what Mnemosyne will NOT adopt.

---

## 1. Versioning Strategy

### 1.1 Spec Versioning

| Version | Date | Focus | Status |
|---|---|---|---|
| v0.1 | 2026-05-27 | Core architecture, 7-layer design, Rust+Python split | Published |
| **v0.2** | 2026-05-28 | External concept integration, governance layers, conversation memory | **Draft** |
| v0.3 | TBD | Implementation feedback, schema refinements, API contract updates | Planned |
| v1.0 | TBD | Stable architecture, reference implementation complete | Target |

### 1.2 Schema Versioning

The `state.db` schema is versioned independently of the spec:

```
state.db
├── _schema_version table (integer, monotonic)
├── _schema_migrations table (applied_at, migration_name, checksum)
└── [all other tables]
```

| Schema Version | Spec Version | Changes |
|---|---|---|
| 1 | v0.1 | Initial tables: pages, links, jobs, conversations, audit_log, contradictions |
| 2 | v0.2 | Add: claims, verdicts, dissents, write_guards, receipts, conversation_tiers, memory_heat |
| 3 | TBD | Add: knowledge_assets (optional DKG export), merkle_roots |

### 1.3 API Versioning

MCP and REST APIs are versioned via namespace:
- `kb_search_v1` → `kb_search_v2` (breaking changes)
- New tools added as `kb_govern_v1` (non-breaking)

---

## 2. Integration: aminglab/knowledge-os → Epistemic Governance

### 2.1 What to Adopt

| Concept | Mnemosyne Mapping | Phase |
|---|---|---|
| Claim as governed object | New `claims` table + `claim_links` edge type | Phase 3 |
| Verdict (endorse/reject/downgrade) | New `verdicts` table, linked to claims | Phase 3 |
| Dissent as first-class object | New `dissents` table, linked to claims | Phase 3 |
| Selective disclosure (private/team/public) | Add `visibility` enum to `pages` and `claims` | Phase 3 |
| Knowledge snapshots | `packs/` export with versioned claim state | Phase 3 |

### 2.2 Schema Additions

```sql
-- New table: claims
CREATE TABLE claims (
    id TEXT PRIMARY KEY,
    page_id TEXT REFERENCES pages(id),
    claim_text TEXT NOT NULL,
    confidence REAL CHECK (confidence BETWEEN 0 AND 1),
    status TEXT CHECK (status IN ('proposed', 'endorsed', 'disputed', 'rejected', 'superseded')),
    visibility TEXT CHECK (visibility IN ('private', 'team', 'public')) DEFAULT 'private',
    proposed_at TEXT,
    verdict_at TEXT,
    superseded_by TEXT REFERENCES claims(id),
    provenance TEXT -- JSON: [{source, line_start, line_end, extractor}]
);

-- New table: verdicts
CREATE TABLE verdicts (
    id TEXT PRIMARY KEY,
    claim_id TEXT REFERENCES claims(id),
    verdict_type TEXT CHECK (verdict_type IN ('endorse', 'reject', 'downgrade', 'supersede')),
    rationale TEXT,
    verdict_by TEXT, -- user_id or agent_id
    verdict_at TEXT,
    evidence_refs TEXT -- JSON: [claim_id, page_id, etc.]
);

-- New table: dissents
CREATE TABLE dissents (
    id TEXT PRIMARY KEY,
    claim_id TEXT REFERENCES claims(id),
    dissent_text TEXT NOT NULL,
    counter_evidence TEXT,
    severity TEXT CHECK (severity IN ('minor', 'moderate', 'major', 'critical')),
    proposed_by TEXT,
    proposed_at TEXT,
    status TEXT CHECK (status IN ('open', 'addressed', 'overruled')) DEFAULT 'open'
);
```

### 2.3 What NOT to Adopt

- **Team cockpit model** — Mnemosyne is solo-first; multi-user governance is Phase 4+
- **Public case layer** — selective disclosure is per-page, not a separate publication system
- **Governance grammar as primary interface** — governance is an API layer, not the main UX

### 2.4 Integration Point

The audit engine (Layer 4) gains a **governance pass** after adversarial review:

```
Audit Pipeline (v0.2):
  1. Structural lint
  2. Contradiction detection
  3. Adversarial review
  4. [NEW] Claim extraction → propose claims to governance queue
  5. [NEW] Human verdict (endorse/reject/downgrade)
  6. Publish or return to draft
```

---

## 3. Integration: Fly-Carrot/KnowledgeOS → Agent Governance Hooks

### 3.1 What to Adopt

| Concept | Mnemosyne Mapping | Phase |
|---|---|---|
| Write guard | Extend `content_hash` → `write_guard` policy | Phase 2 |
| Receipt | New `receipts` table, linked to jobs | Phase 2 |
| Intent → route → dispatch | Extend `jobs` table with intent/routing metadata | Phase 2 |
| Phase log | Extend `audit_log` with structured phase data | Phase 2 |

### 3.2 Schema Additions

```sql
-- Extended: pages table (add write_guard policy)
ALTER TABLE pages ADD COLUMN write_guard TEXT CHECK (write_guard IN ('open', 'protected', 'frozen')) DEFAULT 'open';
-- open: any agent can write
-- protected: agent can write only if content_hash matches expected
-- frozen: only human can write (hand-edit protection)

-- New table: receipts
CREATE TABLE receipts (
    id TEXT PRIMARY KEY,
    job_id TEXT REFERENCES jobs(id),
    agent_id TEXT,
    intent TEXT, -- 'ingest', 'compile', 'audit', 'publish'
    route TEXT, -- which satellite/tool was invoked
    dispatch_at TEXT,
    completion_at TEXT,
    status TEXT CHECK (status IN ('dispatched', 'running', 'succeeded', 'failed', 'timeout')),
    artifacts TEXT, -- JSON: {output_files, hashes, metrics}
    phase_log TEXT -- JSON: [{phase, timestamp, duration_ms, status}]
);

-- Extended: jobs table (add intent/routing)
ALTER TABLE jobs ADD COLUMN intent TEXT;
ALTER TABLE jobs ADD COLUMN routed_to TEXT; -- satellite or tool name
ALTER TABLE jobs ADD COLUMN receipt_id TEXT REFERENCES receipts(id);
```

### 3.3 What NOT to Adopt

- **Boot/kernel/shell/driver abstraction** — Mnemosyne is not an OS-inside-an-OS
- **Distracted-agent prevention** — out of scope; agent behavior is the client's responsibility
- **Material/src separation** — Mnemosyne's `raw/` + `wiki/` + `memory/` is sufficient

### 3.4 Integration Point

The `jobs` queue (Layer 2) becomes observable:

```
Job Lifecycle (v0.2):
  1. Intent submitted (agent or human)
  2. Route selected (which satellite/tool)
  3. Receipt created
  4. Dispatch to satellite
  5. Phase logging (per sub-task)
  6. Receipt updated with artifacts
  7. Audit log entry created
```

---

## 4. Integration: BAI-LAB/MemoryOS → Hierarchical Conversation Memory

### 4.1 What to Adopt

| Concept | Mnemosyne Mapping | Phase |
|---|---|---|
| Short-term memory (7 turns) | `conversations` table with `tier='short'` | Phase 2 |
| Mid-term memory (heat decay) | `conversations` table with `heat_score` + decay logic | Phase 2 |
| Long-term memory (capacity 100) | `memory/committed/` with capacity limit + promotion queue | Phase 2 |
| Implicit profile extraction | `conversations` → `memory/inbox/` pipeline with fast model | Phase 2 |

### 4.2 Schema Additions

```sql
-- Extended: conversations table
ALTER TABLE conversations ADD COLUMN tier TEXT CHECK (tier IN ('short', 'mid', 'long')) DEFAULT 'short';
ALTER TABLE conversations ADD COLUMN heat_score REAL DEFAULT 0.0; -- 0.0 to 1.0
ALTER TABLE conversations ADD COLUMN last_referenced_at TEXT;
ALTER TABLE conversations ADD COLUMN decay_rate REAL DEFAULT 0.1; -- per day
ALTER TABLE conversations ADD COLUMN promoted_to_memory_id TEXT REFERENCES pages(id);

-- New table: user_profiles (implicit, extracted from conversations)
CREATE TABLE user_profiles (
    id TEXT PRIMARY KEY,
    key TEXT NOT NULL, -- 'job_title', 'location', 'interest', etc.
    value TEXT NOT NULL,
    confidence REAL CHECK (confidence BETWEEN 0 AND 1),
    source_conversation_ids TEXT, -- JSON: [conversation_id, ...]
    extracted_at TEXT,
    last_verified_at TEXT,
    status TEXT CHECK (status IN ('active', 'stale', 'superseded')) DEFAULT 'active'
);
```

### 4.3 What NOT to Adopt

- **ChromaDB as primary storage** — Mnemosyne uses SQLite + hybrid search, not vector-only
- **Capacity limit of 100 for long-term** — Mnemosyne's limit is configurable, not hardcoded
- **Per-session memory reset** — Mnemosyne conversations persist across sessions

### 4.4 Integration Point

The conversation layer (Layer 6) gains memory promotion:

```
Conversation Memory Pipeline (v0.2):
  1. Conversation logged to `conversations` (short-term)
  2. Fast model extracts key facts → `user_profiles` + proposed memories
  3. Heat score updated on reference
  4. Decay job runs daily (background)
  5. Hot mid-term memories promoted to `memory/inbox/`
  6. Human approves → `memory/committed/`
  7. Cold memories archived (retained for provenance)
```

---

## 5. Integration: OriginTrail/DKG → Cryptographic Provenance (Optional)

### 5.1 What to Adopt

| Concept | Mnemosyne Mapping | Phase |
|---|---|---|
| Merkle proof | Optional `merkle_root` field on `packs` export | Phase 4 |
| Knowledge Asset format | `packs/` export → RDF serialization + proof | Phase 4 |
| On-chain anchoring | Optional blockchain transaction per pack publish | Phase 4 |
| Self-attested → endorsed → consensus | `packs.trust_tier` enum | Phase 4 |

### 5.2 Schema Additions

```sql
-- Extended: packs table (Phase 4)
ALTER TABLE packs ADD COLUMN merkle_root TEXT; -- SHA-256 of serialized content
ALTER TABLE packs ADD COLUMN blockchain_tx_hash TEXT; -- optional anchor
ALTER TABLE packs ADD COLUMN trust_tier TEXT CHECK (trust_tier IN ('self_attested', 'endorsed', 'consensus_verified')) DEFAULT 'self_attested';
ALTER TABLE packs ADD COLUMN rdf_serialization TEXT; -- Turtle/JSON-LD export
```

### 5.3 What NOT to Adopt

- **TRAC token economics** — Mnemosyne has no tokens, no staking, no incentives
- **P2P gossip network** — Mnemosyne is local-first; networking is optional export
- **RDF as primary format** — Markdown remains canonical; RDF is export-only
- **Multi-node consensus** — Dual-node is Foundry/Frontline, not Byzantine consensus

### 5.4 Integration Point

The publish engine (Layer 5) gains an optional **external verification** step:

```
Publish Pipeline (v0.2, optional DKG mode):
  1. Article approved
  2. Compile pack export
  3. [OPTIONAL] Serialize to RDF
  4. [OPTIONAL] Compute Merkle root
  5. [OPTIONAL] Anchor to blockchain
  6. Publish pack to `packs/latest/`
  7. [OPTIONAL] Submit to DKG network
```

---

## 6. What Stays Unchanged

The following are **non-negotiable** and not modified by any integration:

| Principle | Rationale |
|---|---|
| **One vault** (`raw/`, `wiki/`, `memory/`, `packs/`) | External concepts are schema extensions, not new directories |
| **One schema** (`state.db`) | All additions are tables in the same database |
| **Rust core** | Performance-critical path unchanged |
| **Python satellites** | Permanent, not transitional |
| **Local-first** | No cloud dependency, no blockchain requirement |
| **Human-curated** | All governance actions default to human approval |
| **MCP + REST + CLI** | API surface expanded, not replaced |

---

## 7. Implementation Order

| Phase | Integration | Effort | Dependencies |
|---|---|---|---|
| Phase 1 (MVP) | None — core only | — | — |
| Phase 2 (Quality) | KnowledgeOS hooks + MemoryOS conversation memory | Low-Medium | Jobs queue, audit engine |
| Phase 3 (Agent-Native) | Knowledge-os epistemic governance | Medium | Claim extraction, verdict UI |
| Phase 4 (Ecosystem) | DKG cryptographic provenance (optional) | High | RDF serialization, blockchain adapter |

---

## 8. Open Questions

1. Should `user_profiles` be agent-visible or internal-only? If visible, how does it affect privacy?
2. Should verdicts be reversible? If a claim is endorsed then new evidence emerges, can it be downgraded?
3. Should heat-decay be configurable per-user or system-wide?
4. Should DKG anchoring be per-pack or per-claim? Per-pack is cheaper; per-claim is more granular.
5. How do we prevent governance fatigue — too many claims requiring human verdict?

---

## 9. Decision Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-28 | v0.2 spec drafted | External concept integration from four adjacent projects |
| 2026-05-28 | All integrations are additive, not architectural | Core principles (one vault, one schema, Rust+Python) are protected |
| 2026-05-28 | Knowledge-os governance deferred to Phase 3 | Requires claim extraction UI and human verdict workflow |
| 2026-05-28 | DKG integration optional and Phase 4 | Blockchain anchoring is not core to local-first mission |
| 2026-05-28 | MemoryOS heat-decay adopted for conversations | Low effort, high value for agent context retention |
| 2026-05-28 | KnowledgeOS write guards adopted for pages | Extends existing content_hash protection, minimal schema change |

---

*This is a living document. v0.3 will incorporate implementation feedback and schema refinements.*