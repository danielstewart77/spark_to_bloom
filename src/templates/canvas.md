# Plan: Hive Mind Live Console

> **Status:** Planned — not yet implemented.

> **Source:** `/usr/src/app/plans/hive-mind-console.md`

---

## Mockup

<div style="background:#07090f;border-radius:10px;padding:0;overflow:hidden;font-family:'Fira Code',monospace;border:1px solid #1e2d3d;">

  <!-- Top bar -->
  <div style="background:#0d1a26;padding:0.6rem 1.2rem;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1e3a52;">
    <span style="color:#38bdf8;font-size:0.72rem;letter-spacing:0.18em;">HIVE MIND CONSOLE</span>
    <span style="color:#475569;font-size:0.68rem;">daniel &nbsp;·&nbsp; <span style="color:#38bdf8;cursor:pointer;">logout</span></span>
  </div>

  <!-- Grid -->
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;padding:1rem;">

    <!-- Ada card — responding -->
    <div style="background:#0d1117;border:1px solid #1e2d3d;border-radius:8px;height:320px;display:flex;flex-direction:column;box-shadow:0 0 16px rgba(56,189,248,0.06);">
      <div style="background:#0d1a26;border-bottom:1px solid #1e2d3d;border-radius:8px 8px 0 0;padding:0.4rem 0.75rem;display:flex;justify-content:space-between;align-items:center;">
        <span>
          <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#22c55e;margin-right:5px;vertical-align:middle;"></span>
          <span style="color:#38bdf8;font-size:0.7rem;">ada</span>
          <span style="color:#334155;font-size:0.65rem;margin-left:6px;">· a3f2b1c9</span>
        </span>
        <span style="color:#475569;font-size:0.63rem;">2m ago</span>
      </div>
      <div style="flex:1;overflow:hidden;padding:0.75rem;font-size:0.72rem;line-height:1.7;color:#94a3b8;">
        <span style="display:block;color:#475569;">user &gt; fix the readme links</span>
        <span style="display:block;color:#dce8f0;"><span style="color:#38bdf8;">ada</span> &gt; Reading README...</span>
        <span style="display:block;color:#f59e0b;">[tool: Read] &nbsp;{file: README.md}</span>
        <span style="display:block;color:#78716c;">[result] &nbsp;{lines: 187}</span>
        <span style="display:block;color:#dce8f0;"><span style="color:#38bdf8;">ada</span> &gt; Found 72 broken links.</span>
        <span style="display:block;color:#f59e0b;">[tool: Edit] &nbsp;{file: README.md}</span>
        <span style="display:block;color:#78716c;">[result] &nbsp;{ok: true}</span>
        <span style="display:block;color:#dce8f0;"><span style="color:#38bdf8;">ada</span> &gt; Done. Skills table replaced.<span style="display:inline-block;width:7px;height:13px;background:#38bdf8;margin-left:2px;vertical-align:middle;animation:none;opacity:1;"></span></span>
      </div>
    </div>

    <!-- Nagatha card — tool call in progress -->
    <div style="background:#0d1117;border:1px solid #1e2d3d;border-radius:8px;height:320px;display:flex;flex-direction:column;box-shadow:0 0 16px rgba(56,189,248,0.06);">
      <div style="background:#0d1a26;border-bottom:1px solid #1e2d3d;border-radius:8px 8px 0 0;padding:0.4rem 0.75rem;display:flex;justify-content:space-between;align-items:center;">
        <span>
          <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#f59e0b;margin-right:5px;vertical-align:middle;"></span>
          <span style="color:#38bdf8;font-size:0.7rem;">nagatha</span>
          <span style="color:#334155;font-size:0.65rem;margin-left:6px;">· 7e4d2a1f</span>
        </span>
        <span style="color:#475569;font-size:0.63rem;">12m ago</span>
      </div>
      <div style="flex:1;overflow:hidden;padding:0.75rem;font-size:0.72rem;line-height:1.7;color:#94a3b8;">
        <span style="display:block;color:#475569;">user &gt; implement stop interrupt</span>
        <span style="display:block;color:#dce8f0;"><span style="color:#38bdf8;">nagatha</span> &gt; Reading story...</span>
        <span style="display:block;color:#f59e0b;">[tool: Read] &nbsp;{file: STORY.md}</span>
        <span style="display:block;color:#78716c;">[result] &nbsp;{lines: 42}</span>
        <span style="display:block;color:#dce8f0;"><span style="color:#38bdf8;">nagatha</span> &gt; Planning TDD approach.</span>
        <span style="display:block;color:#f59e0b;">[tool: Write] &nbsp;{file: IMPL.md}</span>
        <span style="display:block;color:#78716c;">[result] &nbsp;{ok: true}</span>
        <span style="display:block;color:#f59e0b;">[tool: Bash] &nbsp;{cmd: pytest}</span>
        <span style="display:block;color:#78716c;">[result] &nbsp;{passed: 14} ▌</span>
      </div>
    </div>

    <!-- Bob card — idle -->
    <div style="background:#0d1117;border:1px solid #1e2d3d;border-radius:8px;height:320px;display:flex;flex-direction:column;box-shadow:0 0 16px rgba(56,189,248,0.03);opacity:0.7;">
      <div style="background:#0d1a26;border-bottom:1px solid #1e2d3d;border-radius:8px 8px 0 0;padding:0.4rem 0.75rem;display:flex;justify-content:space-between;align-items:center;">
        <span>
          <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#475569;margin-right:5px;vertical-align:middle;"></span>
          <span style="color:#38bdf8;font-size:0.7rem;">bob</span>
          <span style="color:#334155;font-size:0.65rem;margin-left:6px;">· f9c3e2b0</span>
        </span>
        <span style="color:#475569;font-size:0.63rem;">1h ago</span>
      </div>
      <div style="flex:1;overflow:hidden;padding:0.75rem;font-size:0.72rem;line-height:1.7;color:#94a3b8;">
        <span style="display:block;color:#475569;">user &gt; what model are you?</span>
        <span style="display:block;color:#dce8f0;"><span style="color:#38bdf8;">bob</span> &gt; I'm llama3:70b, running locally via Ollama.</span>
        <span style="display:block;color:#334155;font-style:italic;margin-top:0.5rem;">— idle —</span>
      </div>
    </div>

  </div>

  <!-- Legend -->
  <div style="padding:0.4rem 1.2rem 0.7rem;display:flex;gap:1.5rem;font-size:0.65rem;color:#475569;">
    <span><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#22c55e;margin-right:4px;vertical-align:middle;"></span>responding</span>
    <span><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#f59e0b;margin-right:4px;vertical-align:middle;"></span>tool call</span>
    <span><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#475569;margin-right:4px;vertical-align:middle;"></span>idle / closed</span>
  </div>

