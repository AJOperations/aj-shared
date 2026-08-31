# aj-shared agent instructions

Work from the requested task outward. Do not preload repository documentation.

## Context routing

- Shared-package implementation/debugging: inspect relevant code and tests first.
- Package orientation/build details: read `README.md` and `pyproject.toml` only when needed.
- Continuing prior work or switching tools/agents: read `docs/HANDOFF.md`.
- Cross-system, HQ, auth, ownership, or downstream-contract work: start with `AJOperations/aj-hq/docs/ARCHITECTURE.md`, then read only the relevant focused HQ/contract document.
- Release/publishing work: read only the relevant packaging/release material.
- Historical reasoning: use Git/PR history only when needed.

Do not crawl all docs or downstream repositories for orientation. Inspect a sibling/downstream repo only when the requested task actually crosses that contract boundary. Current code and tests are authoritative for implemented package behavior; if prose conflicts, flag it as stale rather than launching a broad audit unless the conflict blocks the task.

## Working autonomy

Do not ask permission to inspect, plan, edit task-owned files, or run safe local tests/checks. Complete and verify the work first.

When ready to publish the repository change, recommend **staging** or **main** with a brief reason, then ask once for authorization. Unless the user narrows it, that approval covers commit, push, PR creation/update, and merge to the recommended target. Do not ask separately for each Git step. Package publication or downstream adoption is not included in that Git approval and remains a separate operation.

## Safety and authority

This is Platform-level shared-package work. Preserve public contract compatibility and test Flask and FastAPI paths with safe local data. Treat local work, commit, push, merge, package publication, downstream adoption, deployment, and live verification as separate evidence milestones even when one approval covers multiple Git steps. Package publication, downstream application changes, repository visibility/access changes, secrets, external writes, destructive changes, and manual deployments require separate explicit approval.
