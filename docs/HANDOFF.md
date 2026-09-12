# Current handoff

Last verified: 2026-09-12
Release line: `v2.1.0`

## Objective and authority

Christine approved PR 8 for merge and delegated the release adjustment on
2026-09-12. Use a new immutable v2.1.0 tag for the additive status contract;
retain v2.0.0 unchanged. Christine confirms no app consumes v2.0.0.
Consumer migration, AJ UI implementation and deployment remain separate.

## Contract and verification

- `aj_shared.status` adds strict request outcomes, combined qualifiers and
  separate retryability. Root exports and JSON examples are documented in
  [STATUS-CONTRACT.md](STATUS-CONTRACT.md).
- 296 local tests and all five compatibility groups passed on Python 3.14.
  PR 8 checks passed on Python 3.9 and 3.14 before release metadata adjustment;
  the updated head must pass again before merge and tag.
- Version-adjusted local suite: 296 passed; all five compatibility groups passed.
  The 2.1.0 source distribution and wheel built; wheel metadata, source and
  exported helper were verified. Two upstream deprecation warnings remain.
- Existing endpoint responses, auth and proxy contract 1.0.0 stay unchanged.
- Exact merge/tag and final CI evidence live in PR 8 and the Git release record.
  A version in source does not establish that its tag has been published.

## Attachment and preserved follow-ups

[NEXT-UPDATE-REVIEW.md](NEXT-UPDATE-REVIEW.md) reconciles the attachment.
Compatibility CI already landed in PR 7. Artifact-integrity and support-policy
recommendations remain follow-ups, not delivered capability.

The EasyAuth/Entra adapter follows HQ's Azure pilot and verified real claims.
ON-040, Azure hosting, Key Vault, consumer adoption and deployment remain separate.
No AJ UI files or consumer repositories were changed. Future consumers should
adopt an approved immutable tag, never this review branch or floating main.
