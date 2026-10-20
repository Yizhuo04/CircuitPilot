# Project continuity

Updated: 2026-10-20. Source of truth: `docs/product-handoff.txt`.

## Current authorization

The founder authorized moving source and project documents into the public
`Yizhuo04/CircuitPilot` repository and continuing all remaining project steps.
Preserve original public history. The private `CircuitPilot-dev` repo is historical.
GitHub workflow authorization was explicitly approved and is active. Keep routine
progress quiet; ask when external input, evidence or decisions are required.

## Implemented and remaining

| Milestone | Software state | Acceptance still requiring external evidence |
| --- | --- | --- |
| M1 foundation | Schemas, topology, validator, FastAPI, fixtures, tests | Physically measured board revision |
| M2 physical graph | Union-find, footprint/occupancy/clearance checks, net partition equivalence, short/missing-wire regressions | Measured parts and manufacturer-specific board |
| M3 planner + SVG | Seeded bounded planner, three circuits, model-derived SVG, ordered steps, responsive workspace | Physical assembly usability testing |
| M4 backend + calibration | Accounts/ownership, immutable versions/plans, PostgreSQL migration, private local storage, manual OpenCV alignment, durable jobs, consent/deletion/export | Selected production host/domain; storage/operations review |
| M5 ML experiment | Annotation UI, consented export/download, grouped split exporter, training/inference/evaluation adapters, provenance tests | Consented labeled real-photo dataset, trusted weights, actual training and held-out results |
| M6 pilot + reliability | Control/guided timing, observed error/help counts, export, protocol/security/deployment documentation | Recruitment, interviews, user measurements, institutions, willingness-to-pay and go/no-go evidence |

No physical board/footprint is released as supported. All plans remain reference-only,
`ready_to_build: false`. No camera output asserts electrical verification. No real
model performance, recruited users, interview outcomes or time savings are claimed.

## Execution evidence

Local Python 3.12.1: 148 tests passed, one PostgreSQL test skipped because no local
PostgreSQL service is installed; 95.43% statement coverage. Lint, formatting, strict
mypy and shared artifact checks passed. Next.js production build and TypeScript checks
passed. Real Chromium exercised registration, actual plan generation, hole inspection,
step completion, private upload, synthetic-image homography and persistence. A mobile
regression found/fixed initial example loading overwriting typed JSON. Final hosted CI run 39371387080 passed: 151 backend tests on verified Python
3.12.15 and 3.13.16, 95.05% coverage, real PostgreSQL migration/product checks,
two production browser flows, image builds, four healthy services and a complete
container HTTP smoke flow. Evidence is recorded in `verification.md`.

Docker is unavailable on the local host; container and real PostgreSQL checks are
executed successfully in GitHub Actions, not falsely claimed as local results. Real photos have
not yet been attached in this chat. The founder offered to send examples; use them
for calibration testing only unless explicit training consent is subsequently given.

## Decisions to preserve

- Keep intended logical nets, ideal conductive groups and functional device behavior distinct.
- Never report structure/graph equivalence as safe electrical operation.
- Reference button pairs are 1/2 and 3/4; this is an explicit convention requiring measurement.
- Generated JSON derives from typed Python contracts and must not drift.
- Board geometry/revision and circuit digest are immutable plan provenance.
- Supply policy is provisionally <=12 V and <=500 mA; it does not certify safety.
- Default photo retention is 30 days; worker performs physical deletion.
- The local filesystem adapter requires shared persistent storage. S3 is not implemented.
- The optional detector runtime is deliberately absent without reviewed data/weights.
- Browser-local step completion is per plan; no credentials/photos go into localStorage.

The current local branch is `main`, tracking the public `origin/main`. The old
private M1 branch is preserved locally as `archive/m1-private`. All current source
is committed. The single-command launcher is running backend, worker and frontend
at 127.0.0.1:8000 / 127.0.0.1:3000; the worker heartbeat check passes. No hosted
public application is provisioned; the hosting account/domain question is pending.

## Next required inputs

1. Attach example top-down board/circuit photos and identify manufacturer/model if known.
2. Measure actual rail continuity, geometry and part footprints before physical release.
3. Establish explicitly consented training/evaluation data grouped by setup/session.
4. Choose a Python/container host and domain before public deployment.
5. Supply/authorize actual pilot participants and institution contacts before outreach.

Continue useful software work independently of pending inputs. Do not fabricate the
physical, data or business outcomes needed to satisfy later acceptance gates.

## Resume

Inspect Git status and this file, then README, architecture and verification.
Run appropriate locked checks rather than reinstalling/rebuilding everything without
cause. Keep incremental commits and update evidence. The original handoff's M1-only
stopping instruction was superseded by the founder's explicit all-milestones request.