</div>

---

**Goal**: Add a `/console` page to spark_to_bloom that shows a live grid of all minds — one window per mind, streaming their active session in real time. New minds auto-appear when added to the system.

---

## Decisions (locked)

| # | Question | Decision |
|---|---|---|
| 1 | Auth | Full auth required. Use standard username/password login only. All provisioning and user management happen through Hive Mind, not the website. |
| 2 | History on load | Live only — stream from the moment you open the page, no backfill. |
| 3 | Tool events | Show everything — tool calls, tool results, all event types. No filtering. |
| 4 | Which sessions per mind | All sessions active in the last 24 hours. Multiple Ada sessions = multiple windows. |
| 5 | Empty placeholders | None. Only show cards for sessions that actually exist. No ghost cards for idle minds. |
| 6 | Live card appearance | When a new session starts while the page is open, its card appears immediately — no refresh. |

---

## User Experience

- Navigate to `https://sparktobloom.com/console`
- Login wall (if not authenticated) → redirect to `/login`
- See a responsive CSS grid — one card per mind session active in last 24h
- Each card shows: mind name, session ID (short), start time, and a live feed streaming from the moment the page loads
- Ada may have 2+ cards if multiple sessions were active in the last 24h
- New minds auto-appear on next poll (60s interval)

---

