<!-- Current approval supersedes the historical local-only execution boundary below. -->

**Publication authorization — 2026-09-13:** Christine approved the recommended Core-first source publication and independent Shared/UI foundation releases. Home releases and all real-consumer adoption remain deferred. Preserve Core's untagged 1.0.0-rc.1 candidate; publish Shared 2.2.0 and UI 0.2.0 only after their release checks pass. Main publication can trigger existing automatic hosting builds; no manual deployment or infrastructure/credential change is included.

# Current suite-adoption handoff — 2026-09-13

**Status:** Local 2.2.0 candidate; no publication or adoption
**Owner:** Christine Thoren
**Review when:** Candidate changes or a consumer/release is authorized

Fresh baseline: main `39477dd`, published immutable `v2.1.1`. The foundation fixes
were reused, not rewritten; no open Shared PR existed at verification. Scope is
Platform / additive functionally material foundations under Christine's explicit
Core/Shared/UI local implementation approval. Home/domain apps remain separate.

[Suite contract and adoption guide](SUITE-ADOPTION.md) documents schema-1 attention/
provenance, bounded dependency transport, safe diagnostics/runtime identity,
transactional audit and job lifecycle helpers. Four package-owned synthetic signal
types and a deliberately incompatible contract gate are included in the wheel.
Shared remains Python-only. Default legacy HQClient behavior stays compatible;
new total budgets are explicitly adopted per app/dependency. No live source,
recipient identity mechanism, caching or domain signal production is invented.

Verification: **328 tests passed** on Python 3.14 (two existing upstream
Starlette/anyio deprecation warnings). All six compatibility groups pass, including
Flask, FastAPI, open-app, file processing, identity and suite. The source archive
and wheel build. Installed-wheel synthetic adoption, rollback and packaging
follow-up are recorded below after final packaging. Prior released 2.1.1 installed
artifact passed all **307 baseline tests**; no package/source tag was moved.

Use `/private/tmp/aj-suite-venv/bin/python -m pytest -q`,
`python scripts/compatibility_ci.py`, `python -m build --no-isolation` and, from a
clean installed wheel, `python -m aj_shared.adoption`. Tests cover budget/capacity,
timeout, malformed/oversize, 401/403/429, write ambiguity/no retry, correlation,
redaction, audience gates, audit rollback, job interruption/freshness and schema
mismatch. Remote Python 3.9 CI remains unrun for these local commits.

Remaining: real recipient/source authorization and caches, Home composition,
measured app budgets, approved audit/job/diagnostic storage/readers/retention and
real-consumer/hosting validation. Publish only after review and separate approval,
with Core coordination first and independent UI release; retain immutable 2.1.1
plus the prior app artifact for rollback. New imports require rolling back app
code with the package. No fleet or Home completion is claimed.

## Packaging closeout — 2026-09-13

Implementation commit `e7fdf37`. The clean candidate wheel and source archive
built successfully. Installing the wheel into a separate target confirmed
version 2.2.0 and all four packaged synthetic items. A deliberately incompatible
schema-major expectation failed as required. All six compatibility groups passed.
The installed released 2.1.1 baseline passed its 307 tests for rollback coverage.
No tag, package release, consumer or provider was changed.

---
## Historical foundation handoff (superseded source/publication status)

# Current handoff

## Release follow-up — 2026-09-13

Christine authorized the v2.1.1 patch release, source merge, immutable tag and GitHub release assets. This follows the verified Core → Shared → UI remediation merges. No live consumer testing or adoption is included: the packages are foundations for future apps. Core's coordination reference is `60f30b6`; keep existing v2.1.0 immutable. Release CI and synthetic package installation are the evidence gates. The local-remediation record below is historical; its publication exclusions have been superseded for this release only.


**Status:** Accepted foundation fixes committed locally; unpublished
**Owner:** Christine Thoren
**Last verified:** 2026-09-13
**Review when:** Source changes, release is authorized, or Azure cutover is scoped

## Scope and source

Branch `fix/accepted-foundation-review-20260913` starts from verified main and
immutable v2.1.0, `e8ba7b0894fc07509abbf7bec3e52f65b3a7fd38`.
Implementation commit: `824167b`. Durable local checkout:
`/Users/christine.thoren/Developer/aj-apps/foundation-fixes-20260913/aj-shared`.
Christine authorized coordinated local Core/Shared/UI remediation only.
The 2026-09-13 confirmed disposition in the fleet foundation review supersedes
its original recommendations and earlier release authority.

## Completed locally

- Finding 4: Flask/FastAPI share exact endpoint versus trailing-slash subtree
  matching. `/api/apps` never grants anonymous access to `/api/apps-private`
- Finding 5: TTL-aware validation/cache resolution; corrupt/future timestamps
  fail closed; JSON endpoints keep 401 responses under default-deny. Dependency
  failures carry a correlated 502, distinct from expired/missing identity
- Finding 6: Flask stores one Core configuration/client per application;
  auth and proxy use HQClient's redirect rejection, response-size bound and
  structured errors. Base URL and platform secret snapshots stay isolated.
  FastAPI rejects a mismatched HQClient destination and uses the same transport
- `/auth/account` navigates to Core's `/account/password` page. Core implementation
  `e438909` completes an authenticated login handoff and owns password changes
  on its own cookie origin. No HQ Home or consumer recovery UI was changed

## Verification

307 tests passed on local Python 3.14. All five compatibility groups passed:
Flask, FastAPI, open-app, file-processing and identity. Wheel and source archive
built successfully in an isolated build environment. These are unreleased
snapshots, not replacements for the immutable v2.1.0 release.

New tests reproduced exact-path bypass, JSON redirect interception, stale
validation, future/corrupt cache timestamps, destination mismatch and transport
failures before the fixes. Two-app destination/credential isolation, API/page
failures, FastAPI actual transport, logout, public paths and retained open-app
proxy behavior now pass. The existing suite retains transport timeout, invalid
JSON, oversize, redirect and CSRF cases. Two upstream Starlette/httpx deprecation
warnings remain; Python 3.9/3.14 remote CI has not run on these local commits.

Core's real PostgreSQL regression suite also ran a bounded in-process integration
against this checkout: actual Core routes, synthetic sessions and separate
origins, with no live integration calls. See Core's existing handoff for the
`CORE_TEST_SHARED_PATH`/`CORE_TEST_POSTGRES_DSN` command prerequisites.

## Intentional deferrals and publication

Preserve findings 1/2/3/7: current redirect/persistence mechanism, intentional
password defaults, open-app proxies and fleet-wide data access. The existing
fleet `AZURE-MIGRATION-GAMEPLAN.md` carries the removal/review gates. Public apps
must remain supported after that redesign. Status contract v2.1.0 and earlier
NEXT-UPDATE-REVIEW.md follow-ups remain unchanged; EasyAuth rollout is separate.

Publish Core's compatible handoff/account changes first, then review and release
new immutable Shared/UI versions before separately approved consumer adoption.
Do not retag v2.1.0. No push, merge, package publication, deployment, credential
change, consumer change or production verification occurred in this task.
