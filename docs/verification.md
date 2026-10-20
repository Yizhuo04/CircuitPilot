# M1 verification — 2026-10-20

Environment: macOS, CPython 3.12.1, uv 0.12.5. All packages resolved in `uv.lock`.
Tests and quality checks use the isolated project virtual environment.

| Check | Observed result |
| --- | --- |
| pytest | 75 passed in 2.60 seconds; no warnings |
| Statement coverage | 285 / 286 statements, 99.65%; gate is 90% |
| Ruff lint | All checks passed |
| Ruff format | 25 files already formatted |
| Strict mypy | No issues in 13 application modules |
| Generated contract/board consistency | Passed |
| Clean local clone + locked offline sync | Passed using populated dependency cache |
| Tests in clean clone | 75 passed in 2.71 seconds; 99.65% coverage |
| Quality/schema checks in clean clone | Passed |
| Source distribution and wheel build | Both succeeded |
| Live HTTP health | 200; status ok; version 0.1.0 |
| Live HTTP series LED fixture | 200; valid true; errors empty; ready_to_build false |
| Live HTTP invalid fixture | 422; unknown_pin and pin_in_multiple_nets |
| Hosted GitHub Actions | Not run: workflow upload requires additional OAuth scope |
| Physical board measurements | Not available; reference model remains unverified |

The uncovered statement is the exporter module's `if __name__ == '__main__'`
entry invocation; the CLI command was exercised separately. Tests cover API error
envelopes, unsupported versions/fields/types, finite positive values, uniqueness,
pin references, supply roles/polarity, jumper net conflicts, every terminal row,
center trench, row isolation, rail splits/isolation, unknown coordinates, topology
mutation isolation, malformed board definitions, and generated artifact drift.

These results do not establish electrical safety, correct physical wiring, LED
current limiting, physical footprints, camera performance, or ML accuracy.
Python 3.13 execution remains pending hosted CI authorization.
