# Verification record — 2026-10-20

The current software supports a real account → circuit → plan → guided steps →
private photo → manual calibration → export/delete workflow. Hardware, trained-model
accuracy and business acceptance remain separate gates.

## Automated evidence

The complete public CI run for source commit `ceaeafa` passed all four jobs:
[GitHub Actions run 39371081806](https://github.com/Yizhuo04/CircuitPilot/actions/runs/39371081806).
It recorded 151 backend tests, 95.05% statement coverage, two browser workflow tests,
container builds, four healthy running services and a complete HTTP smoke flow.
A subsequent interpreter-selection correction in `dd0a8a3` ensures the Python 3.13
matrix cannot silently fall back to the repository's 3.12 version pin. The final
interpreter-verified run is recorded below.

| Check | Observed result |
| --- | --- |
| Local backend full run before final heartbeat regression | 148 passed, one PostgreSQL test skipped; 95.43% coverage |
| Additional electrical regression suite | 16 passed, including unrelated-branch reversed-LED regression |
| Worker heartbeat regression | Passed for absent, recent, stale and future timestamps |
| Lint/format, strict mypy | Passed; 33 application modules type checked |
| Shared schemas and board fixture consistency | Passed |
| Next.js production build and TypeScript | Passed locally and in CI |
| Frontend formatting | Passed in CI |
| Local real Chromium workflow | Two tests passed in 21.7 seconds |
| Mobile validation/overflow | Passed at 390-pixel width; invalid inputs cannot produce plans |
| Visual QA | Inspected desktop assembly and mobile validation screenshots |
| Clean local clone | Locked offline install and three-circuit package imports passed |
| Current source distribution/wheel | Built; wheel contains all three circuit fixtures and worker |
| Single-command launcher | Starts backend, worker and frontend; owned processes stop on Ctrl+C |
| Local complete HTTP smoke | Account/project/circuit/plan/steps/private photo/calibration/export passed; temporary account deleted |
| Worker maintenance CLI and healthcheck | Passed against the local running application |
| Docker stack in CI | PostgreSQL, backend, frontend and worker all healthy; full HTTP smoke passed |
| Physical continuity / footprints | Not measured; all current plans remain reference-only |
| Real-photo model training/evaluation | Not performed; no consented labeled dataset or trusted weights supplied |
| User recruitment / pilot benefit | Not performed; instrumentation/protocol only |
| Public hosted deployment | Not provisioned; hosting account/domain not selected |

The Docker startup test exposed a missing worker healthcheck, which was fixed with
an actual loop heartbeat rather than bypassing service health. Browser testing
exposed/fixed initial example loading overwriting edited JSON. Test fixtures and
model doubles are explicitly synthetic; these results are not real detector accuracy.

## Test coverage

Tests cover every terminal row, center trench, isolated/split rails, unknown holes,
strict schemas and references, supply roles/polarity, ideal-conductor partition
comparison, missing jumpers/shorts, occupancy/reference geometry, independent planner
gates, seeded reproducibility, owner isolation, immutable versions, revocable
sessions, upload decoding/single use, consent withdrawal, data exports/deletion,
manual calibration uncertainty, interrupted-job recovery, annotation provenance,
leakage-safe splits, detection metrics, and optional adapter contracts.

## Previous interpreter-verified run

[Run 39371387080](https://github.com/Yizhuo04/CircuitPilot/actions/runs/39371387080)
passed all four jobs for commit `dd0a8a39d3cdc63300e2abbde452a95187125411`:

- Python **3.12.15**: 151 tests passed in 47.80 seconds; **95.05%** coverage.
- Python **3.13.16**: 151 tests passed in 51.50 seconds; **95.05%** coverage.
- Both interpreter identities were asserted before running checks. The real
  PostgreSQL migration/product test ran rather than skipping.
- Web: production build, type/format checks and **two browser tests passed**.
- Containers: images built, all four services became healthy, and the complete
  HTTP smoke flow passed before temporary resources and volumes were cleaned up.

The documentation commit following this code revision changes no executable source;
CI deliberately skips Markdown-only updates.

Do not treat earlier job labels as proof of the interpreter used. The corrected
workflow asserts `sys.version_info` against its requested matrix value before checks.
The original M1-only report is preserved separately in `m1-verification.md`.

## Hosted pilot release checks

The latest executable revision is `c2ed6e11226f3bfed193ae214c5ecee38ba385de`.
[Run 39376980415](https://github.com/Yizhuo04/CircuitPilot/actions/runs/39376980415)
passed all five jobs:

- Verified Python 3.12.15: **173 passed** in 48.34 seconds, **94.66% coverage**.
- Verified Python 3.13.16: **173 passed** in 31.24 seconds, **94.66% coverage**.
- Both include the real PostgreSQL migration, JSONB and product test. Strict mypy
  passed for 34 application modules; lint, formatting and exported schema checks passed.
- Production frontend build, type/format checks and **two browser tests** passed (6.6s).
- Original Compose stack: four healthy services and full HTTP smoke passed.
- Hosted image: Python/OpenCV plus the Debian-compatible Node runtime built and
  started under production settings with PostgreSQL 17 and a private disk. Full
  account/project/circuit/plan/steps/upload/calibration/export/delete smoke passed.
- Container PID 1 and the worker heartbeat were asserted to use UID 10001. The
  service restarted cleanly, retained a disk marker, became healthy again, and
  passed the complete HTTP smoke a second time. Temporary resources were removed.

`render.yaml` passed validation against Render's published JSON Schema on 2026-10-20.
The account-specific Render API validation requires a workspace; it has not run.
These are GitHub-hosted container rehearsals, not evidence of a live Render deployment.
No hosting account, paid resource or public application URL has been created yet.

The additional 22 regressions cover managed database URL normalization, hosted
defaults, origin/port rejection, database/worker readiness failure, storage bootstrap
boundaries, process failures, SIGTERM handling and graceful-shutdown escalation.
