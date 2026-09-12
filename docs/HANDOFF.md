# Current handoff

Last verified: 2026-09-12
Branch: `codex/aj-ui-status-contract`
Base: freshly fetched `origin/main` at `885b8d7` (v2.0.0 release line).

## Active objective and authority

Christine approved AJ UI Phase 3 and authorized this bounded aj-shared status
contract, tests, technical documentation, scoped commit/push and review PR.
Stop at review: no merge, tag, release, deployment or consumer migration.
Platform shared-package work; additive public functionality, preserving existing
behavior. Synthetic tests only; no live data, service or credential changes.

## Current verified state

- Current remote main was inspected: no compatible exported status helpers exist.
- This branch adds `aj_shared.status` and root exports. Exact API, JSON examples,
  metadata requirements and rejection behavior: [STATUS-CONTRACT.md](STATUS-CONTRACT.md).
- Attachment recommendations were reconciled in [NEXT-UPDATE-REVIEW.md](NEXT-UPDATE-REVIEW.md).
  Compatibility CI already landed in PR 7; artifact integrity and support-policy
  recommendations remain separate work, not delivered capability.
- Local Python 3.14: 296 tests passed; all five compatibility groups passed.
  Only two upstream FastAPI/Starlette deprecation warnings remain.
- Source distribution and wheel build passed. Build artifacts are temporary
  verification output, not a v2.0.0 release replacement. Package version remains
  2.0.0; this additive change is a minor candidate for a later approved release.
- `git diff --check` passed. Existing endpoints, auth, proxies and contract version
  1.0.0 remain unchanged. AJ UI and consumer repositories were not modified.
- Commit/push/PR and hosted CI evidence: see this branch's Git/PR record.
  Nothing from this branch is merged, released, adopted or deployed.

## Review gate

Review the strict wire choices: required three axes; `missing` descriptions for
partial data; known-offset timestamp for stale data; integer seconds for retry
hints; invalid input raises without fallback. The source dependency is implemented
for review. AJ UI Phase 4 can use the documented model after contract review;
installable consumer adoption needs merge, an approved immutable release, and
separate consumer approval. Do not pin consumers to this branch or `main`.

## Preserved separate workstreams

- v2.0.0 already includes the Core Job reads, fail-closed tag normalization and
  package compatibility CI. No consumer adoption is asserted by that release.
- The provider-neutral EasyAuth/Entra adapter follows HQ's Azure pilot and verified
  real injected claims; issuer-specific logic does not belong here.
- ON-040 artifact/build identity, Azure hosting, Key Vault and deployment remain
  separate. Do not change HQ legacy Job routes or introduce vendor/Sage workflows.

> Replace this handoff with the current checkpoint when work transfers; do not append a history.
