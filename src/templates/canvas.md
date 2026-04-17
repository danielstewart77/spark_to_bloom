# Developer Console (Debug Control Room)

> **Status:** Concept. Not yet designed or implemented.
> **Motivation:** As system complexity grows, Ada's in-context view is incomplete at any given moment. This console gives Daniel a shared situational picture so both can diagnose faster — without requiring Ada to narrate every step or Daniel to ask.

---

## Mockup

<div style="font-family:'Fira Code',monospace;font-size:0.78rem;background:#07090f;border:1px solid #1e3a52;border-radius:6px;padding:0;overflow:hidden;margin:1.5rem 0;box-shadow:0 0 24px rgba(56,189,248,0.08);">

  <!-- Header bar -->
  <div style="background:#0d1a26;border-bottom:1px solid #1e3a52;padding:0.5rem 1rem;display:flex;justify-content:space-between;align-items:center;">
    <span style="color:#38bdf8;letter-spacing:0.15em;font-size:0.72rem;">HIVE MIND // DEVELOPER CONSOLE</span>
    <span style="color:#475569;font-size:0.68rem;">session: ada-tg-4f2a &nbsp;|&nbsp; <span style="color:#22c55e;">&#9679;</span> live</span>
  </div>

  <!-- ASSESSMENT panel -->
  <div style="border-bottom:1px solid #1e3a52;">
    <div style="background:#0d1a26;padding:0.3rem 1rem;display:flex;justify-content:space-between;">
      <span style="color:#38bdf8;font-size:0.68rem;letter-spacing:0.1em;">ASSESSMENT</span>
      <span style="color:#475569;font-size:0.68rem;">10:06:42</span>
    </div>
    <div style="padding:0.75rem 1rem;max-height:110px;overflow-y:auto;color:#94a3b8;line-height:1.7;">
      <span style="color:#f59e0b;">&gt;</span> Knowledge graph page crashed during demo. Investigating volume mount state.<br>
      <span style="color:#f59e0b;">&gt;</span> Hypothesis: docker-compose is using a named volume instead of a host bind mount for /data — graph SQLite DB was not persisted across container restart.<br>
      <span style="color:#475569;">&gt;</span> Ruled out: network issue, API timeout, code regression. Container logs show DB opened fresh on startup.<br>
      <span style="color:#22c55e;">&gt;</span> Next: confirm volume config in docker-compose.yml, check /data mount inside container.
    </div>
  </div>

  <!-- Middle row: CODE | STATE -->
  <div style="display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid #1e3a52;">

    <!-- CODE / CONFIG panel -->
    <div style="border-right:1px solid #1e3a52;">
      <div style="background:#0d1a26;padding:0.3rem 1rem;">
        <span style="color:#38bdf8;font-size:0.68rem;letter-spacing:0.1em;">CODE / CONFIG</span>
        <span style="color:#475569;font-size:0.68rem;margin-left:0.75rem;">docker-compose.yml : 34</span>
      </div>
      <div style="padding:0.75rem 1rem;max-height:160px;overflow-y:auto;color:#64748b;line-height:1.8;">
        <span style="color:#475569;">31 &nbsp;</span> <span style="color:#94a3b8;">server:</span><br>
        <span style="color:#475569;">32 &nbsp;</span> <span style="color:#94a3b8;">&nbsp;&nbsp;image: hive-mind-server</span><br>
        <span style="color:#475569;">33 &nbsp;</span> <span style="color:#94a3b8;">&nbsp;&nbsp;volumes:</span><br>
        <span style="background:#7f1d1d;color:#fca5a5;display:inline-block;width:100%;">34 &nbsp;&nbsp;&nbsp;&nbsp;- hive-data:/data &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span style="color:#f87171;">&#9664; named vol</span></span>
        <span style="color:#475569;">35 &nbsp;</span> <span style="color:#94a3b8;">&nbsp;&nbsp;environment:</span><br>
        <span style="color:#475569;">36 &nbsp;</span> <span style="color:#94a3b8;">&nbsp;&nbsp;&nbsp;&nbsp;- DATA_DIR=/data</span><br>
        <br>
        <span style="color:#22c55e;">&#8250; should be:</span><br>
        <span style="background:#052e16;color:#86efac;display:inline-block;width:100%;">&nbsp;&nbsp;&nbsp;&nbsp;- ./data:/data &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span style="color:#4ade80;">&#9664; bind mount</span></span>
      </div>
    </div>

    <!-- SYSTEM STATE panel -->
    <div>
      <div style="background:#0d1a26;padding:0.3rem 1rem;">
        <span style="color:#38bdf8;font-size:0.68rem;letter-spacing:0.1em;">SYSTEM STATE</span>
      </div>
      <div style="padding:0.75rem 1rem;max-height:160px;overflow-y:auto;line-height:1.9;">
        <span style="color:#475569;">containers</span><br>
        <span style="color:#22c55e;">&nbsp;&nbsp;&#9679;</span> <span style="color:#94a3b8;">server &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;running &nbsp;8420</span><br>
        <span style="color:#22c55e;">&nbsp;&nbsp;&#9679;</span> <span style="color:#94a3b8;">telegram &nbsp;&nbsp;&nbsp;running</span><br>
        <span style="color:#22c55e;">&nbsp;&nbsp;&#9679;</span> <span style="color:#94a3b8;">spark &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;running &nbsp;5000</span><br>
        <br>
        <span style="color:#475569;">volumes</span><br>
        <span style="color:#f87171;">&nbsp;&nbsp;&#9679;</span> <span style="color:#94a3b8;">hive-data &nbsp;&nbsp;named &nbsp;<span style="color:#f87171;">&#9664; no host path</span></span><br>
        <br>
        <span style="color:#475569;">git</span><br>
        <span style="color:#94a3b8;">&nbsp;&nbsp;branch &nbsp;&nbsp;&nbsp;master</span><br>
        <span style="color:#94a3b8;">&nbsp;&nbsp;last &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;fix: namespace telegram session</span>
      </div>
    </div>

  </div>

  <!-- ACTION LOG panel -->
  <div>
    <div style="background:#0d1a26;padding:0.3rem 1rem;">
      <span style="color:#38bdf8;font-size:0.68rem;letter-spacing:0.1em;">ACTION LOG</span>
    </div>
    <div style="padding:0.75rem 1rem;max-height:120px;overflow-y:auto;color:#475569;line-height:1.8;">
      <span style="color:#1e3a52;">10:06:38</span> &nbsp;<span style="color:#94a3b8;">read docker-compose.yml</span><br>
      <span style="color:#1e3a52;">10:06:39</span> &nbsp;<span style="color:#94a3b8;">grep: searched for volume definitions</span><br>
      <span style="color:#1e3a52;">10:06:40</span> &nbsp;<span style="color:#f87171;">found named volume 'hive-data' — no host bind mount</span><br>
      <span style="color:#1e3a52;">10:06:41</span> &nbsp;<span style="color:#94a3b8;">confirmed /data inside container has no host path</span><br>
      <span style="color:#1e3a52;">10:06:42</span> &nbsp;<span style="color:#22c55e;">assessment updated &nbsp;&#8250; awaiting Daniel</span>
    </div>
  </div>

