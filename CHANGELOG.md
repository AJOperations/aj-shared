# Changelog

All notable changes to `aj-shared` are documented here. Review this file
before updating a consumer's shared-source reference.

## [Unreleased]

- Flask and FastAPI now share one 1,200-second default identity-cache TTL and
  one fail-closed tag normalizer. Both adapters accept list and JSON-list tag
  claims and reject malformed or wrong-shaped values such as mappings and
  tuples.
- Added Flask regression coverage for the exact TTL boundary, tag claim
  shapes, and missing-session behavior. The package and identity contract
  versions remain unchanged because this closes an inconsistent authorization
  edge case without changing valid inputs.

## [1.4.0] — 2026-07-30

- Cross-app tokens are removed from safe browser page URLs immediately after
  successful validation, while preserving every unrelated query value.
  JSON routes and non-GET requests do not redirect or lose their request body
  in either the Flask or FastAPI integration.
- `csrf_protect` now requires the exact shared frontend proof value
  `X-Requested-With: XMLHttpRequest`; the Flask and FastAPI logout routes now
  enforce CSRF before clearing the local session.
- HQ proxy requests reject redirects, cap JSON responses at 2 MiB, reject
  feedback screenshots above HQ's existing 5 MiB limit, and return stable,
  correlated failures without exposing network or upstream response details.
  The framework-neutral `HQClient` applies the same redirect and response-size
  boundaries for FastAPI consumers.
- Merged the previously separate FastAPI `v1.3.0` feature line into canonical
  `main`, preserving the optional adapter and Flask import compatibility.
- Added focused Flask and FastAPI regression coverage for token cleanup,
  CSRF/logout, redacted failures, invalid/oversize upstream responses,
  screenshot bounds, and package metadata.
- The package contract remains `1.0.0`; this is a compatible package release.

## [1.3.0] — 2026-07-16

- Added the opt-in `aj_shared.fastapi_integration.FastAPIHQ` adapter for
  standalone FastAPI/Starlette apps. The adapter provides signed local HQ
  sessions, default-deny browser authentication, `require_user`, hierarchical
  `require_role`, `current_user`, `has_tag`, `csrf_token`, and `require_csrf`.
- Added `install_standard_routes(app)`, covering the same HQ proxy and
  `/api/contract` route shapes as the Flask adapter. JSON endpoints return
  JSON 401/403 responses, cached user roles are forwarded to `/api/apps`,
  multipart uploads retain filename/content type, and upstream failures use
  generic bodies.
- Added the framework-neutral `HQClient` with a five-second default timeout,
  platform-key forwarding, typed response wrapper, and fail-closed validation.
- FastAPI support remains optional through `aj-shared[fastapi]`; importing the
  base package does not import or require FastAPI. Existing Flask imports,
  behavior, and the `1.0.0` route contract are unchanged.
- FastAPI sessions default to a 1,200-second TTL. Cookies are HttpOnly,
  SameSite=Lax, and Secure in production. Mutations accept the exact
  `X-Requested-With: XMLHttpRequest` header or a constant-time-checked signed
  `_csrf` form nonce.
- Estimate Engine is the first planned consumer. Adoption remains explicit by
  pinning this release; existing apps stay on their current version until
  intentionally upgraded.

## [1.2.1] — 2026-07-12

- **`AJ_FLEET_ORIGINS` gained `https://aj-budgets.up.railway.app`** (Budget
  Builder), confirmed by Christine directly. No other changes.

## [1.2.0] — 2026-07-11

Two additions to `register_proxy()`, both requested during Phase 3 retrofits
that had to hand-roll workarounds for gaps this package didn't cover yet.
These changes were tagged and published. The `v1.1.1` and `v1.2.0` tags both
resolve to the `v1.2.0` commit `1f9838e`; the historical `v1.1.1` commit is
`38df44d`. Do not rewrite either historical tag. Current consumers remain
on their recorded source reference until a separately approved consumer
change.

- **`exclude_routes=` parameter.** Pass an iterable of route rules (e.g.
  `exclude_routes=['/api/jobs', '/api/jobs/<job_number>']`) to skip
  registering those routes in the blueprint entirely, so the app's own
  business-logic route at that path is the only one that exists — no
  reliance on Werkzeug's first-registered-wins collision behavior. Budget
  Builder, Intelligence (BID), and Project Invoices currently work around
  this collision by defining their own route *before* calling
  `register_proxy()` (documented in `reference-phase3-quickref.md`) — that
  ordering trick still works and isn't being removed, but `exclude_routes=`
  is now the explicit, documented way going forward. Also respected by the
  automatic `/api/contract` registration, for an app that wants to hand-roll
  its own contract route.
