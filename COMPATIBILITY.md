# Fleet compatibility CI

Run this before reviewing a change to canonical `aj-shared/main`:

```bash
python scripts/compatibility_ci.py
python -m pytest -q
```

The first command exercises representative Flask, FastAPI, intentionally open,
file-processing, and identity contracts. The second runs every package test.
Both use synthetic fixtures and make no live HQ, provider, credential, consumer,
or production-data call.

| Group | Representative boundary |
|---|---|
| `flask` | Public exports, session/auth behavior, proxy security, and safe failures |
| `fastapi` | Optional-adapter authentication, CSRF, route shapes, files, and metadata |
| `open-app` | Unauthenticated reads and validation stub remain open; mutations keep CSRF |
| `file-processing` | Multipart forwarding, screenshot bounds, and safe upstream failures |
| `identity` | Session expiry, roles/tags, signed sessions, and malformed-claim denial |

Run one group while developing with:

```bash
python scripts/compatibility_ci.py --group identity
```

These are representative package fixtures, not proof that a current consumer
build or deployed app is compatible. Every consumer adoption still records its
resolved shared tag and runs that app's own critical journeys.

## Hosted workflow and cost boundary

`.github/workflows/compatibility.yml` runs on pull requests and pushes to
`main`, using Python 3.9 and 3.14. Each job installs the declared development
extras, runs all five compatibility groups, then runs the complete package
suite. The ten-minute timeout caps each job at ten runner-minutes.

Actual hosted duration and billed runner-minutes are **Unknown until the first
hosted run**. Record that result before changing the matrix or timeout. The
workflow does not install, build, or deploy any consumer repository.
