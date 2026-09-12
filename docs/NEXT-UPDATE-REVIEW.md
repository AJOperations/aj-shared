# Attached next-update recommendations: source reconciliation

Status: checked against remote main `885b8d7` on 2026-09-12.
Owner: Christine Thoren. Review when source or release policy changes.
Source: `AJ-SHARED-NEXT-UPDATE.md`, dated 2026-09-12.

The attachment labels its recommendations unapproved. The current request
explicitly approves bounded status-contract implementation and review publication.
It settles the vocabulary; no new vocabulary decision is needed.

| Item | Verified state and disposition |
|---|---|
| 1. Resolved artifact checksums | Absent. Current handoff defers ON-040. Retained for separate artifact-integrity work; a trustworthy expected digest, deterministic content rules and consumer build enforcement must be designed together. Hashing the installed artifact alone cannot establish that it matches its tag. This PR does not add a checksum claim or migrate consumer builds. |
| 2. Consumer fixtures in CI | The attachment's review-branch claim is stale. PR 7 merged ON-030; main has five representative package compatibility groups, full tests and Python 3.9/3.14 CI. These exercise Flask/FastAPI/open-app/file/identity boundaries, not real consumer builds. Reuse this existing runner; new status tests run in its full-suite step. Actual external consumer fixtures remain separate adoption work. |
| 3. Change-class/version table | The linked release runbook already gives patch = compatible fix, minor = compatible addition, major = breaking behavior. This PR is an additive minor candidate at a later approved release; no bump now. The proposed rule making every acceptance broadening major is not adopted as governance here. Review behavior consumers rely on, not signatures alone. |
| 4. Expand–migrate–contract exit | No consumer resolved-version inventory is implemented in this package. Retain the proposal: no removal until evidence covers every supported consumer and shows no reliance on the deprecated surface; missing evidence blocks removal. A resolved version alone is insufficient without a version-to-surface dependency map. No removals here. |
| 5. Deprecation/support window | Named replacements, a one-major deprecation window and support for current/previous majors are recommendations, not established package policy. Retain for an explicit release-policy decision; do not silently create a support commitment in a status-helper PR. |
| 6. Shared vocabulary | Confirmed absent from current exported code; implemented additively in this PR. Exact types, exports, errors, metadata and examples are in STATUS-CONTRACT.md. No legacy mappings or UI work. |

The Dropbox release runbook linked by README still contains floating-main consumer
instructions that conflict with current repository guidance and the settled immutable
tag policy. Follow immutable tagged adoption; the stale runbook is recorded here for
its documentation owner, not rewritten during this aj-shared-only task.

Items 1 and 4–5 remain follow-up work, not delivered capability. None blocks AJ UI
Phase 4's source-level status model once this contract is reviewed. Existing endpoints,
release tags, consumers and deployments are untouched.
