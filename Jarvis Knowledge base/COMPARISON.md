# Comparison with Existing Tools

| Feature | Synto | Synthadoc | LLM-WIKI-MCP | Link | **Unified OS (Target)** |
|---|---|---|---|---|---|
| Markdown ingest | ✅ | ✅ | ✅ | ✅ | ✅ |
| PDF/DOCX/Video ingest | ❌ | ✅ | Partial | ❌ | ✅ |
| Two-tier LLM compile | ✅ | ❌ | ❌ | ❌ | ✅ |
| Incremental compile | ✅ | ❌ | N/A | N/A | ✅ |
| Hand-edit protection | ✅ | ❌ | ❌ | ❌ | ✅ |
| Rejection feedback loop | ✅ | ❌ | ❌ | ❌ | ✅ |
| Contradiction detection | ❌ | ✅ | ❌ | ❌ | ✅ |
| Claim-level citations | ❌ | ✅ | ❌ | ❌ | ✅ |
| Audit.db / cost tracking | ❌ | ✅ | ❌ | ❌ | ✅ |
| Conversation history | ❌ | ❌ | ✅ | ❌ | ✅ |
| Context budgets | ❌ | ❌ | ✅ | ❌ | ✅ |
| Memory lifecycle | ❌ | ❌ | ❌ | ✅ | ✅ |
| Graph context retrieval | ❌ | ❌ | ❌ | ✅ | ✅ |
| MCP server | ✅ | Partial | ✅ | ✅ | ✅ (unified) |
| REST API | ❌ | ✅ | ❌ | ✅ | ✅ |
| Pack export | ✅ | ❌ | ❌ | ❌ | ✅ |
| Single schema | ❌ | ❌ | ❌ | ❌ | ✅ |
| Priority job queue | ❌ | ❌ | ❌ | ❌ | ✅ |

## Design Philosophy Differences

- **Synto** is a *compiler*. We adopt its compilation pipeline.
- **Synthadoc** is an *auditor*. We adopt its audit and provenance model.
- **LLM-WIKI-MCP** is a *conversational bridge*. We adopt its query and context management.
- **Link** is a *memory manager*. We adopt its graph and lifecycle primitives.

The unified OS does not replace these tools' *ideas*. It replaces the *integration tax* of using them together.
