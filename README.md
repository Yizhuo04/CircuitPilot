# CircuitPilot

**From circuit to connection.** A functional web workspace for importing small
logical circuits, generating graph-checked reference breadboard layouts, following
pin mappings, and aligning privately uploaded photos.

Current public source: [Yizhuo04/CircuitPilot](https://github.com/Yizhuo04/CircuitPilot).
Original repository history is preserved. CircuitPilot-dev is the historical M1 copy.

## Run locally

Prerequisites: Python 3.12/3.13, [uv](https://docs.astral.sh/uv/getting-started/installation/),
Node.js 24, and pnpm 11.25.0. Both dependency lockfiles are committed.

```sh
git clone https://github.com/Yizhuo04/CircuitPilot.git
cd CircuitPilot
uv run --locked python scripts/dev.py --install
```

Open **http://127.0.0.1:3000** and create an account. The launcher runs backend,
worker, and frontend; Ctrl+C stops its processes. No cloud database or AI API key
is required. Development data is stored under ignored `data/`. API docs: http://127.0.0.1:8000/docs.

Alternatively, run these in three terminals from the repository root:

```sh
uv sync --locked
uv run --locked uvicorn app.main:app --reload --no-access-log
```

```sh
uv run --locked python -m app.worker
```

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

Use a reference circuit or paste JSON, generate a layout, inspect holes and steps,
upload a photo, then select A1 → J1 → J63 → A63 for a manual expected-layout overlay.
`.env.example` documents optional overrides. Next.js proxies `/api/` to FastAPI.

## Implemented software

- Typed versioned schemas and descriptive structural validation.
- Explicit terminal strips/rail segments, ideal-conductor union-find, occupancy,
  reference footprints, body clearance, disconnected nets, and unintended shorts.
- Seeded bounded greedy planning, jumper routing, and an independent validation gate.
  Three reference circuits; at most eight components and ten added jumpers.
- Interactive model-derived SVG, named pin mappings, ordered steps, and browser-local
  completion tracking per plan.
- Accounts, revocable sessions, owner-isolated projects, immutable circuit/plan
  snapshots, private uploads, export/deletion, consent and retention.
- Manual OpenCV homography and durable analysis jobs with recoverable leases.
- Reviewed photo annotations, consent-filtered dataset export, grouped split
  preparation, optional local detector adapters, training and evaluation tools.
- Guided/control pilot timers, observed error/help counts, and exportable measurements.
  Step explanations use validated deterministic content without requiring an LLM.

## Important engineering boundaries

The bundled board and footprints are **unverified references** with synthetic
geometry. Every current plan retains `ready_to_build: false`. Obtain measured
continuity, geometry, pin numbering, footprints and electrical-rule evidence before
physical use. Basic rules reject direct ideal supply shorts, reversed LEDs in
supported series branches, and LED supply paths without series resistance. They
do not establish safe current, power ratings, analog behavior, or arbitrary active
circuits. Supply limits of 12 V / 500 mA are a provisional product envelope, not a
safety guarantee. Disconnect power before wiring; do not energize unverified layouts.

**No CircuitPilot-trained detector or real-photo accuracy is bundled.** Default photo
analysis aligns expected geometry without inventing detections. Optional trusted,
evaluated weights can enable uncertain observations; real-model execution remains
untested until weights/data exist. Photos cannot prove electrical continuity.
No participants, interviews, time savings, or institutional commitments are claimed.
[Progress](docs/progress.md) separates software from hardware/data/pilot acceptance.

## Verify

```sh
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked python -m app.export_schemas --check
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

With the application running:

```sh
pnpm --dir frontend exec playwright install chromium
pnpm --dir frontend test:e2e
```

CI targets Python 3.12/3.13, real PostgreSQL migrations/product flow, browser tests,
and container builds. Local PostgreSQL tests skip unless
`CIRCUITPILOT_TEST_POSTGRES_URL` is configured. See actual [verification evidence](docs/verification.md).
Regenerate shared contracts with `uv run --locked python -m app.export_schemas`;
review/version incompatible changes instead of independently editing JSON artifacts.

## API and deployment

```sh
curl -sS http://127.0.0.1:8000/api/v1/health
curl -sS http://127.0.0.1:8000/api/v1/circuits/validate -H 'Content-Type: application/json' --data-binary @backend/tests/fixtures/series_led.json
```

Structural success returns `valid: true`, `validation_scope: netlist_structure`, and
`ready_to_build: false`. Saved resources require authentication. See [API](docs/api.md).

Docker Compose defines PostgreSQL, backend, worker, persistent private uploads,
and frontend. Set a strong `POSTGRES_PASSWORD` in untracked `.env`, then run:

```sh
docker compose up --build
```

Ports bind to loopback. Production requires HTTPS, secure cookies, migrations,
backups and a selected hosting account; no hosted deployment is claimed.
Read [deployment](docs/deployment.md), [architecture](docs/architecture.md),
[board evidence](docs/board_specifications.md), [ML workflow](ml/README.md),
[pilot protocol](docs/pilot-protocol.md), and [security](SECURITY.md).
The original [product handoff](docs/product-handoff.txt) remains the source of truth.
