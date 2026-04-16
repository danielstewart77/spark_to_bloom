ada@hive_mind:~$ diff --minds ada nagatha

> Ada vs Nagatha — Backend Architecture
> Two minds, two fundamentally different subprocess models. Ada keeps a process alive for the entire session. Nagatha spawns a fresh process on every single turn. Same gateway, same session manager, opposite lifetime strategies.

## Ada — Claude CLI (Persistent Subprocess)

```mermaid
graph TD
    A_REQ[Gateway Request] --> A_SM[Session Manager]
    A_SM -->|"spawn once\nclaude -p --stream-json\n--resume claude_sid"| A_PROC["Claude CLI Process\nlives across all turns"]
    A_SM -->|persist| A_DB["SQLite\nclaude_sid for resume"]
    A_PROC -->|stdout NDJSON stream| A_SM
    A_PROC -->|MCP protocol| A_MCP["MCP Tools\nBrowser · Graph · Memory · Gmail"]
    A_PROC -->|Stop hook every 5 turns| A_SOUL["soul_nudge.sh\n/self-reflect"]
    A_PROC -.->|stderr warnings| A_LOG[Structured Logs]
```

## Nagatha — Codex CLI (Ephemeral Per-Turn)

```mermaid
graph TD
    N_REQ[Gateway Request] --> N_SM[Session Manager]
    N_SM --> N_STATE["Module-level state\nsystem_prompt · thread_id"]
    N_STATE -->|"new process per turn\ncodex exec --json --full-auto\nor resume thread_id"| N_PROC["Codex CLI Process\nexits after each turn"]
    N_PROC -->|stdout NDJSON to completion| N_SM
    N_PROC -->|thread.started event| N_STATE
    N_STATE -.->|persist thread_id| N_DB["SQLite\nclaude_sid = thread_id"]
```

## Key Differences

| | Ada | Nagatha |
|---|---|---|
| Subprocess lifetime | Session-scoped (persistent) | Turn-scoped (ephemeral) |
| CLI tool | `claude` (Anthropic) | `codex` (OpenAI) |
| MCP tools | Full stack | None |
| Session resume | `--resume` flag | `resume thread_id` arg |
| Soul / identity | Hooks + graph writes | Graph only (no hooks yet) |
