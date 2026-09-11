# Current handoff

Last verified: 2026-09-11
Branch: main
Release line: `v2.0.0`

## Active objective

The v2 modernization line establishes a clean, immutable package boundary
before Azure identity work. It includes the v1.6.0 AJ Core Job client surface,
one fail-closed tag normalizer shared by Flask and FastAPI, and representative
package-only compatibility CI. The standard proxy contract remains `1.0.0`.
No consumer app is upgraded by this release.

## Current verified state

- Committed and merged: PR #7 merged the ON-020 authorization cleanup and
  ON-030 compatibility CI into `main` at `7f634f7`.
- Release: `v2.0.0` is the intentional next adoption line. Its release commit
  records package version, changelog, README, test metadata, and this handoff.
- CI: the compatibility workflow passed on Python 3.9 and 3.14. Local full
  suite: 92 passed (third-party FastAPI/Starlette test-client warnings only).
- Deployment: not applicable — this is a Python library. Consumer adoption,
  hosting, Azure configuration, and production verification remain separate.

## What v2 changes

- **ON-020 complete:** Flask and FastAPI now accept only native lists or
  JSON-encoded lists for tags. Mappings, tuples, malformed JSON, and other
  wrong-shaped claims fail closed. Both adapters share the 1,200-second
  session-cache constant; the tampered-cookie regression is stable across the
  supported Python range.
- **ON-030 complete:** `.github/workflows/compatibility.yml` runs package-only
  Flask, FastAPI, open-app, file-processing, and identity checks on pull
  requests and `main` pushes. `COMPATIBILITY.md` describes its coverage and
  limits.
- **ON-040 deferred:** protected runtime/build identity is not part of v2. Its
  design must use tagged consumer pins and current build-record evidence before
  code begins.

## Next actions

1. Migrate HQ home to Azure, then prove the separately scoped Entra/EasyAuth
   claims adapter against its real injected claims. EasyAuth performs sign-in;
   a later v2.x package release should translate the verified principal to
   AJ's existing `id`, `name`, `email`, `role`, and `tags` model, failing
   closed on missing or ambiguous claims.
2. Update approved consumers one repository at a time to the immutable
   `v2.0.0` tag only when their own migration, critical-journey verification,
   and rollback path are approved. Preserve Job # compatibility and quarantine
   ambiguous Core mappings.
3. Keep ON-040, shared frontend/chrome work, Azure hosting, Key Vault, OIDC
   deployment trust, and consumer deployment as separate workstreams.

## Do not touch

- Do not change AJ HQ legacy `/api/jobs/*` routes; Core Job routes are additive.
- Do not add vendor auto-creation, Sage ingestion, or contract/PO fields here.
- Do not pin consumers to `@main`; use an immutable tag.
- Do not put issuer-specific Azure logic, Key Vault access, or deployment code
  in this package.

## Relevant files

- `aj_shared/identity.py` — shared fail-closed tag normalization.
- `aj_shared/aj_auth.py` and `aj_shared/fastapi_integration.py` — framework
  adapters using that normalization.
- `.github/workflows/compatibility.yml`, `scripts/compatibility_ci.py`, and
  `COMPATIBILITY.md` — package-only compatibility evidence.
- `aj_shared/hq_client.py` and `tests/test_hq_client_core.py` — v1.6.0 Core
  Job read surface retained in v2.

> Overwrite this file when transferring active work between agents/tools. Keep
> only current state that matters to the next agent; do not append a history.
