# Behavioral Rule Retrieval

> **Status:** Ready to implement.

---

## What

Inject Ada's behavioral rules from the vector store into context automatically on every turn, so session feedback accumulates into real behavior change over time.

58 rules are already in the vector store under `data_class=ada-behavior-rule`.

---

## Implementation

### 1. REST Endpoint

Add to the main gateway (`server.py`):

```
GET /memory/query?text=<message>&k=3&data_class=ada-behavior-rule&threshold=0.65
```

Returns top-K semantically similar rules above the similarity threshold. No MCP dependency.

### 2. Two-Tier Injection

**Tier 1 — Session start (standing rules)**
Load a fixed small set of always-applicable rules once at session start. Candidates: credentials, verification, completeness, specs.

**Tier 2 — Per-turn (contextual rules)**
On every user message, query the endpoint with the message text. Inject results only if similarity ≥ 0.65. Skip low-signal messages (greetings, simple lookups).

### 3. Hook

`UserPromptSubmit` hook calls the REST endpoint and injects results as:

```xml
<behavior-rules>
- Never embed credentials in skill files; use keyring lookups only.
- When a skill step requires asking the user, execute it as written — do not infer around it.
- After a write operation, read back to verify actual state before reporting success.
</behavior-rules>
```

---

## Design Rules

| # | Rule |
|---|---|
| 1 | **Relevance threshold** — only inject per-turn rules when similarity ≥ 0.65 |
| 2 | **Two tiers** — standing rules load at session start; per-turn surfaces context-specific ones only |
| 3 | **REST not MCP** — hook calls HTTP, no MCP dependency; aligns with MCP removal roadmap |
| 4 | **Tag injection** — `<behavior-rules>` XML block for high attention weight |

---

## Files

| File | Change |
|---|---|
| `server.py` | Add `GET /memory/query` endpoint |
| `.claude/hooks/` | Add `UserPromptSubmit` hook script |
| `core/sessions.py` | Session-start tier-1 injection (optional) |
