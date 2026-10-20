# Project continuity

Updated: 2026-10-20. Source of truth: `docs/product-handoff.txt`.

## Scope and state

M1 software foundation is implemented. Physical board verification is outstanding;
no physical board is released as supported. M2 implementation has not begun.

Implemented: repository/environment, strict typed circuit/board/result contracts,
three circuit fixtures, explicit 63-row terminal and split-rail reference topology,
deterministic netlist integrity, two FastAPI endpoints, shared JSON Schema,
regression tests, CI configuration, and local documentation. Frontend intentionally
deferred to M3 under section 17.8 of the handoff. No persistence, planner, camera,
or trained ML capabilities are claimed.

## Decisions to carry forward

- Do not union functional device terminals; physical ideal-conductor graph is M2.
- Do not turn `valid: true` into build readiness. M1 always returns
  `ready_to_build: false`, with scope `netlist_structure`.
- Board IDs/revisions and geometry must remain explicit and versioned. Reference
  rail splits are test assumptions, never proof about a user's physical board.
- Keep the provisional 12 V / 500 mA maximum supply policy and all-pins-assigned
  policy visible. Revisit them with pilot requirements and electrical-rule design.
- The four-pin normally-open button needs a documented footprint/contact-pair
  mapping before M2 can claim physical connectivity checks involving it.
- Shared artifacts derive from Python schemas/generator and are checked in CI.
- The existing `Yizhuo04/CircuitPilot` repository is public and initially contains
  only a README. The user selected a new private `Yizhuo04/CircuitPilot-dev`
  repository for this implementation. Preserve the original public repository.

## Verification evidence

Local Python 3.12.1: 75 tests pass, 99.65% statement coverage. Ruff lint and
format checks, strict mypy over 13 application modules, and generated artifact
consistency checks pass. The test client uses httpx2 as recommended by the
installed Starlette version; no dependency deprecation warning remains.

Real Uvicorn HTTP smoke check on localhost: health returns 200 and version
`0.1.0`; series LED returns 200 with `valid: true`, no errors, and
`ready_to_build: false`; the invalid fixture returns 422 with `unknown_pin` and
`pin_in_multiple_nets`. CI is configured for Python 3.12 and 3.13; its actual
remote execution is recorded separately after pushing.

Clean local clone: locked offline installation from the populated dependency cache
succeeds; all 75 tests and quality/schema checks pass again. A source distribution
and wheel build successfully. This verifies the declared environment rather than
relying on undeclared globally installed packages.

GitHub repository: `https://github.com/Yizhuo04/CircuitPilot-dev`, private.
GitHub rejected the initial push because the active OAuth credential lacks
`workflow` scope. Application source is pushed separately; the workflow is retained
as a separate local commit, ready to push after the user runs:

```sh
gh auth refresh --hostname github.com --scopes workflow
git push origin main
```

Run these in the original local checkout, not a new clone, which will not yet
contain the pending workflow commit. No hosted CI run is claimed. Python 3.13 is
configured in the pending matrix but has not been executed in this session.

## Hardware evidence required

Select the actual manufacturer's board model/revision, measure continuity and
isolation including rail splits, and record geometry and evidence. Follow
`docs/board_specifications.md`. This cannot be completed from the supplied handoff.

## M2 plan, pending user go-ahead

1. Define versioned placement, terminal mapping, jumper, footprint, and occupancy
   contracts. Start with narrowly specified tested parts; do not guess button pins.
2. Build ideal-conductor union-find from board strips, explicit jumpers, and known
   internal ideal contacts. Device leads map into groups independently.
3. Check logical/physical terminal partition equivalence in both directions,
   including supply terminals: disconnected intended nets fail, merged distinct
   nets fail. Report implicated nets, pins, holes, and ideal links.
4. Add known-correct hand-authored layouts plus missing jumper, short, occupancy,
   center trench, unsupported footprint, and polarity regressions. Keep functional
   component terminals distinct. Add meaningful graph invariance/property checks.
5. Stop before automatic placement/routing, which belongs to M3. Never expose an
   unvalidated layout as a buildable plan.

## Resume instructions

Read this file, the architecture review, and the original handoff. Inspect Git
status and existing code before editing. Run the locked verification commands in
README. Do not reinstall the full stack or implement later milestones at once.
Preserve error codes, documented scope, generated artifacts, and test invariants;
version incompatible changes. Update this file with evidence at each milestone.
