# M1 API

Base: `http://127.0.0.1:8000`. Interactive docs: `/docs`. OpenAPI: `/openapi.json`.
Canonical paths use `/api/v1`; the shorthand `/health` in the roadmap is not an alias.

## GET /api/v1/health

HTTP 200:

```json
{"status": "ok", "version": "0.1.0"}
```

## POST /api/v1/circuits/validate

Accepts a Circuit object as the entire JSON body, not a `circuit` wrapper. The
request contract is `shared/circuit_schema.json`. Use
`backend/tests/fixtures/series_led.json` for a complete request.

HTTP 200 for a structurally valid circuit:

```json
{
  "schema_version": "1.0",
  "valid": true,
  "validation_scope": "netlist_structure",
  "ready_to_build": false,
  "errors": [],
  "warnings": [
    {
      "code": "structure_only",
      "message": "Structural checks do not verify physical wiring, device polarity, LED current limiting, or electrical safety. No assembly plan exists yet.",
      "path": []
    },
    {
      "code": "disconnect_power",
      "message": "Disconnect power before wiring. Use a low-voltage, current-limited supply.",
      "path": []
    },
    {
      "code": "led_analysis_pending",
      "message": "LED polarity and a suitable series current-limiting resistor still require electrical analysis; resistor presence alone is insufficient.",
      "path": []
    }
  ]
}
```

Schema errors and cross-reference errors both return HTTP 422 with the same
ValidationResult envelope. `schema.*` codes describe malformed or unsupported
input. Domain codes include `duplicate_id`, `duplicate_member`, `unknown_pin`,
`unassigned_pin`, `pin_in_multiple_nets`, `missing_supply`, `unknown_supply_net`,
`supply_short`, `supply_role`, `unmapped_supply_net`, `supply_polarity`, and
`jumper_net_conflict`.

Example domain issue (inside `errors`):

```json
{
  "code": "unknown_pin",
  "message": "Pin 'R1.99' is not declared.",
  "path": ["nets", 0, "members", 3]
}
```

Paths use zero-based array indices; schema paths also include FastAPI's `body`
prefix. Clients should branch on codes, not human-readable messages. Schema
failure prevents domain checks, so errors are not guaranteed to exhaust every
problem in an invalid request. No data is saved. No M2–M6 endpoints exist yet.
