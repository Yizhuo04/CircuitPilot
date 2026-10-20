# CircuitPilot

An assembly copilot that will translate logical circuits into validated breadboard
guidance. This repository implements **Milestone 1's backend foundation**, with a
functional FastAPI API, typed contracts, deterministic netlist checks, and explicit
breadboard topology. It does not generate wiring instructions yet.

The source of truth is [the original product handoff](docs/product-handoff.txt).
See [architecture review](docs/architecture.md), [board assumptions](docs/board_specifications.md),
[API contract](docs/api.md), and [milestone continuity](docs/progress.md).

## Run locally

Prerequisites: Python 3.12 or 3.13, Git, and [uv](https://docs.astral.sh/uv/getting-started/installation/).
The lockfile was generated with uv 0.12.5. Commands below run from the repository root.

```sh
uv sync --locked
uv run --locked uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open [interactive API documentation](http://127.0.0.1:8000/docs).
No database, Node installation, AI API key, or external service is required.
`.env.example` documents optional Uvicorn settings; defaults work without copying it.
If you copy it to `.env`, Uvicorn does not automatically load that file: export the
variables in your shell or use the explicit options shown above.

In a second terminal:

```sh
curl -sS http://127.0.0.1:8000/api/v1/health
curl -sS http://127.0.0.1:8000/api/v1/circuits/validate \
  -H 'Content-Type: application/json' \
  --data-binary @backend/tests/fixtures/series_led.json
curl -sS -w '\nHTTP %{http_code}\n' \
  http://127.0.0.1:8000/api/v1/circuits/validate \
  -H 'Content-Type: application/json' \
  --data-binary @backend/tests/fixtures/invalid_netlist.json
```

Health returns `{"status":"ok","version":"0.1.0"}`. A valid fixture returns HTTP
200, `valid: true`, and `ready_to_build: false`, with explicit warnings. The invalid
fixture returns HTTP 422 with `unknown_pin` and `pin_in_multiple_nets` errors.
See [the API documentation](docs/api.md) for an example response.

## Verify

```sh
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked python -m app.export_schemas --check
```

The prepared GitHub Actions workflow targets Python 3.12 and 3.13; uploading it
requires the authorization step below. Tests enforce at least 90% statement
coverage. To update generated shared schemas and the reference board
fixture after an intentional contract change:

```sh
uv run --locked python -m app.export_schemas
```

Review the diff and version any incompatible contract or board change. Never edit
the generated JSON independently of its Python source.

## Repository map

```text
backend/
  app/
    main.py                  FastAPI composition and schema-error envelope
    api/routes.py            health and structural circuit validation
    schemas/                 Component, Net, Supply, Circuit, BoardModel, ValidationResult
    services/breadboard.py    direct conductive groups and explicit reference geometry
    services/circuit_engine.py  deterministic cross-object integrity checks
    export_schemas.py        reproducible shared contract/fixture generation
  tests/
    fixtures/                series LED, LED + button, deliberately invalid netlist
shared/
  circuit_schema.json
  board_schema.json
  validation_schema.json
  boards/bb830-reference-r1.json
docs/                        architecture, API, board evidence procedure, progress
frontend/README.md           frontend intentionally deferred to M3
ml/datasets/README.md        future data collection and evaluation requirements
.github/workflows/ci.yml
pyproject.toml
uv.lock
```

## Current contract and limits

- Supported components: resistor (`1`, `2`), LED (`anode`, `cathode`), normally-open
  push button (`1`..`4`), ideal jumper (`1`, `2`), supply terminal (`positive`, `negative`).
- Resistors require a positive finite `value_ohms`. Units are SI, with explicit
  `_ma` and `_mm` suffixes where used. Unknown fields, numeric strings, and unsupported
  component types are rejected. Physical footprints/orientation fields are not
  accepted until M2 defines and validates their semantics.
- Every declared pin must appear in exactly one net. Repeated net IDs, component
  IDs, or member references are rejected. One-pin nets are allowed for external
  terminals and passive open connections. An ideal jumper's pins must share a net.
- One supply is supported; its positive/negative mappings must resolve to distinct
  power/ground nets. Power and ground roles require a supply. All marked power/ground
  nets must map to that supply. Multiple supplies are unsupported.
- Provisional product envelope: `0 < voltage_v <= 12`,
  `0 < current_limit_ma <= 500`. These chosen limits are not a safety guarantee.
  Schema limits are 64 components and 128 nets; initial pilot circuits should remain
  within the handoff's 2–8 component scope.
- `valid` means **netlist structure only**. Device behavior, LED current limiting,
  physical LED orientation, shorts through internal button contacts, physical pin
  occupancy, layouts, and analog behavior are not verified in M1.
- Board `bb830-reference/r1` has 630 terminal holes and 200 explicitly segmented
  rail holes, synthetic coordinates, and **no physical measurement evidence**.
  It is a test fixture, not a released supported physical board.
- No persistence, user accounts, planner, frontend, camera verification, or trained
  ML model exists yet. The local API is unauthenticated and should remain bound to
  localhost. Public deployment hardening belongs before an external pilot.

Disconnect power before wiring; use a low-voltage, current-limited supply.
Neither these checks nor a future photograph prove electrical safety or continuity.

## GitHub

Private source repository: [Yizhuo04/CircuitPilot-dev](https://github.com/Yizhuo04/CircuitPilot-dev).
Never commit credentials, user uploads, or model weights. CI needs no project
secrets. Configure your own Git author name/email before making new commits.

The current GitHub login can push source code but lacks the OAuth `workflow`
scope. GitHub rejected uploading `.github/workflows/ci.yml`; the complete workflow
is saved in the local checkout as a separate commit awaiting authorization. From
that original checkout, enable hosted CI with:

```sh
gh auth refresh --hostname github.com --scopes workflow
git push origin main
```

Complete the GitHub login/consent flow when prompted. This changes the GitHub
credential's scope; it is not an application API key. The remote repository has no
hosted CI run until the workflow is uploaded. All verification commands above work
without hosted CI. See [progress](docs/progress.md) and [verification evidence](docs/verification.md).

## Next milestone

M2 adds footprints, occupancy, terminal placement, an ideal-conductor union-find
graph, and exact logical/physical net equivalence checks. Required regressions
include missing jumpers, unexpected shorts, center-gap errors, and functional
device terminals remaining electrically distinct. See the scoped plan in
[progress](docs/progress.md). M1 does not start M2 automatically.
