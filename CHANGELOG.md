# Changelog

All notable changes to `aj-shared` are documented here. Subagents and
retrofit sessions read this before upgrading an app's pinned version — see
`WAVE-PLAN.md`.

## [1.0.2] — 2026-07-10

Fixes real errors in `AJ_FLEET_ORIGINS`, found while verifying AbbVie
Invoicing's pilot retrofit. The original list was built partly from
inference (Phase 0 audits' self-reported "Live URL" lines) rather than
values confirmed directly by Christine — two entries were wrong as a
result:

- `aj-staffing.up.railway.app` didn't exist at all. Staffing's real live
  URL is `ajstaffingmodel.netlify.app` (current production, Netlify —
  not being touched; an eventual Railway migration is separate, future
  work) plus its active `ajstaffingmodel-testing.up.railway.app` testing
  subdomain.
- The Invoice Tracker entry, sourced from its own audit's mention of a
  "historical Railway service slug," was also wrong. Confirmed real URL:
  `aj-invoicing.up.railway.app`.

Every entry is now either the long-standing HQ URL or a value Christine
confirmed directly on 2026-07-10: `aj-tools.up.railway.app` (Tools — repo
also renamed `AJFilemaker` -> `AJTools` to match, since the old name had
drifted from the live product name), AbbVie's staging URL
(`aj-abbvie-invoice-builder-staging.up.railway.app` — previously missing;
only production was listed, but staging is where this wave's actual
testing happens), and `ajbookings.up.railway.app` /
`aj-shows.up.railway.app` / `aj-bid.up.railway.app`. Rooms doesn't get an
entry — no auth, no backend, excluded from the wave.

Lesson for future entries, going forward: confirm each app's real URL(s)
directly with Christine, never infer from a doc alone, and add both
production and any active staging/testing subdomain.

## [1.0.1] — 2026-07-10

Fixes two real bugs in `configure_session_security()`, found while
debugging a login redirect loop on AbbVie Invoicing (first app fully on
this package):

- **`SESSION_COOKIE_HTTPONLY`/`SAMESITE`/`SECURE` were never actually being
  set.** The previous code used `app.config.setdefault(...)`, but Flask
  pre-populates all three of these keys in `app.config` at `Flask()`
  construction time (to `True`/`None`/`False` respectively) — so
  `setdefault()` was a guaranteed no-op every time. Every app calling
  `configure_session_security()` was silently running on Flask's stock
  defaults instead. Fixed to direct assignment.
- **No `ProxyFix`.** Railway terminates TLS at its edge and forwards to
  the container over plain HTTP — without `ProxyFix`, Flask has no way to
  know the original request was HTTPS. `request.url` built from the wrong
  scheme is exactly what `require_auth()` uses as the `next` redirect
  target sent to HQ, so this could corrupt the whole login redirect
  round-trip, not just cookie flags. `configure_session_security()` now
  wraps `app.wsgi_app` in `werkzeug.middleware.proxy_fix.ProxyFix`.

Both fixes verified directly: config values actually change now (confirmed
via a real `Flask()` instance, not just reading the code), and
`request.url`/`request.scheme` correctly report `https://` when
`X-Forwarded-Proto: https` is present (confirmed via Flask's test client
with that header set).

No API changes — existing calls to `configure_session_security(app)` pick
up both fixes automatically on upgrade.

## [1.0.0] — 2026-07-09

Initial release. Phase 1 of the AJ Unification Wave.

### Added
- `aj_auth.py` — session-cached HQ token validation (20-minute TTL fix
  ported from Invoice Tracker, the fleet's best-in-vintage copy), `has_tag()`,
  `require_auth()` / `require_auth(role=...)`. No issuer-specific code —
  identity issuer details live in HQ config only, per the wave's hard rule.
- `aj_proxy.py` — Flask blueprint registering the full standard HQ Data Proxy
  route set (`/api/apps`, `/api/apps/all`, `/auth/validate`, `/auth/logout`,
  `/api/users`, `/api/rates`, `/api/rates/lookup`, `/api/people`,
  `/api/codes`, `/api/codes/fees`, `/api/codes/expenses`, `/api/jobs`,
  `/api/jobs/<job_number>`, `/api/clients`, `/api/contracts`,
  `/api/users/me/password`, `/api/feedback`, `/api/dropbox/list`,
  `/api/dropbox/upload`, `/api/email/send`) in one `register_proxy()` call.
- `contract.py` — `CONTRACT_VERSION` + `/api/contract` (gated by
  `X-AJ-Key`), auto-registered by `register_proxy()`. Reports
  `{app_name, contract_version, aj_shared_version}`; `aj_shared_version` is
  read from the installed package's own metadata so apps can't misreport it.
- **Security hardening** (OWASP Top 10 2025-aligned — see
  `reference-app-standards`'s Security Standards section and
  `audit/OWASP-2025-SECURITY-STANDARDS.md` in the wave workspace for the full
  mapping):
  - `require_env_secret()` — fail-loud-in-production secret loading, the
    same pattern already proven independently in HQ's and Bookings' `app.py`.
  - `configure_session_security()` — explicit `SESSION_COOKIE_SECURE` /
    `HTTPONLY` / `SAMESITE` flags.
  - `register_error_handlers()` — generic JSON error responses, no stack
    traces to the client; server-side logging on 500s.
  - `csrf_protect` — custom-header requirement on mutating routes.
  - `rate_limited()` — in-memory sliding-window limiter for auth-adjacent
    endpoints (safe under the fleet's `--workers 1` hard rule).
  - `build_set_clause()` — safe, allowlisted dynamic `SET` clause builder,
    replacing the fleet-wide hand-rolled f-string pattern found in nearly
    every app during the Phase 0 audit.
  - `configure_cors()` / `AJ_FLEET_ORIGINS` — fixed origin allowlist,
    replacing both fully-open `CORS(app)` calls and overly-broad
    provider-domain regexes (`.*\\.up\\.railway\\.app`) found in several apps.
  - **`register_proxy()` routes are session-gated by default.** Every route
    except `/api/apps` (intentionally public per HQ's own design),
    `/auth/validate` (the auth check itself), and `/auth/logout` now requires
    `@require_auth`; `/api/apps/all` requires `@require_auth(role='admin')`.
    Closes a real gap found during the AbbVie pilot retrofit: these routes
    forward to HQ using the server-held `PLATFORM_SECRET`, not the visiting
    user's session, so without local gating an unauthenticated visitor could
    pull job/people/rate/client data through any app's proxy. Verified via
    test client: all gated routes redirect unauthenticated requests; the
    three exceptions don't.
  - **Known follow-up, not fixed here:** `/api/apps/all`'s underlying HQ
    route (`app.py`) gates on `_is_admin()`, which checks a session cookie or
    `?token=` — neither of which a server-to-server proxy call carries. The
    local gate above stops a non-admin from ever reaching this route, but HQ
    will still 401 the forwarded call regardless of the local user's role.
    Fixing HQ's side is a trust-model decision (does it accept the app's
    local admin check + `PLATFORM_SECRET` as sufficient proof?), not made
    here — flagged for Christine.
  - **`require_auth_by_default(app, public_paths=[...])`** — an app-wide
    `before_request` hook, opt-in per app. Flips the model from "opt in to
    protection" (decorate each route with `@require_auth`) to "opt out to
    public": every route requires a valid session unless its path matches
    an explicit allowlist the app passes in (e.g. Bookings'
    `public_paths=['/book/', '/event/']`, Invoice Tracker's `['/s/']`).
    A route a developer forgets to protect now fails safe by default
    instead of silently staying public. `aj_proxy.py`'s own intentionally-
    public endpoints (`/api/apps`, `/auth/validate`, `/auth/logout`,
    `/api/contract`) are always exempted automatically — an adopting app
    doesn't need to re-list them. Verified via test client: an undecorated
    route redirects unauthenticated requests; an allowlisted path doesn't.
    Motivated by Christine's stated goals for the auth model (2026-07-09):
    seamless single-login across apps (already the existing token-redirect
    + per-app session cache — this doesn't change that), protect real data
    from outside the AJ ecosystem by default, and still allow deliberately
    public pages (freelancer/client-facing submission and booking surfaces).
    This does not retroactively change any app already using the per-route
    decorator only — it's an explicit adoption per app, not automatic.

### Notes
- Apps pin a tagged release (`pip install git+https://github.com/AJOperations/aj-shared@v1.0.0`)
  — never `main`.
- `PLATFORM_SECRET` env var is required (same value as HQ and every other
  app). `AJ_HQ_BASE` env var can override HQ's base URL for local dev.
