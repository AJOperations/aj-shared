# Fleet compatibility CI

## Useful answer

Run this before reviewing a change to canonical `aj-shared/main`:

```bash
python scripts/compatibility_ci.py
python -m pytest -q
```

The first command exercises representative Flask, FastAPI, intentionally open,
file-processing, and identity contracts. The second runs every package test.
Both use synthetic fixtures and make no live HQ, provider, credential, consumer,
or production-data call.

## Contract groups

| Group | Representative boundary |
|---|---|
| `flask` | Existing public exports, Flask session/auth behavior, proxy security, and safe failures |
| `fastapi` | Optional adapter authentication, CSRF, route shapes, files, and package metadata |
| `open-app` | Unauthenticated reads and validation stub remain open while mutations keep CSRF |
| `file-processing` | Multipart forwarding, screenshot bounds, generic upstream failures, and response-size limits |
| `identity` | Exact session-cache expiry, roles/tags, signed sessions, and fail-closed malformed claims |

Run one group while developing with:

```bash
python scripts/compatibility_ci.py --group identity
```

These are representative package fixtures, not proof that a current consumer
build or deployed app is compatible. Every consumer adoption still records its
resolved shared commit and runs that app's own critical journeys.

The protected [runtime identity contract](RUNTIME-IDENTITY.md) explains how a
future consumer build supplies and verifies the exact app/shared commits and
environment without exposing arbitrary configuration.

## Hosted workflow and cost boundary

`.github/workflows/compatibility.yml` runs on pull requests and on pushes to
`main`, with one job for Python 3.9 and one for Python 3.14. Each job installs
the declared development extras, runs all five compatibility groups, and then
runs the complete package suite. The ten-minute timeout caps any single job, so
one workflow can consume at most 20 runner-minutes before GitHub setup overhead
or cancellation behavior.

Actual hosted duration and billed runner-minutes are **Unknown until the first
hosted run**. Record that first result before changing the matrix or timeout.
The workflow does not install, build, or deploy any consumer repository.

Local reference only—on 2026-07-30, Python 3.14 with an already-installed
editable development environment ran all five groups in 2.8 seconds of wall
time. Dependency installation and hosted-runner startup dominate CI duration,
so this local number is not a hosted cost estimate.

## Failure meaning

A group failure blocks a shared merge until the package defect or the
representative fixture is reviewed. Do not weaken a fixture merely because a
consumer currently behaves differently. A consumer-specific exception belongs
in that consumer's reviewed adoption plan; app-, client-, issuer-, host-, and
provider-specific policy stays out of this package.