- **`open_app=True` parameter.** For the fleet's intentionally-open apps
  (no login at all — currently just Tools). When set, every route that
  would normally require a valid HQ session is registered without that
  gate, and `/auth/validate` always returns `{'valid': False}` immediately
  rather than proxying to HQ. This is exactly the workaround Tools' Phase 3
  retrofit had to hand-roll (defining `/auth/validate` and `/api/feedback`
  itself, before `register_proxy()`, to win on route-registration order) —
  an open app can now pass `open_app=True` instead of rediscovering that
  same trick. `csrf_protect` still applies to mutating routes even in
  open-app mode (no reason to drop that protection just because there's no
  login).

Verified via a scratch venv + `app.test_client()`: `exclude_routes` keeps an
app's own same-path route live and leaves all other routes gated as normal;
`open_app` leaves routes locally ungated (confirmed by pointing at an
unreachable `hq_base` and observing a network-layer 502, not our own 401,
plus the stubbed `/auth/validate` response) while a default `register_proxy()`
call (no new params) is unchanged — no regression to any app already on this
package.

## [1.1.1] — 2026-07-11

- **`AJ_FLEET_ORIGINS` gained `https://aj-tools-staging.up.railway.app`**,
  confirmed by Christine during Tools' Phase 3 retrofit session. No other
  changes. Apps whose own staging URL is still missing from this list
  (Bookings, Project Portal, Project Invoices, at minimum) should get their
  entry added the same way — confirmed, never guessed — the next time
  someone has the actual URL in hand.

## [1.1.0] — 2026-07-10

Two fleet-wide fixes found during AbbVie Invoicing's Phase 2 adversarial
wave-review (`audit/abv-invoice-builder-wave-review.md`). Both affect every
app using `aj-shared`, not just AbbVie — **verify these are actually working
as expected during each app's own Phase 3 retrofit**, not just here.

- **`require_auth()` gained a `json=` parameter.** Every route in
  `aj_proxy.py`'s blueprint used the redirect-only behavior despite being
  pure JSON API endpoints called via `fetch()` from every app in the fleet —
  a session-expiry mid-use hit a 302 redirect to HQ's login HTML, which
  `fetch()` follows transparently (200 status), so `res.json()` throws
  instead of the app's own 401 interceptor ever getting a real 401 to react
  to. Fixed by switching every route in `aj_proxy.py` to
  `@require_auth(json=True)` (or `@require_auth(role=..., json=True)`) —
  these now return a clean `401` JSON body on an expired/missing session,
  which apps using `aj-utils.js`'s shared fetch wrapper already handle
  correctly (session-expired toast + redirect). **Backward compatible** —
  existing `@require_auth` / `@require_auth(role=...)` calls elsewhere keep
  the redirect behavior unless `json=True` is added explicitly. Any app with
  its *own* JSON-only routes (e.g. a local `/api/summary`) should add
  `json=True` there too — AbbVie's was fixed as part of this same finding.
- **`csrf_protect` was checking for a header nothing was actually
  sending.** Its own docstring has claimed since v1.0.0 that "frontend calls
  through aj-utils.js already send this header automatically on mutating
  fetches" — that was never true. Fixed in `aj-utils.js` itself (HQ static,
  not this package — see HQ's own deploy) to auto-attach
  `X-Requested-With: XMLHttpRequest` on every wrapped `fetch()` call using a
  mutating method (POST/PUT/PATCH/DELETE), so the claim in `csrf_protect`'s
  docstring is now actually true fleet-wide with zero per-app frontend
  changes needed. `csrf_protect` itself is unchanged in this package — this
  entry documents the fix on the other end of the contract it depends on.
  Also applied `@csrf_protect` to every mutating route in `aj_proxy.py`
  (`/api/users/me/password`, `/api/feedback`, `/api/dropbox/upload`,
  `/api/email/send`) — these were left undecorated since `csrf_protect`
  shipped in v1.0.0.

**Deploy-order dependency, read before rolling this out to any app:** the
`aj-utils.js` fix must reach production HQ *before or at the same time as*
any app starts enforcing its own CSRF check against the
`X-Requested-With` header (as AbbVie's own blueprints now do — see its
`routes/*.py`). If an app enforces the header check while production HQ is
still serving the old `aj-utils.js`, every mutating request from that app
breaks with a 403, because the old JS never sends the header. Confirm HQ's
static assets are live with this fix before flipping on backend enforcement
elsewhere.

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
