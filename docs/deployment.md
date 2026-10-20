# Running and deploying CircuitPilot

The root README covers local SQLite development. No public hosting account/domain
has been configured. The Sites runtime uses Cloudflare Workers and cannot host this
retained Python/OpenCV backend directly; use a Python/container-capable host rather
than replacing validated Python logic with browser-only approximations.

## PostgreSQL and containers

`compose.yaml` runs PostgreSQL 17, backend, durable worker and Next.js. Set a long
random `POSTGRES_PASSWORD` in an untracked `.env`; choose URL-safe password characters
or percent-encode them when constructing a database URL. Build/run:

```sh
docker compose up --build
```

Backend applies Alembic migrations before serving. Worker waits for backend health,
shares the upload volume, recovers interrupted jobs, and removes expired images.
The frontend proxies requests to the internal backend. User-facing ports bind to
127.0.0.1, so this configuration is a local/private deployment by default.

For a new standalone PostgreSQL database:

```sh
export CIRCUITPILOT_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE'
uv run --locked alembic upgrade head
```

Do not commit credentials or paste real connection strings into public issues.
Do not point the initial migration at an existing unversioned development database:
local `auto_create_schema=true` creates tables without Alembic version history.
Back up/export its data and migrate into a fresh versioned database deliberately.
Never stamp an arbitrary existing database as current without a schema comparison.

## Before external access

Terminate HTTPS at a managed proxy/load balancer and route one public origin to the
frontend. Keep backend/database private. Set:

```text
CIRCUITPILOT_ENVIRONMENT=production
CIRCUITPILOT_COOKIE_SECURE=true
CIRCUITPILOT_AUTO_CREATE_SCHEMA=false
CIRCUITPILOT_ALLOWED_ORIGINS=["https://your-selected-domain"]
```

Production configuration requires PostgreSQL and rejects plain-HTTP allowed origins.
The frontend backend URL is a build-time rewrite setting: rebuild when it changes.
Add upstream request/rate/time limits, encrypted database/volume backups, restoration
checks and monitoring for failed/stuck jobs. Disable request-path logging of upload
ticket URLs. Account recovery, email verification and institutional identity are
not implemented and must be resolved before an unrestricted paid service.

This release's object storage adapter is a private local filesystem. Backend and
worker must share one persistent volume; do not scale them across independent
filesystems. S3 storage is an outstanding deployment extension, not an existing
integration. An ephemeral platform filesystem would lose uploaded photos.

Run the worker continuously, or schedule `python -m app.worker --once` frequently
enough to enforce retention. Database rows expire access immediately; the worker
performs physical file deletion. Application retention does not automatically erase
external backups; set corresponding backup retention/deletion procedures.

## Release gates

Green automated checks do not replace physical board/part verification, current
and power-rating analysis, real held-out model evaluation, privacy review or actual
pilot observations. Current plans remain reference-only. See `docs/progress.md`.
Do not change a status flag to imply these gates have been satisfied.
