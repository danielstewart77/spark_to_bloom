# Skippy: in-repo lucent fork cleanup

> Skippy's repo (`~/Storage/Dev/hive_mind_skippy`) carries stale forks of the lucent code in two places. The canonical source lives in `~/Storage/Dev/hive_nervous_system`, runs as the `hive-lucent` container, and is what every mind (Skippy bare-metal, hive_mind containers) actually talks to over HTTP. The in-repo forks are no-runtime-value duplicates that have drifted from the canonical version, plus a handful of `core/` modules that bypass the HTTP API and call the fork's internals directly. This card covers cutting them out.

## Confirmed: one shared lucent

There is exactly one live lucent. One container (`hive-lucent`), one DB file (`~/Storage/Dev/hive_nervous_system/data/lucent.db`, 15 MB, root-owned because the container writes it), two access paths to the same backend:

- hive_mind containers → docker network → `hive-lucent:8424`
- Skippy (bare-metal) → host bind → `127.0.0.1:8425` → same container

So Skippy and the rest of the Hive Mind read and write the same KG and the same vector store. The in-repo forks are dead code that the test suite still exercises.

## Stale leftover DB files on disk (delete when convenient)

- `~/Storage/Dev/hive_mind/data/lucent.db` — 11 MB, last touched 2026-05-05. From before lucent was extracted into the nervous_system container.
- `~/Storage/Dev/data/lucent.db` — 86 KB, touched 2026-05-13 20:16. Looks like something ran from `~/Storage/Dev/` with a relative `data/lucent.db` path and accidentally created a fresh DB. Worth tracking down so it doesn't keep happening.

## What's in the repo and shouldn't be

### Dead-code lucent forks (delete entirely)

- `nervous_system/lucent_api/` — partial fork of the canonical API (lucent.py, lucent_memory.py, lucent_graph.py, kg_guards.py, routers/). Diverged from the canonical version (missing `MEMORY_TOOLS`, returns different shapes).
- `tools/stateful/lucent.py`, `tools/stateful/lucent_memory.py`, `tools/stateful/lucent_graph.py` — older fork that the in-repo `core/` modules still import directly.
- `tools/stateful/memory.py`, `tools/stateful/knowledge_graph.py` — even older Neo4j-era stateful tools. Zero runtime callers (only docstring references in the lucent_*.py files above).

### Runtime callers of the dead-code forks (migrate to HTTP, then delete)

These four files import sqlite-direct from the dead fork instead of going through the lucent HTTP API. Per CLAUDE.md ("Skippy talks to the shared `hive_nervous_system` container over HTTP+bearer"), this is wrong-by-architecture today:

- `core/kg_guards.py` — `from tools.stateful.lucent import _get_connection`
- `core/memory_expiry.py` — `from tools.stateful.lucent import _get_connection`
- `core/epilogue.py` — `from tools.stateful.lucent_memory import memory_store_direct` and `from tools.stateful.lucent_graph import graph_upsert_direct`
- `tools/stateless/lucent_migrate.py` — `from tools.stateful.lucent import _get_connection`

Each needs to be reworked to call the lucent container over HTTP (`LUCENT_URL_SELF` + `LUCENT_BEARER_TOKEN`). The relevant endpoints (`/memory/store`, `/memory/list`, `/graph/upsert-direct`, `/graph/properties/merge`, etc.) are already live on the canonical lucent.

`epilogue.py` and `kg_guards.py` are on hot paths (Stop hook, every KG write) — be careful with timeouts and retries during the migration.

## Drifted live-code tests (26 failing, separate triage)

After the dead-code tests were removed (PR #3 in hive_mind_skippy), 26 failures remain. All three buckets are tests of live `core/` code that drifted from the current taxonomy / function shapes:

### `tests/unit/test_memory_schema.py` (10 failures)

Tests reference the **old 8-class taxonomy** (`technical-config`, `person`, `timed-event`). Skippy moved to the 4-class taxonomy (`current-state`, `ephemeral`, `feedback`, `future-state`) — see `specs/data-classes/`. Either rewrite the tests to use current classes or delete them as the surface they test moved.

Symptom: `ValueError: Unknown data_class 'timed-event'. ... Valid classes: ['current-state', 'ephemeral', 'feedback', 'future-state']`.

### `tests/unit/test_prune_memory.py` (9 failures)

Tests mock module-level attributes that were refactored out — `parse_pruning_block`, `SPEC_DIR`, etc. The current `core/prune_memory.py` has a different API (one function per data class, dispatched from `prune-memory` skill). Tests need a rewrite against the current shape, or removal in favour of a smaller integration test.

Symptom: `AttributeError: module 'core.prune_memory' has no attribute 'parse_pruning_block' / 'SPEC_DIR'`.

### `tests/unit/test_memory_expiry.py` (7 failures)

`TestBuildMetadataTimedEventExpiry` (and friends) call `core.memory_schema.build_metadata` with `data_class="timed-event"` — same taxonomy drift as above. Either retarget to a current class that supports `expires_at` or delete.

Symptom: same `Unknown data_class 'timed-event'` ValueError.

## Recommended order of operations

1. Migrate the four runtime callers off `tools.stateful.lucent*` to the lucent HTTP API (one PR per caller — `core/kg_guards.py` is the riskiest).
2. Once nothing imports from `tools/stateful/lucent*` or `nervous_system/lucent_api/`, delete those directories entirely.
3. Triage the 26 remaining drifted tests:
   - Test files whose live-code surface has materially changed (`test_prune_memory.py`) — rewrite against the current API or delete.
   - Test files that just need taxonomy updates (`test_memory_schema.py`, `test_memory_expiry.py`) — search-and-replace `timed-event`/`person`/`technical-config` with the current 4-class names.
4. Delete the two stale `lucent.db` files on disk (after confirming no process owns them).

## Why this is being deferred

The fork-deletion is a multi-PR refactor that touches Skippy's hot paths (Stop hook, every KG write). The dead-code tests have been removed (PR #3) so the failing-test count is informative again. The remaining 26 are real but low-blast-radius — they don't block anything Skippy does day-to-day. Coming back to it when there's a clear half-day window.
