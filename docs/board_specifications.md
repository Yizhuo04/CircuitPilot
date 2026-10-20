# Board model: bb830-reference, revision r1

Status: **reference_unverified**. This is an explicit synthetic topology fixture,
not a measured product specification. There is no manufacturer association.

- 63 rows; columns A–E form one group per row, F–J another. E–F are separated
  by a trench; consecutive rows are isolated. 630 terminal holes, 126 groups.
- Four rails: `L_POS`, `L_NEG`, `R_POS`, `R_NEG`, each numbered 1–50.
  Indices 1–25 share the TOP group, 26–50 the BOTTOM group. Each rail is
  isolated from all other rails and terminal strips. 200 rail holes, 8 groups.
- `+` and `-` are printed labels only; they do not assign a circuit voltage or net.
- Coordinates are synthetic millimeters at 2.54 mm pitch. The reference origin is
  A1. Rail rows and positions are schematic and must not be used as a real photo
  template. The center trench is recorded as a keep-out rectangle.
- All 830 holes have explicit IDs, coordinates, and group IDs in
  `shared/boards/bb830-reference-r1.json`. No footprint is released as supported.
- Utilities: `get_hole`, `group_for_hole`, `are_directly_connected`, and
  `holes_in_group`. Unknown holes/groups raise domain errors. Reference footprint enumeration now lives in `services/footprints.py`;
  manual homography and hole-to-image projection live in `services/calibration.py`.
  None of these software utilities establishes physical board continuity.

## Evidence needed before physical support

Choose a manufacturer, part number, and identifiable board revision. Record board
photos/dimensions and measurement date, instrument, and method. With the board
unpowered and empty, measure continuity within every proposed conductive group
and isolation across groups, including every rail split and both trench sides.
Record any factory bridge or adapter jumper separately from built-in continuity.
Measure hole centers, pitch, trench, and rail geometry; account for board orientation.

Store results with the model revision and peer review them. Replace the synthetic
coordinates and topology only in a new model/revision, add regression fixtures,
and set `physically_verified` with an evidence reference only after actual
measurement. A nonempty evidence string is an audit pointer, not automated proof.
