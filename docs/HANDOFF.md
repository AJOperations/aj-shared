# Current handoff

Last verified: 2026-09-10
Branch: main
Release line: `v1.6.0`

## Active objective

The neutral AJ Core Job client surface is complete. Version 1.6.0 adds `core.job.read`, `HQClient.get_core_job(hq_job_id)`, and cursor-capable `HQClient.list_core_jobs(limit, cursor)`. Both call AJ HQ's additive, versioned `/api/core/v1/jobs` contract. No consumer app was migrated in this session.

## Current verified state
- Local: clean after the release commit.
- Committed: Job methods, scope, tests, metadata, CHANGELOG, and README are committed on `main`.
- Pushed: immutable tag `v1.6.0` is published at release handoff commit `3a3662d`; `main` also contains publication record `b88753f`.
- Merged: direct `main` release; no pull request was required.
- Staging deployed: not applicable — this is a Python library.
- Staging verified: not applicable.
- Production deployed: consumer adoption is intentionally deferred.
- Production verified: the upstream AJ HQ Job contract is already live; unauthenticated production requests return its expected 401 rather than a route 404.

## Next actions

- In separate, one-repository passes, upgrade each approved consumer and add only its canonical `hq_job_id` storage/backfill. Preserve Job # compatibility reads and quarantine ambiguous mappings.
- Do not treat this package release as consumer adoption or as authority to alter Job workflows.

### Retired PR #2 follow-up

PR #2 (`codex/overnight-aj-shared-20260730`, `a6eeae2`) was closed on 2026-09-10 without merge. It was based on the v1.4.0 era and is not a safe merge target after the v1.5.0 and v1.6.0 releases. Its package work was not already merged; its later Core client work is separate.

Start a new package-only branch from current `main`; do not reopen or merge the retired branch. Split the former work as follows:

- **ON-020 — carry forward.** Put Flask and FastAPI tag handling behind one fail-closed normalizer. Accept only a list or JSON list; reject mappings, tuples, malformed JSON, and other wrong-shaped claims. Keep the shared 1,200-second cache constant and retain the deterministic tampered-cookie regression test. This closes the current adapter inconsistency in authorization behavior.
- **ON-030 — carry forward.** Add the representative compatibility command and GitHub Actions workflow to current `main`. Cover Flask, FastAPI, open-app, file-processing, and identity contracts, then run the complete package suite. Keep the workflow read-only and package-only; it is not consumer deployment evidence.
- **ON-040 — defer as a separately scoped decision.** Protected runtime identity is not implemented or adopted. Before coding it, update its design to use tagged consumer pins (not floating `main`), current release metadata, and the build-record evidence required by ADR 0012. A package-only carrier still does not establish runtime identity until an approved consumer injects and verifies the values.

For a future combined release, rebase the selected ON-020/ON-030 changes onto the current public exports, Core client tests, changelog, and version. Give ON-040 its own explicit inclusion decision. Run the full package suite and `git diff --check`; then present the release version, immutable tag, rollback tag, and consumer-adoption boundary for approval.

## Blockers / unknowns

Consumer-by-consumer Core field migration remains deliberately deferred. The only package-planning decision is whether ON-040 is selected after its tagged-release/build-evidence design is refreshed; ON-020 and ON-030 are ready to implement on a current branch.

## Do not touch

- Do not change AJ HQ legacy `/api/jobs/*` routes; the Core Job routes are additive.
- Do not add vendor auto-creation, Sage ingestion, or contract/PO fields here.
- Do not pin consumers to `@main`; use an immutable tag.

## Relevant files

- `aj_shared/hq_client.py` — Core Job read methods.
- `pyproject.toml` — version 1.6.0.
- `tests/test_hq_client_core.py` — route and scope coverage.
- `CHANGELOG.md` and `README.md` — published API surface.
- `aj_shared/aj_auth.py` and `aj_shared/fastapi_integration.py` — ON-020 tag-handling boundary.
- `.github/workflows/` and `scripts/` — ON-030 compatibility automation, when implemented.

## Verification

- `pytest -q`: 86 passed (two third-party deprecation warnings only).
- `python -m build --wheel`: built `aj_shared-1.6.0-py3-none-any.whl` successfully.
- `git diff --check`: clean.
- Retired PR #2 review, 2026-09-10: branch-only implementation was not present in current `main`; a fresh PR-head suite passed 82 tests on Python 3.14 (two third-party deprecation warnings). The stale branch conflicts with current `CHANGELOG.md` and package-root exports, so it must not be merged directly.

> Overwrite this file when transferring active work between agents/tools. Keep only current state that matters to the next agent; do not append a running history.
