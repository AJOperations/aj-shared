# Suite adoption contracts — local 2.2.0 candidate

This is an additive Python-only foundation, not a Home implementation. Import
`aj_shared.suite`, `aj_shared.transport`, `aj_shared.runtime_identity` and
`aj_shared.adoption` explicitly. Existing status, Flask/FastAPI, public-app,
HQClient and identity APIs remain compatible.

## Attention and provenance

`validate_attention(payload, allowed_origin=...)` validates schema major 1,
strict existing status, separate provenance, bounded complete snapshots and
producer-owned items. Unsupported majors, duplicates, unsafe destinations,
invalid calendar dates, unknown timezones, extra fields and inconsistent empty/
partial/unavailable states fail closed. Query strings/fragments are intentionally
excluded from this first destination contract; introduce a reviewed contract
extension if a real producer needs safe query parameters. Date-only values remain
date-only; qualified instants and IANA local-rule zones remain distinct.

`validate_provenance` never turns fetch time into successful freshness. Consumers
must discard protected cached results when authority is revoked/uncertain.
`protected_read` denies before executing its reader unless the caller passes
literal verified `True`; this is an explicit enforcement seam, not a verifier of
browser-supplied user IDs. The producer authenticates and filters records before
creating any title, count, link or snapshot. Shared supplies no cache or domain
signal producer. Home owns composition, deduplication across placements, ordering,
resolution/expiry presentation and recipient-specific cache invalidation.

## Bounded transport

Construct one reusable `BoundedTransport(TransportPolicy(...))` per app/dependency,
or pass `transport_policy=` to an app-scoped HQClient. Policy controls connect,
read and total seconds, maximum response bytes and in-flight capacity. Defaults
are synthetic starting values, not measured fleet budgets. All calls reject
redirects, sanitize dependency failures and propagate validated operation references.
401/403, rate limit, invalid response, oversize, timeout and capacity have distinct
codes. Writes are never automatically retried; an interrupted write reports
`outcome_unknown`. Successful legacy response shapes remain unchanged.

A bounded daemon worker lets the caller return even during stalled DNS or custom
adapters. Its slot remains occupied until the worker exits, so repeated timeouts
cannot create unlimited workers. Socket resources may outlive the caller until
connect/read timeout or adapter completion. Do not construct a transport per call;
use a thread-safe adapter and no shared mutable user-cookie state. There is no
queue, retry stack, circuit breaker, cache or server-side fan-out orchestrator.
The existing default HQClient path is preserved for backward compatibility;
adopting total budgets is explicit. Flask/FastAPI consumers can supply their
configured HQClient without moving credentials into browser code.

## Safe records and identity

`operation_reference` validates opaque correlation only. `validate_diagnostic`
accepts bounded safe identifiers, route templates, outcomes and timing, never
headers, cookies, raw URLs, SQL or form payload fields. `emit_diagnostic` returns
False on sink failure so ordinary reads remain usable; validation errors still
surface to the implementer. Event/dependency identifiers must be configured codes,
not interpolated record IDs. Shared does not silently intercept requests.

`validate_runtime` checks explicitly provided artifact metadata;
`support_identity` returns only app/schema/support-owner fields unless privileged
access was established by the caller. Missing values use `Unknown`; no Git,
environment dump, provider lookup or asserted deployment observation is generated.

`record_audited_write` owns a fresh local transaction. It supplies event ID,
verified actor, server time, target/action/outcome and operation reference. The
write and audit sink MUST use that same connection and neither callback may
commit. Sink failure rolls back the write. Pass stable actor/target IDs only after
server authorization. The caller's adapter must provide transaction context
management; use an explicit adapter for drivers that do not. No distributed
transaction or external-write automation is implied. Readers use independently
verified access and business actors get no routine audit editing/deletion seam.

`start_job`, `finish_job`, `interrupt_stale_job` and `validate_job` retain safe
counts, run ID, logical operation reference, attempt, truthful freshness and
restricted recovery reference. A retry gets a new run ID with the same logical
reference. Failed/partial/interrupted runs cannot advance last-success time.
The app chooses and records interruption thresholds; helpers do not run a scheduler.

Use fake sinks until stream readers, storage ownership, retention/deletion and
volume ceilings are approved. No default company retention, surveillance,
productivity ranking or automatic employee context collection is supplied.

## Upgrade and rollback

Run `python -m pytest -q`, `python scripts/compatibility_ci.py`, build the wheel
and source archive, install the wheel in a clean environment, then run
`python -m aj_shared.adoption`. It loads the packaged four-type synthetic fixture.
`check_compatibility(2)` deliberately fails the schema-1 gate. Test the installed
artifact, not only a checkout. The CI matrix retains Python 3.9/3.14 and all
Flask/FastAPI/open-app/file/identity groups; suite is an additional group.

After separate publication approval, consumers pin an immutable 2.2.0 release tag
and record its wheel/source checksum, resolved commit and app artifact. Prior
2.1.1 is the rollback baseline; retain the prior app artifact and configuration.
Code using the new imports cannot simply downgrade its dependency: roll back the
application change too. Data/draft rollback remains app-owned. Core and UI have
independent versions. Home and actual source integrations, hosted cross-origin
behavior, real-consumer critical journeys and managed-environment rollback remain
pending; package-only tests cannot complete those gates.
