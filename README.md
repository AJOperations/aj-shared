# aj-shared

Shared authentication, HQ proxy, and contract-versioning package for AJ internal applications. The current package version is `1.4.0`; the shared route contract remains `1.0.0`.

## What it provides

- Flask authentication, role and tag checks, secure-session setup, CSRF protection, and bounded rate limiting
- The standard Flask HQ proxy and `/api/contract` route
- Optional FastAPI authentication and proxy support through `aj-shared[fastapi]`
- A framework-neutral `HQClient`

See [`CHANGELOG.md`](CHANGELOG.md) before changing a consumer. Consumer upgrades are explicit; a package change does not update or deploy an application by itself.

## Local setup and tests

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e '.[dev]'
./.venv/bin/python -m pytest -q
```

Python 3.9 or newer is required.

## Configuration contract

Consumers provide configuration. Never place secret values in this repository.

- `AJ_HQ_BASE` — HQ base URL; Flask helpers use the current production HQ URL when omitted
- `PLATFORM_SECRET` — shared service credential used for protected HQ and contract requests
- `FLASK_SECRET_KEY` — Flask session-signing key
- `FLASK_ENV` — controls whether insecure development fallbacks are allowed
- `APP_SECRET_KEY` — session-signing key passed to the FastAPI integration

Review the consuming app's README and deployment configuration for the variables it actually uses.

## Main interfaces

Flask consumers import public helpers from `aj_shared`, including `require_auth`, `require_auth_by_default`, `get_current_user`, `has_tag`, `configure_session_security`, `csrf_protect`, `rate_limited`, `register_proxy`, and `register_contract_route`.

FastAPI consumers use `aj_shared.fastapi_integration.FastAPIHQ`. Framework-neutral consumers use `aj_shared.hq_client.HQClient`.

## Release and recovery

This repository is a package, not a hosted service. A technical release updates the version and changelog, runs the complete tests and package checks, merges the reviewed revision to `main`, creates a new immutable `vX.Y.Z` audit tag, and then updates consumers explicitly. Never move or reuse a tag. Keep `CHANGELOG.md`, `pyproject.toml`, the package metadata test, and the release tag aligned. A consumer rollback restores that consumer's last verified resolved package revision.

AJ approval, consumer sequencing, and evidence requirements live in Dropbox at `docs/runbooks/AJ-SHARED-RELEASE.md`. Contact AJ Operations before push, merge, tag publication, or consumer adoption.

## Technical boundaries

- Keep issuer-specific identity logic in HQ, not this package
- Keep the shared route contract backward compatible unless a coordinated breaking change is approved
- Confirm exact consumer origins; do not guess URLs or broaden CORS patterns
- Do not treat a package merge or release as consumer deployment authority
