# Spark to Bloom

Spark to Bloom is a FastAPI site that serves Daniel's public-facing content and a protected operator surface for Hive Mind. It combines static and Markdown-backed pages with authenticated tools for the live console and graph viewer.

## What the project does

- Serves the public website content for `sparktobloom.com`
- Renders Markdown-backed pages such as Canvas and LinkedIn content
- Provides username/password authentication for protected pages
- Proxies Hive Mind session data into a live console UI
- Proxies Hive Mind graph data into a protected graph viewer

## Current architecture

Spark to Bloom is not the Hive Mind backend. It is the website and auth/proxy layer in front of it.

Browser
- Loads public pages directly from Spark to Bloom
- Accesses protected `/console` and `/graph` pages after login

Spark to Bloom
- FastAPI app in `src/main.py`
- Jinja templates in `src/templates/`
- Static assets in `src/static/`
- SQLite auth database in `data/stb.db`

Hive Mind gateway
- Provides session and graph data over HTTP
- Configured via `GATEWAY_API_URL` / `GRAPH_API_URL`

## Main features

### Public pages

- `/`
- `/about`
- `/pullrequests`
- `/canvas`
- `/linkedin`
- `/pages/{subpath}`

Markdown-backed pages are rendered from files in `src/templates/`.

### Authenticated pages

- `/console`
  Displays one card per recent Hive Mind session and attaches to passive observer streams.

- `/graph`
  Displays a Cytoscape-based graph view backed by Hive Mind graph data.

### Auth flow

- `/login`
- `POST /login`
- `POST /logout`

Auth is backed by a local SQLite users table and signed session cookies.

## Repository layout

```text
spark_to_bloom/
├── src/
│   ├── main.py
│   ├── auth.py
│   ├── graph_data.py
│   ├── config.py
│   ├── templates/
│   └── static/
├── scripts/
│   └── create_user.py
├── data/
│   └── stb.db
├── tests/
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Requirements

- Python 3.12
- FastAPI
- Uvicorn
- Jinja2
- Markdown
- `python-multipart`
- `bcrypt`
- `itsdangerous`

For the protected console and graph pages to be useful, Spark to Bloom also needs access to a running Hive Mind gateway.

## Configuration

Important environment variables:

- `GATEWAY_API_URL`
  Base URL for the Hive Mind gateway session APIs

- `GRAPH_API_URL`
  Fallback base URL for graph data if `GATEWAY_API_URL` is not set

- `HIVE_INIT_HOST`
  Optional host name dedicated to serving the standalone Phase 1 installer

- `HIVE_INIT_REPO_DIR`
  Filesystem path containing the canonical `hive-init.py` and `hive-init.sh` assets

- `HIVE_INIT_HOST_PATH`
  Host-side path mounted into the Spark to Bloom container for standalone installer delivery

- `STB_SECRET_KEY`
  Secret used for session signing

- `STB_DB_PATH`
  Path to the SQLite auth database

The app defaults to:

- gateway URL: `http://server:8420`
- auth DB: `data/stb.db`
- hive-init host: `gethivemind.sparktobloom.com`
- hive-init repo dir: `/mnt/dev/hive-init`
- hive-init host path: `/home/daniel/Storage/Dev/hive-init`

## Hive Init delivery

Spark to Bloom can deliver the standalone `hive-init` installer from a separate
repo without absorbing the installer logic into this codebase.

Two delivery patterns are supported:

- Main site downloads:
  - `/downloads/hive-init.py`
  - `/downloads/hive-init.sh`

- Dedicated host:
  - `https://gethivemind.sparktobloom.com/`
  - `https://gethivemind.sparktobloom.com/hive-init.py`
  - `https://gethivemind.sparktobloom.com/hive-init.sh`

The container must have the canonical installer repo mounted read-only and
`HIVE_INIT_REPO_DIR` pointed at that mount.

## Local development

Install dependencies:

```bash
cd /home/hivemind/dev/spark_to_bloom
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

Run the app locally:

```bash
cd /home/hivemind/dev/spark_to_bloom
venv/bin/python -m uvicorn main:app --app-dir src --host 0.0.0.0 --port 5000
```

## Docker

Build and run with Compose:

```bash
cd /home/hivemind/dev/spark_to_bloom
docker compose up -d --build frontend
```

The app is served on port `5000`.

## Creating a login user

Bootstrap or replace a website user:

```bash
cd /home/hivemind/dev/spark_to_bloom
venv/bin/python scripts/create_user.py --username daniel --admin --replace
```

You can also pass `--password` non-interactively.

## Testing

Run the main Spark test suites:

```bash
cd /home/hivemind/dev/spark_to_bloom
venv/bin/python -m pytest -q tests/test_auth.py
venv/bin/python -m pytest -q tests/test_console_routes.py
venv/bin/python -m pytest -q tests/test_graph_routes.py
venv/bin/python -m pytest -q tests/test_graph_data.py
```

## Notes for operators

- Static assets use file-mtime cache busting in the template renderer, so CSS and JS URLs update automatically when those files change
- The live console depends on Hive Mind passive observer streams; if the gateway is unavailable, the page still renders but stream data will not populate
- GitHub auth in Daniel's normal shell does not imply GitHub auth inside the Codex harness user environment

## License

No license file is currently defined in this repository.
