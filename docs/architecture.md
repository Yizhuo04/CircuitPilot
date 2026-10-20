# Architecture review — 2026-10-20

The modular monolith, structured inputs, deterministic graph gate, and separation
between uncertain visual observations and electrical facts are appropriate. No
fundamental rewrite is needed. The following gaps determine what can be released.

## Critical correctness gaps

1. **A physically verified board is missing.** The handoff describes 830-point
   boards but provides neither manufacturer/revision nor measurements. Software
   tests cannot establish physical rail continuity. M1 includes an explicit,
   unverified reference model; releasing a buildable plan requires recorded
   continuity measurements and measured geometry for a named board revision.
2. **Net equivalence is necessary but insufficient for electrical correctness.**
   Connected LED pins can still have wrong polarity or excessive current; a
   resistor elsewhere in a netlist does not prove current limiting. M1's response
   separates structural validity from build readiness. Later electrical-rule checks
   need part ratings, forward-voltage assumptions, supply limits, and supported
   topology restrictions. No LLM may substitute for those checks.
3. **Functional devices and ideal conductors need separate semantics.** Resistors
   and LEDs must not union their terminals. Ideal jumpers do. Four-pin push-button
   internal contact pairs depend on the selected footprint; that mapping must be
   explicit before layouts are supported. M1 knows pin names but does not assert
   button contact behavior. M2 must test component leads against the conductive
   graph without collapsing functional terminals.
4. **Pin naming alone is not a physical footprint.** Lead spacing, insertion
   restrictions, orientation, shared-hole policy, and clearance need a footprint
   catalog. Pixel geometry must derive from the same board revision. M1 rejects
   footprint/orientation input fields rather than silently ignoring constraints.

## Boundaries to preserve

- Schema validation handles shapes, supported variants, finite values, and bounds.
  Domain validation handles references, uniqueness, supply roles, and assignments.
  Both produce a consistent 422 error envelope, with codes and paths.
- Keep intended logical nets, actual ideal conductive groups, and device behavior
  distinct. M2 compares partitions of terminal references, detecting both split
  intended nets and merged distinct nets. Board topology alone is not that checker.
- Layout acceptance must fail closed. A bounded planner may legitimately report no
  layout. Infeasibility and search-budget exhaustion need distinct outcomes.
- Before M4 persistence, define immutable version IDs, board revision references,
  planner versions/seeds, and exact provenance. Supply mapping and board revision
  must be captured with a plan. Add owner checks before storing user resources.
- Before external uploads, add upload size/type limits, isolated object keys,
  ownership, retention/deletion, explicit training consent, and asynchronous jobs.
  These are future release requirements, not implemented security guarantees.
- ML remains downstream of deterministic geometry. Plan labels alone are not
  ground truth for photographs. Separate setups/sessions across evaluation splits;
  report occlusion and uncertainty rather than invent continuity evidence.

## M1 decisions

Use FastAPI/Pydantic v2 with a locked uv environment and no database dependency.
Keep domain modules independent of HTTP. Generate shared JSON Schema and board
fixtures from typed Python contracts; CI checks that artifacts do not drift.
Defer NetworkX until graph queries justify it; M1 grouping uses explicit group IDs.
Defer the complete physical conductive graph and union-find to M2, the frontend
to M3, persistence to M4, and ML experiments to M5.

Provisional supported supply limits (12 V and 500 mA maxima) and requiring every
declared pin to have a net are implementation policies, not requirements supplied
by a board manufacturer. Confirm them during pilot scoping. Disconnected pins
currently need explicit separate nets; optional unconnected-pin semantics would
require a versioned contract change.

Dependency workflow follows [uv's locked sync guidance](https://docs.astral.sh/uv/concepts/projects/sync/).
The schema-error adapter follows [FastAPI's request-validation extension point](https://fastapi.tiangolo.com/tutorial/handling-errors/).