## Architecture

```
Browser
  └── GET /console              → spark_to_bloom (auth check → render page)
  └── GET /api/minds            → spark_to_bloom → server:8420/broker/minds
  └── GET /api/console/sessions → spark_to_bloom → server:8420/sessions (filtered: last 24h)
  └── GET /api/console/{session_id}/stream  → spark_to_bloom (SSE proxy, auth check)
                                             → server:8420/sessions/{id}/events
  └── POST /login               → spark_to_bloom (auth, sets session cookie)
  └── POST /logout              → spark_to_bloom (clears cookie)
```

spark_to_bloom acts as a **reverse proxy + auth layer**. The browser never talks to the hive_mind gateway directly.

This feature requires **small but real hive_mind changes**. The console cannot be built as a pure spark_to_bloom proxy.

Required upstream endpoints:
- `GET /broker/minds` — registered mind list
- `GET /sessions` — all sessions (filter by `last_active` timestamp client-side)
- `GET /sessions/{id}/events` — new read-only event stream for passive observers

---

## Critical Defect: Passive Observer Stream Missing

This is the implementation defect Nagatha found while reviewing the plan.

The current gateway websocket at `WS /sessions/{id}/stream` is **not** a passive subscription endpoint. It expects the client to send a new message, then it streams the response for that injected message. That means the proposed console cannot attach to an already-running Telegram or Discord session and watch it safely. Connecting to the current endpoint would either block forever waiting for input or mutate the live session by sending a prompt.

### Required fix

Add a true observer path in hive_mind:

- SessionManager publishes outbound session events to a fan-out bus per session
- Existing client surfaces still receive their normal response path
- New read-only endpoint exposes the same event stream to observers without injecting input
- spark_to_bloom proxies that observer stream to the browser

### Recommended shape

- New gateway route: `GET /sessions/{session_id}/events`
- Transport: SSE is simplest because spark_to_bloom already wants to emit SSE to the browser
- Scope: read-only observers only; no writes, no prompt injection
- Authorization: enforced in spark_to_bloom before opening the upstream stream

Without this gateway change, the console is not a live console. It is just a session list with empty cards.

---

## Auth Design

Use a standard auth stack with username/password login. The website does not provide self-registration, access requests, or a browser-based admin console. All user creation, disablement, and password resets are managed through Hive Mind.

### Database
Add SQLite DB to spark_to_bloom (`data/stb.db`) with:

```sql
CREATE TABLE users (
    id       INTEGER PRIMARY KEY,
    username TEXT    NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    disabled_at INTEGER
);
```

### Session Cookies
- Login: POST `/login` with username/password → verify against DB → set signed `session` cookie (via `itsdangerous` or similar)
- Every protected route checks the cookie. Invalid/missing → 401/redirect to `/login`.
- Logout: POST `/logout` → clear cookie

### Login UX

- `/login` remains a normal username/password form
- No `Request access` flow
- No self-registration flow
- No password setup flow in the browser beyond normal login

### User Management UX

- No `/admin/users` page
- Daniel manages users conversationally:
  - “Nagatha, add user alice”
  - “Ada, disable user bob”
  - “Reset Carol’s website password”
- The selected mind updates the spark_to_bloom auth DB through a small protected integration path or direct DB write in the same deployment context

### Why this is the better fit

- Preserves proper website auth boundaries
- Avoids the username-only request-access attack surface
- Avoids a bulky admin UI that exists only for occasional operator tasks
- Keeps user management inside the product’s actual operating model

### Non-negotiable detail

The first admin still needs a bootstrap path. To avoid deadlock, keep:

```bash
python scripts/create_user.py --username daniel --admin
```

This creates the first owner account or seeds the owner row. After that, ongoing user management happens through Hive Mind commands, not browser UI.

### Protected Routes

| Route | Protected |
|---|---|
| `GET /console` | Yes |
| `GET /graph` | Yes |
| `GET /api/minds` | Yes |
| `GET /api/console/sessions` | Yes |
| `GET /api/console/{id}/stream` | Yes |
| `GET /graph/data` | Yes |
| `GET /graph/public-data` | Yes |
| `GET /login` | No |
| `POST /login` | No |
| `GET /health` | No |
| `GET /` | No (public) |

