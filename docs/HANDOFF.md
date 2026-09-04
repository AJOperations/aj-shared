# Current handoff

Last verified: 2026-09-04
Branch: main
Release line: `v1.6.0`

## Active objective

The neutral AJ Core Job client surface is complete. Version 1.6.0 adds `core.job.read`, `HQClient.get_core_job(hq_job_id)`, and cursor-capable `HQClient.list_core_jobs(limit, cursor)`. Both call AJ HQ's additive, versioned `/api/core/v1/jobs` contract. No consumer app was migrated in this session.

## Current verified state
- Local: clean after the release commit.
- Committed: Job methods, scope, tests, metadata, CHANGELOG, and README are committed on `main`.
- Pushed: `main` is published at the release handoff commit `3a3662d`; immutable tag `v1.6.0` is published at that same commit.
- Merged: direct `main` release; no pull request was required.
- Staging deployed: not applicable — this is a Python library.
- Staging verified: not applicable.
- Production deployed: consumer adoption is intentionally deferred.
- Production verified: the upstream AJ HQ Job contract is already live; unauthenticated production requests return its expected 401 rather than a route 404.

## Next actions

- In separate, one-repository passes, upgrade each approved consumer and add only its canonical `hq_job_id` storage/backfill. Preserve Job # compatibility reads and quarantine ambiguous mappings.
- Do not treat this package release as consumer adoption or as authority to alter Job workflows.

## Blockers / unknowns

None for this library release. Consumer-by-consumer field migration remains deliberately deferred.

## Do not touch

- Do not change AJ HQ legacy `/api/jobs/*` routes; the Core Job routes are additive.
- Do not add vendor auto-creation, Sage ingestion, or contract/PO fields here.
- Do not pin consumers to `@main`; use an immutable tag.

## Relevant files

- `aj_shared/hq_client.py` — Core Job read methods.
- `pyproject.toml` — version 1.6.0.
- `tests/test_hq_client_core.py` — route and scope coverage.
- `CHANGELOG.md` and `README.md` — published API surface.

## Verification

- `pytest -q`: 86 passed (two third-party deprecation warnings only).
- `python -m build --wheel`: built `aj_shared-1.6.0-py3-none-any.whl` successfully.
- `git diff --check`: clean.

> Overwrite this file when transferring active work between agents/tools. Keep only current state that matters to the next agent; do not append a running history.
