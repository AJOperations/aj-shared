# Current handoff

Last verified: 2026-09-01
Branch: main
Last verified commit: 6f5425d (no new commit made — a tag was cut on this existing commit)

## Active objective

No active build work in progress. Only action this session: cut and pushed the `v1.5.0` tag at the existing commit `6f5425dd1ada901c4c61b17f16bfde4694888d24` (the CHANGELOG.md entry for 1.5.0 already existed, describing the AJ Core v1 HQClient methods — it had just never been tagged). Done in response to a production incident in `aj-budget-builder`: that app was pinned to `aj-shared@main` (a floating ref), a stale build cache served an install missing `HQClient.list_core_clients`, and the app crash-looped. Per this repo's own CHANGELOG.md `## Notes` convention ("pin a tagged release, never main"), consumer apps should pin to `@v1.5.0` (or newer), not `@main`. Full incident writeup: `aj-budget-builder`'s `docs/HANDOFF.md`.

## Current verified state
- Local:
- Committed:
- Pushed:
- Merged:
- Staging deployed:
- Staging verified:
- Production deployed:
- Production verified:

## Next actions

## Blockers / unknowns

## Do not touch

## Relevant files

## Verification

> Overwrite this file when transferring active work between agents/tools. Keep only current state that matters to the next agent; do not append a running history.
