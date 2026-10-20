# Running and deploying CircuitPilot

The root README covers local SQLite development. A Render Blueprint is prepared;
no paid resources or hosting account have been created. The Sites runtime uses Cloudflare Workers and cannot host this
retained Python/OpenCV backend directly; use a Python/container-capable host rather
than replacing validated Python logic with browser-only approximations.

## Recommended first hosted pilot: Render

Use a Hobby workspace with one **1c-2g web service**, **0.1c-256mb managed
PostgreSQL 17**, and a **1 GB private persistent disk**. Both resources are in
Singapore. Use the supplied HTTPS `onrender.com` address initially; a purchased
domain is unnecessary. The 2 GB web service leaves room for Next.js, the Python
API, and photo processing; the 512 MB service is not the chosen configuration.

[Deploy this repository to Render](https://render.com/deploy?repo=https://github.com/Yizhuo04/CircuitPilot)

1. Sign in to Render with the founder's GitHub account and connect this repository.
2. Review the resources parsed from `render.yaml` and Render's displayed charges.
   The planned base budget is approximately **US$32/month**, before taxes, bandwidth,
   build overages and future growth. Pricing checked 2026-10-20: web compute $25/month,
   entry paid Postgres approximately $6/month, photo disk $0.25/GB/month. Database
   storage is explicitly 1 GB, avoiding an implicit larger allocation. Confirm the
   actual checkout estimate; [current pricing](https://render.com/pricing) controls.
3. Complete account/billing authorization and create the Blueprint. No credentials
   need to be pasted into this chat. Database credentials are wired internally.
4. Wait for a successful deployment and open the service's HTTPS address. Create
   your account and run the guided reference-circuit/photo flow. Run the external
   smoke command below; it creates and deletes only its own temporary account.

```sh
python3 scripts/smoke.py --base-url https://YOUR-SERVICE.onrender.com
```

`Dockerfile.hosted` packages the existing three modules in one service because
[Render disks attach to one service instance](https://render.com/docs/disks).
The entrypoint initializes only `/var/data/uploads` and drops to UID 10001 before
migrations or network services. FastAPI listens on internal loopback port 8000;
Next.js exposes the platform's `PORT` and proxies `/api`. The worker shares the
private disk. No user photo is copied into the build or repository.

The entrypoint requires a PostgreSQL URL, enables secure cookies, disables automatic
schema creation, and derives the exact allowed origin from `RENDER_EXTERNAL_URL`.
Render's standard database URL is normalized to the installed psycopg 3 driver.
For a later custom domain, set `CIRCUITPILOT_ALLOWED_ORIGINS` to a JSON list of the
exact HTTPS origins you use, including the Render origin only if still needed.

The service health path `/api/v1/health/ready` checks database access and the worker's
recent heartbeat. `/api/v1/health` remains the inexpensive liveness endpoint.
Any child process exit shuts down the hosted bundle; SIGTERM is forwarded to owned
process groups with a bounded graceful shutdown. Migrations finish before serving.
Auto-deploy is configured to wait for GitHub checks to pass.

This is a single-instance pilot. Disk-backed deployments have a short outage during
replacement and cannot scale horizontally. Move photos to a reviewed object-store
adapter before splitting/scaling the modules. This change does not supply S3 support.
Do not install model-training dependencies in the web container; train separately.

The same hosted image can be rehearsed without provisioning Render resources:

```sh
docker compose -f compose.hosted-test.yaml up --build -d --wait
python3 scripts/smoke.py --base-url http://127.0.0.1:10000
docker compose -f compose.hosted-test.yaml down --volumes
```

This rehearsal uses production settings with bearer authentication over local HTTP;
browser cookies intentionally require real HTTPS. It uses only a disposable database
and volume. CI also restarts the app and verifies the persistent disk survives.

Before inviting external testers, inspect Render's database and disk backup status,
retention, billing alerts and memory usage. Record an actual restoration exercise
with a disposable database/disk before depending on backups. Platform disk snapshots
and database recovery have separate timelines; a coordinated restore must reconcile
image metadata and files. Application deletion cannot instantly erase retained
platform backups. See Render's [disk snapshot behavior](https://render.com/docs/disks).

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
