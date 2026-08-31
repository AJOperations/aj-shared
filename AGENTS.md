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

## Safety and authority

This is Platform-level shared-package work. Preserve public contract compatibility and test Flask and FastAPI paths with safe local data. Do not add credentials, publish a package, change repository visibility, alter downstream applications, merge, deploy, or change production behavior without explicit authority for that exact action. Treat local work, commit, push, merge, package publication, downstream adoption, deployment, and live verification as separate milestones.
