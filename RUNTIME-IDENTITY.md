# Protected runtime identity

## Useful answer

`/api/contract` can now carry the app commit, shared-package commit, package
version, contract version, and environment that a build process supplied. It
does not make that information public, inspect a Git checkout at runtime, or
guess when build metadata is missing.

The existing `X-AJ-Key` protection remains required. Missing or invalid
metadata is returned as `null` with `all_fields_supplied: false`, so a missing
claim cannot look complete. `all_fields_supplied` means only that every value
has the right shape; it is not proof that the values match the running
artifact. Exact assurance requires the operator to compare this response with
the immutable build record.

## Protected response

The existing response keeps its compatible fields and adds
`runtime_identity`:

```json
{
  "app_name": "Example App",
  "contract_version": "1.0.0",
  "aj_shared_version": "1.4.0",
  "runtime_identity": {
    "app_commit": "0123456789abcdef0123456789abcdef01234567",
    "shared_commit": "89abcdef0123456789abcdef0123456789abcdef",
    "environment": "staging",
    "all_fields_supplied": true,
    "provenance": "externally_supplied_build_metadata"
  }
}
```

The package version comes from installed package metadata. The contract version
continues to identify the shared proxy contract independently. The three build
values are validated before they are returned:

- `AJ_APP_COMMIT`—the full 40- or 64-character Git commit for the app source
- `AJ_SHARED_COMMIT`—the full resolved commit installed from canonical
  `aj-shared/main`, not merely the word `main` or the package repository's
  current head
- `AJ_RUNTIME_ENVIRONMENT`—one of `local`, `development`, `test`, `testing`,
  `preview`, `staging`, or `production`

Wrong-shaped values, shortened commits, arbitrary environment names, and
newlines are not reflected. They become `null`.

Shape validation cannot distinguish a real Git commit from a 40- or
64-character hexadecimal secret. The three variables must contain build
metadata only. If an operator or build system puts a hex-shaped credential in
one of them, the protected endpoint will return it; that is a configuration
incident, not a redaction capability this helper can honestly claim.

## Threat and exposure decision

The endpoint stays protected because exact revisions and environment identity
help operators but also give an attacker unnecessary deployment detail. The
response therefore:

- uses the existing constant-time platform-key check
- defines no field for a URL, hostname, branch, repository credential,
  provider ID, user data, or production data
- validates a small fixed schema instead of reflecting arbitrary environment
  variables
- reports missing evidence as Unknown rather than deriving values from files,
  Git commands, package names, or provider conventions

The endpoint protects the metadata from anonymous access; it does not attest
that externally supplied values are true. The response labels that provenance
explicitly, and operators must compare the values with the build record before
calling a runtime identified.

This is an additive protected response field, so the package and identity/proxy
contract versions do not change. A consumer that rejects unknown response
fields must be corrected before adopting this revision.

## Build injection boundary

The package-side work ends at a protected, shape-validated carrier. Each app's
separately reviewed build process must inject the three non-secret values into
the artifact that is actually tested and released, and retain the immutable
build record an operator uses for comparison. A provider rebuild of the same
app commit may resolve a new shared commit, which is exactly why
`AJ_SHARED_COMMIT` must come from the install/build record.

Before setting these values for a consumer:

1. Resolve and record the full app commit
2. Install canonical `aj-shared/main` once and record the exact resolved shared
   commit from that install
3. Build the release artifact with all three values
4. Test that artifact; do not rebuild it between review and release
5. Query the protected contract endpoint and compare it with the build record
6. Keep the prior successful artifact and its two commits as the rollback unit

Until a consumer performs those steps, its response is a supplied claim—not
confirmed exact runtime identity. Completing that build binding requires a
consumer or provider change, so it is deliberately outside this package-only
queue item.

Changing a consumer repository, CI workflow, Railway/Netlify/Azure setting,
credential, or deployed environment is outside this package packet and needs
its own approval. No consumer or provider configuration was changed here.
