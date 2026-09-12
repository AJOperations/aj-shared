# Request status contract

Status: proposed additive API for review; unreleased. Owner: Christine Thoren.
Verified: 2026-09-12. Review when the API or approved AJ UI vocabulary changes.

AJ UI Phase 4 can implement against this wire specification at source/review
level. Production adoption still needs review, merge, an approved immutable
package release and separately approved consumer changes. Existing v2.0.0 does
not contain these helpers. Package version and proxy contract version are unchanged.

## Exact Python exports

All are exported from both `aj_shared` and `aj_shared.status`:

- `RequestOutcome`: `Literal["loading", "ok", "empty", "denied", "failed", "unavailable", "queued", "unknown"]`
- `DataQualifier`: `Literal["stale", "partial", "cached"]`
- `REQUEST_OUTCOMES` and `DATA_QUALIFIERS`: tuples in the order above.
- `StatusPayload`: TypedDict with the wire fields below. Types alone do not validate input.
- `StatusValidationError`: a `ValueError` subclass.
- `build_status(status: RequestOutcome, *, qualifiers: List[DataQualifier], retryable: bool, **metadata: object) -> StatusPayload`
- `validate_status(value: object) -> StatusPayload`

Both functions validate and return a fresh JSON-ready dictionary, including fresh
list fields. Neither mutates input. `build_status` requires all three axes explicitly;
its metadata keywords are only `as_of`, `missing`, and `retry_after`.
`validate_status` accepts a decoded JSON object, not JSON text or an endpoint envelope.
Invalid field values raise `StatusValidationError`; missing required builder arguments
are normal Python `TypeError`s. Error wording is diagnostic, not a stable machine code.
Neither function emits a fallback. Callers handle invalid input explicitly; never
catch an error and silently substitute `ok` or `empty`.

## Wire fields

| Field | JSON type | Requirement |
|---|---|---|
| `status` | string | Required; exactly one approved outcome |
| `qualifiers` | array of strings | Required; zero or more approved qualifiers, no duplicates |
| `retryable` | boolean | Required; true or false, never a string or integer |
| `as_of` | string | Required exactly when `stale` is present |
| `missing` | array of strings | Required exactly when `partial` is present; nonempty, each description nonblank |
| `retry_after` | integer | Optional only with `retryable: true`; seconds from receipt, 0 through 9007199254740991 inclusive |

`as_of` uses a deliberately bounded timestamp format:
`YYYY-MM-DDTHH:MM:SS[.ffffff](Z|±HH:MM)`. Fractional seconds may contain
1–6 digits. A real calendar date and time with a known offset are required.
Naive timestamps, leap seconds, `-00:00` (unknown offset), and offsets beyond
23:59 are rejected. The helper preserves the supplied timestamp; it does not
check freshness, compare clocks, or determine whether data is stale.

`missing` describes absent data/sources in consumer-owned words; it is not a new
identifier vocabulary. Text and qualifier order are preserved. `retry_after`
is a delay hint, not an HTTP header, absolute date, or automatic retry command.
The integer bound preserves exact representation in JavaScript. Unknown fields,
nulls, aliases, wrong container types, duplicate qualifiers, orphan metadata,
and coerced booleans/numbers are rejected. Optional fields must be omitted when
not applicable; null does not mean absent.

All outcome/qualifier combinations are structurally allowed, including simultaneous
`partial` and `stale`. The consumer owns their truthfulness. `unknown` is an explicit
valid outcome, never inferred from malformed input. `empty` says a check found no
results; `unavailable` says the check could not be completed. No helper maps HTTP
codes, legacy statuses, business meaning, or visual tones into system states.

## JSON examples

Successful but stale and incomplete, from cached data:

```json
{"status":"ok","qualifiers":["stale","partial","cached"],"as_of":"2026-09-12T14:02:00Z","missing":["Source B has not responded"],"retryable":true,"retry_after":30}
```

A completed check with no results:

```json
{"status":"empty","qualifiers":[],"retryable":false}
```

A check that could not complete:

```json
{"status":"unavailable","qualifiers":[],"retryable":true}
```

Explicit uncertainty:

```json
{"status":"unknown","qualifiers":[],"retryable":false}
```

Server use (Flask/FastAPI can serialize the result normally):

```python
from aj_shared import build_status

state = build_status(
    "ok", qualifiers=["stale", "partial"], retryable=False,
    as_of="2026-09-12T14:02:00Z", missing=["Source B has not responded"],
)
```

The module uses only Python standard-library functionality. It introduces no
framework objects, endpoints, service calls, storage, environment settings, or
frontend behavior. Existing package imports/dependencies remain unchanged.
Embedding the object into an endpoint response is a separate consumer decision;
this change does not reshape or reinterpret any existing response.