---

## Session Window Logic

Query: `GET server:8420/sessions` → filter client-side to sessions where `last_active >= now - 86400s`.

Each qualifying session gets its own card:
- Mind name (from `mind_id` field)
- Short session ID (first 8 chars)
- `last_active` timestamp (relative: "3 min ago")
- Status dot: running=green, idle=yellow, closed=grey

Sorting: by `last_active` descending. Running sessions first, then idle, then closed.

---

## Stream Proxy

`GET /api/console/{session_id}/stream` — SSE endpoint on spark_to_bloom:

1. Auth check (reject if unauthenticated)
2. Open the new read-only upstream event stream at `server:8420/sessions/{session_id}/events`
3. Forward every received JSON message as an SSE `data:` line
4. If the upstream stream closes (session ended): emit `{"type":"session_closed"}` and end the SSE stream
5. Client reconnects automatically — on reconnect, if session is closed, card shows closed state

**Show everything** — no event filtering.

---

## Frontend (console.html)

Vanilla JS, extends `layout.html`. No build step.

```
layout.html
  └── console.html
        ├── #minds-grid  (CSS Grid, auto-fill, minmax 320px)
        │     └── .mind-card  (one per session, injected dynamically)
        │           ├── .card-header  (mind name · session id · status dot · age)
        │           └── .card-feed   (scrolling event feed, monospace)
        └── <script>
              ├── loadSessions()     — fetch /api/console/sessions, diff against current cards
              ├── connectStream(id)  — open EventSource per session
              ├── renderEvent(event) — append to card feed
              └── poll()            — re-run loadSessions() every 10s
```

### Event Rendering

| Event type | Rendered as |
|---|---|
| `user` | `user > [content]` — slate/muted |
| `assistant` chunk | `[mind] > [text]` — ice blue, streams in character by character |
| `tool_use` | `[tool: name]  {args}` — amber |
| `tool_result` | `[result]  {content}` — amber/dim |
| `system` | `[sys]  ...` — dark slate |
| `session_closed` | `— session closed —` — grey, italic |

Auto-scroll to bottom. Pause while user scrolls up; resume within 100px of bottom.

---

## Theme

Dark terminal aesthetic matching existing spark_to_bloom style.

```
background-deep:   #07090f
background-card:   #0d1117
background-header: #0d1a26
border:            #1e2d3d
accent:            #38bdf8   /* sky blue */
status-active:     #22c55e   /* green */
status-thinking:   #f59e0b   /* amber */
status-closed:     #475569   /* grey */
font-mono:         'Fira Code', monospace
```

---

## Files to Create/Modify

| File | Change |
|---|---|
| `/usr/src/app/server.py` | Add read-only session event stream endpoint for passive observers |
| `/usr/src/app/core/sessions.py` | Add per-session event fan-out / observer subscription support |
| `src/main.py` | Add auth, `/login`, `/logout`, `/console`, `/api/minds`, `/api/console/sessions`, `/api/console/{id}/stream`; protect `/graph` routes |
| `src/auth.py` | New — DB init, user lookup, password verify, session cookie, `require_auth` dependency |
| `src/templates/console.html` | New page |
| `src/templates/login.html` | New login form |
| `src/static/style.css` | Add card, feed, header, login styles |
| `scripts/create_user.py` | New — CLI to bootstrap first admin user |
| `requirements.txt` | Add `bcrypt`, `itsdangerous` |
| `docker-compose.yml` (stb) | Add `STB_SECRET_KEY` env, ensure `data/` bind-mounted |

---

## Bootstrap / First Run

```bash
python scripts/create_user.py --username daniel --admin
```

Creates DB at `data/stb.db` if it doesn't exist and seeds the first owner account. After that, user creation and password resets are done through Hive Mind commands.

---

## Out of Scope (this iteration)

- Full browser-based user management console
- Session history replay
- Pinning or annotating cards
- Filtering by mind
