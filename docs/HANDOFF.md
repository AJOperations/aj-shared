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