</div>

---

## The Problem

The system has reached a complexity level where:

- Ada frequently lacks full context during a debugging session (config state, running containers, recent errors, recently changed files)
- Daniel is largely hands-off — a feature, not a bug — but that means he has no ambient visibility into system state. The gap only surfaces during demos or incidents.
- Common failure modes (e.g. named Docker volumes silently overwriting bind mounts) require Daniel to narrate the situation before Ada can act. A live view eliminates that round-trip.

---

## Concept

A terminal-themed developer console — think NOC/SOC dashboard — that Ada writes to during debugging sessions. Not a log viewer. A structured workspace Ada populates with her active diagnosis, relevant code, and live system state so Daniel can see exactly what Ada sees.

The mental model: Ada is at the keyboard. Daniel is standing behind her looking at the same screens.

---

## Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│ ASSESSMENT                                              [timestamp]  │
│  Ada's current diagnosis in plain language. What she thinks is       │
│  wrong, what she ruled out, what she's about to try. Scrollable.    │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────────┐  ┌──────────────────────────────────────┐
│ CODE / CONFIG            │  │ SYSTEM STATE                         │
│  Verbatim file content   │  │  Container status, volume mounts,    │
│  or diff. File path +    │  │  env vars, recent git log, service   │
│  line numbers shown.     │  │  health. Read-only snapshot.         │
│  Scrollable.             │  │  Scrollable.                         │
└──────────────────────────┘  └──────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ ACTION LOG                                                           │
│  Timestamped list of what Ada has done / is doing. Tool calls,      │
│  commands run, files edited. Append-only. Scrollable.               │
└─────────────────────────────────────────────────────────────────────┘
```

All panels: dark terminal theme, monospace font, green/amber/white on near-black. Panels are independently scrollable. Pause-on-hover so Daniel can read without auto-scroll fighting him.

---

## Ada-Side Interface

Ada writes to the console via REST endpoints on the gateway (server.py),
the same way all other system state flows:

| Endpoint | Purpose |
|----------|---------|
| `POST /console/assessment` | Overwrite the assessment panel with current diagnosis |
| `POST /console/code` | Push a file/diff block to the code panel (path, content, highlight_lines) |
| `POST /console/state` | Set a key/value entry in the system state panel |
| `POST /console/log` | Append a timestamped entry to the action log |
| `POST /console/clear` | Reset all panels (start of new debug session) |
| `GET /console` | WebSocket or SSE feed — consumed by the browser frontend |

Ada calls these proactively during any session where something is wrong — not only on request. The console is a running narration to the room, not a response to "what's going on."

---

## Integration Points

- **Gateway endpoints**: console state is held in the gateway (server.py), served via WebSocket or SSE to the frontend. Ada writes via HTTP POST, same as every other gateway interaction.
- **Website page**: new `/console` route on this site alongside graph and canvas. Same dark terminal aesthetic.
- **Telegram fallback**: if Daniel asks "what's going on" and the console is unpopulated, Ada summarises from context as normal. The console is additive.

---

## Scope Boundaries

- **Read-only for Daniel.** No input surface in the console — Daniel uses Telegram to respond or redirect.
- **Not a log aggregator.** Ada populates this intentionally. Signal over noise.
- **Not a monitoring dashboard.** No uptime graphs, no metrics — see `escalation-design.md` for alerting.
- **Not persistent across sessions** (initially). Each `console.clear()` or new debug session starts fresh.

---

## Why This Matters

The named-volume incident (April 2026, live demo) is the canonical example: Ada had written the docker-compose incorrectly and didn't know it until the crash. If the console had been showing the active volume mounts at the time, Daniel would have spotted it before the demo started. The fix takes seconds once you can see the state — the cost is in the back-and-forth to surface it.

---

## Open Questions

1. Should Ada auto-clear on new session creation, or leave the last state visible until explicitly cleared?
2. Should Daniel be able to annotate panels (sticky notes, highlights)? Useful but adds scope — defer to v2.
3. Does console state live purely in-memory on the gateway (reset on restart), or get written to SQLite for persistence across restarts?
