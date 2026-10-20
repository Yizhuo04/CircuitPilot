# Current architecture

CircuitPilot is a modular monolith: a Next.js/React workspace calls a FastAPI Python
backend through a same-origin proxy. SQLAlchemy 2 stores owned resources in SQLite
for local development or PostgreSQL with JSONB in deployment. Alembic provides an
explicit initial migration. The backend and worker share private local object storage.

## Correctness boundaries

1. `schemas/circuit.py` defines intended connectivity. Structural validation checks
   references, supported components/values, net uniqueness and supply roles.
2. `services/breadboard.py` provides explicit versioned geometry/conductive groups.
3. `services/footprints.py` enumerates narrow reference placements and body envelopes.
4. `services/placement_engine.py` performs bounded seeded greedy placement/routing.
5. `services/connectivity.py` independently checks occupied holes, geometry,
   terminal completeness, expected-net connectivity and distinct-net isolation.
   Union-find merges only ideal conductors, including explicit button contact pairs.
   Functional resistor/LED terminals remain separate.
6. `services/electrical.py` adds narrow structural electrical rules for supported
   resistor/LED branches, including pressed-button worst-case ideal shorts. It is
   not a simulator and does not establish numeric current/power-rating safety.
7. Only a passing independent graph report yields a saved reference plan. No current
   board or footprint has physical evidence, so build readiness stays false.

The planner makes up to twelve attempts, then reports bounded search exhaustion.
This is not a proof of infeasibility. Planning is limited to eight components and
ten added jumpers. The same input and seed produce identical plan content; database
resource IDs/timestamps intentionally differ when a new immutable snapshot is saved.

## Persistence and ownership

Users own projects; circuit versions reference projects, plans reference immutable
circuit versions, and steps are stored in sequence. Photos/annotations are project
resources. Verification runs reference a plan and a photo from the same project.
All read/write/export/delete paths check project ownership; inaccessible IDs return
404. Historical circuit and plan snapshots have no update endpoint.

Sessions are revocable opaque tokens stored as hashes; passwords use salted scrypt.
Browser cookies are HttpOnly/SameSite=Strict, and cookie-authenticated writes require
an allowed Origin. Production rejects insecure cookie/origin/database settings.
Production still needs account recovery/email verification, upstream request limits,
backups, monitoring and a reviewed deployment configuration before unrestricted use.

## Photos and jobs

One-use expiring upload tickets are scoped to owned projects. The local storage
adapter enforces actual PNG/JPEG decoding, dimensions/byte bounds and generated
object keys. Normalization strips EXIF/location metadata. Consent defaults false;
reviewed annotations alone never grant training permission.

Manual calibration projects model coordinates into the photo using OpenCV. It
rejects invalid/mirrored/degenerate/extreme selections and returns expected overlays
plus uncertainty. It does not infer continuity. A database-backed verification queue
uses atomic claims and recoverable leases. FastAPI schedules immediate work after
responding; a separate worker recovers pending/interrupted work and deletes expired
photos. Keep worker storage consistent with backend storage.

## ML and evaluation

The default application has no trained detector. Optional operator-selected trusted
local weights require matching hashes, evaluation metadata and class names. The
adapter can produce uncertain possible-component/endpoint observations; detections
cannot alter a plan or suppress electrical/physical validation. Actual real-model
execution awaits a consented dataset and evaluated weights.

Dataset exports require reviewed labels plus explicit consent. Setup, capture
session and identical content hashes form connected groups that never cross splits.
Exact hashes do not detect every near-duplicate; manually audit burst/session data.
Evaluation distinguishes per-class AP/precision/recall, duplicate detections and
uncalibrated scores. Training wrappers preserve provenance and evaluate test after
selection; no real-data metrics are claimed yet.

## Remaining critical evidence

- Measured manufacturer/revision-specific board continuity and geometry.
- Measured footprints, button pin pairs, part ratings, polarity/current rules.
- Real held-out photos, localization errors, detector metrics and calibration.
- Real participants, observed assembly outcomes and commercial validation.

These gaps cannot be resolved by more generated code. They remain release gates.
The original M1 review is preserved in `m1-architecture-review.md`.
