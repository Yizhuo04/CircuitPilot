# CircuitPilot API

Base: `http://127.0.0.1:8000`. Interactive docs: `/docs`. OpenAPI: `/openapi.json`.
Canonical paths use `/api/v1`; the shorthand `/health` in the roadmap is not an alias.

## GET /api/v1/health

HTTP 200:

```json
{"status": "ok", "version": "0.1.0"}
```

## GET /api/v1/health/ready

Readiness returns the same shape as liveness: HTTP 200 with `status: "ok"`, or
HTTP 503 with `status: "unavailable"`. It checks a database query and, when
`CIRCUITPILOT_REQUIRE_WORKER_HEALTH=true`, the recent worker heartbeat. The hosted
configuration enables that requirement. Responses are not cached; failure details
and connection strings are not returned. Use this path for host health checks.

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
      "message": "Structural checks do not verify physical wiring, device polarity, LED current limiting, or electrical safety. This endpoint does not validate a physical assembly plan.",
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
problem in an invalid request. This stateless endpoint saves no data. Product routes below persist owner-scoped resources.

## Accounts and saved workflow

The interactive OpenAPI document is the precise request schema for all routes.
Register/login with `{email, password}` (12–128 characters). Responses contain a
public user, bearer token and HttpOnly SameSite=Strict session cookie. Tokens are
opaque, hashed in storage and expire; logout revokes the active session. Browser
cookie-authenticated writes require an allowed `Origin`. The web proxy preserves
same-origin requests. API clients can instead send `Authorization: Bearer TOKEN`.

| Method | Route under /api/v1 | Behavior |
| --- | --- | --- |
| POST | /auth/register, /auth/login | Create account or session |
| GET | /auth/me | Current public user |
| POST | /auth/logout | Revoke current session |
| DELETE | /auth/account | Delete owned project data, photos and account |
| GET | /circuit-library | Three editable logical circuit examples |
| GET | /board-models | Catalog status summaries |
| GET | /board-models/{id}?revision=r1 | Explicit reference geometry/connectivity |
| POST, GET | /projects | Create or list owned projects |
| GET, DELETE | /projects/{id} | Retrieve owned versions/photos or delete project |
| GET | /projects/{id}/export | Export metadata/plans and authenticated photo URLs |
| POST | /projects/{id}/circuits | Validate and append immutable circuit version |
| POST | /plans | Generate and persist independently checked reference plan |
| GET | /plans/{id}, /plans/{id}/steps | Retrieve plan and ordered steps |
| POST | /images/uploads | Mint ten-minute, single-use owned upload ticket |
| PUT | /images/uploads/{token} | Upload actual JPEG/PNG bytes, authenticated |
| GET | /images/{id}/content | Private normalized PNG; expired images inaccessible |
| DELETE | /images/{id} | Delete photo and related annotations/runs |
| PATCH | /images/{id}/consent | Enable/withdraw future training consent for owned photo |
| POST | /verification-runs | Queue manual homography with four named reference points |
| GET | /verification-runs/{id} | Pending/running/needs_confirmation/failed result |
| POST | /images/{id}/annotations | Append draft/reviewed annotation version |
| GET | /datasets/export | Latest reviewed labels on owned, consented, unexpired photos |
| POST | /assistant/messages | Explain a selected step after revalidating its stored layout |
| POST | /pilot-sessions | Start control/guided timing for an owned project |
| POST | /pilot-sessions/{id}/complete | Record observed error/help counts and completion time |
| GET | /pilot-sessions | Export owned pilot measurements |

Example plan request:

```json
{"circuit_version_id":"RETURNED_VERSION_ID","board_model_id":"bb830-reference","board_revision":"r1","seed":0}
```

Planning failure returns HTTP 422 with `error.code` such as `search_exhausted`,
`unsupported_size`, `reversed_led`, `missing_current_limiting` or
`ideal_supply_short`. Exhausted bounded search is not a proof of mathematical
infeasibility. A successful plan includes immutable input digest, board revision,
planner version/seed, component pin mappings, jumpers, steps and validation.
All current plans remain reference-only and not ready to build.

Upload ticket request: `{project_id, consent_for_training:false}`. PUT the raw image
to its returned `upload_url` using the same account. Do not log/share that URL.
The default byte limit is 10 MB; images are at least 32 pixels per side and at most
20 megapixels. Actual format and decoding are checked; re-encoding strips metadata.

Verification request:

```json
{
  "plan_id":"OWNED_PLAN_ID", "image_id":"OWNED_IMAGE_ID",
  "calibration_points":[
    {"hole_id":"A1","x":80,"y":40},
    {"hole_id":"J1","x":540,"y":40},
    {"hole_id":"J63","x":540,"y":440},
    {"hole_id":"A63","x":80,"y":440}
  ]
}
```

Coordinates above are illustrative and must be selected from the actual photo.
The image and plan must belong to the same owned project. Results contain expected
overlays, uncertainty and `electrically_verified:false`. Without evaluated detector
weights, `component_detection_available:false` and observations are empty. No
confidence scores are invented. Degenerate, mirrored, out-of-image or extreme
calibration selections fail explicitly.

Non-schema product errors use `{error:{code,message}}`; unknown/inaccessible
resources return the same 404. Conflicting states return 409, expired sessions 401,
invalid cookie origins 403, rate limits 429, and oversized bodies 413. Invalid body
schemas retain the versioned ValidationResult 422 envelope described above.
