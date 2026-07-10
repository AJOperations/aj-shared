"""
aj_auth.py — Shared auth module for AJ internal tools.

Validates sessions against HQ's centralized user store via the token_redirect
flow: HQ issues a short-lived cross-app token after login, the app validates
it once, then caches the user in Flask session locally for a bounded TTL.

Requires:
  - PLATFORM_SECRET env var (same value as HQ and every other AJ app)
  - The app registers aj_proxy's blueprint (provides /auth/validate) OR
    otherwise exposes an equivalent local proxy route.

Design constraint (hard rule): this module must never contain issuer-specific
code. Identity issuer details (Entra, ACE, or anything else) live in HQ
config only — this module just validates whatever HQ hands back.

Roles: 'admin' | 'leadership' | 'staff'
  role is the permission ceiling — controls access to admin UIs and
  destructive operations.

Tags: stackable, drive per-app feature access. Set in HQ admin UI, defined by
  HQ — this module doesn't hardcode a fleet-wide tag vocabulary.

Usage:
    from aj_shared import require_auth, get_current_user, has_tag

    @app.route('/page')
    @require_auth
    def page():
        user = get_current_user()  # { id, name, email, role, tags }

    @app.route('/admin-only')
    @require_auth(role='admin')
    def admin_only(): ...

    @app.route('/mutating-action', methods=['POST'])
    @require_auth
    @csrf_protect
    def mutate(): ...

App startup (once, in app.py):
    from aj_shared import configure_session_security, register_error_handlers
    configure_session_security(app)
    register_error_handlers(app)
"""

import os
import time
import logging
import functools
from urllib.parse import quote

from flask import request, redirect, g, session, abort, jsonify

logger = logging.getLogger(__name__)

_HQ_BASE = os.environ.get('AJ_HQ_BASE', 'https://aj-hq.up.railway.app')
_HQ_TIMEOUT = 5
_SESSION_KEY = '_aj_user'
_CACHED_AT_KEY = '_aj_user_cached_at'

# How long a cached session is trusted before re-checking with HQ. See
# _get_or_validate_user() docstring for why a TTL exists instead of trying to
# detect sign-out directly.
_SESSION_TTL_SECONDS = 20 * 60  # 20 minutes

# Role hierarchy — higher index = more permissive.
_ROLE_LEVELS = {'staff': 0, 'leadership': 1, 'admin': 2}

# Methods that mutate state — csrf_protect() and the standard error handler's
# input-validation guidance apply to these.
_MUTATING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


# ---------------------------------------------------------------------------
# Secrets & configuration (OWASP A04:2025 — Cryptographic Failures)
# ---------------------------------------------------------------------------
# Same fail-loud-in-production pattern already proven out independently in
# HQ's and Bookings' app.py — centralized here so every app gets it for free
# instead of hand-rolling it per repo. Never silently fall back to a known
# string in production; only ever fall back for local dev.

def require_env_secret(name, dev_default=None):
    """
    Read a required secret from the environment. Raises at call time (i.e.
    at app import/startup) if unset in production. Only ever returns a
    fallback value when FLASK_ENV is explicitly non-production — mirrors the
    pattern already in HQ's and Bookings' app.py.

    Usage (once, near the top of app.py, before app.secret_key is set):
        from aj_shared import require_env_secret
        app.secret_key = require_env_secret('FLASK_SECRET_KEY')
        PLATFORM_SECRET = require_env_secret('PLATFORM_SECRET')
    """
    is_prod = os.environ.get('FLASK_ENV', 'production') == 'production'
    value = os.environ.get(name)
    if value:
        return value
    if is_prod:
        raise RuntimeError(
            f"{name} is not set — refusing to start in production. "
            f"Set it in Railway env vars (same value as HQ and every other AJ app)."
        )
    if dev_default is None:
        dev_default = 'dev-secret-change-in-prod'
    logger.warning(f"{name} not set — using insecure dev default (FLASK_ENV != production)")
    return dev_default


def _platform_secret():
    # Read fresh each call rather than caching at import time — keeps this
    # safe to import before env vars are guaranteed to be loaded (e.g. under
    # certain test runners), and matches the existing per-app pattern.
    return os.environ.get('PLATFORM_SECRET', '')


# ---------------------------------------------------------------------------
# Session security (OWASP A01/A07:2025 — Broken Access Control / Auth Failures)
# ---------------------------------------------------------------------------

def configure_session_security(app):
    """
    Set explicit session cookie flags, and correct Flask's view of the
    request scheme behind Railway's reverse proxy. Call once at app startup,
    after app.secret_key is set.

    Don't rely on framework defaults for something this load-bearing — see
    reference-app-standards's Security Standards section.

    Bug fix (2026-07-10): this previously used app.config.setdefault(), which
    is a no-op here — Flask pre-populates SESSION_COOKIE_HTTPONLY/SAMESITE/
    SECURE in app.config at Flask() construction time (to True/None/False
    respectively), so setdefault() never actually overrode them. Direct
    assignment is required to actually apply these.

    Also wraps app.wsgi_app in ProxyFix (2026-07-10, same fix). Railway
    terminates TLS at its edge and forwards to the container over plain
    HTTP — without ProxyFix, Flask has no way to know the original request
    was HTTPS (wsgi.url_scheme reflects the internal hop, not what the
    browser used). request.url built from that wrong scheme is exactly what
    require_auth() uses as the `next` redirect target sent to HQ, so a
    scheme mismatch here can corrupt that whole redirect round-trip, not
    just cookie flags.
    """
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = not app.debug


# ---------------------------------------------------------------------------
# Standard error handling (OWASP A02/A10:2025 — Security Misconfiguration /
# Mishandling of Exceptional Conditions)
# ---------------------------------------------------------------------------

def register_error_handlers(app):
    """
    Install standard error handlers: log detail server-side, return a
    generic JSON error to the client with no stack trace. Call once at app
    startup.

    Apps that need a custom 404/500 page for browser-facing routes can still
    register their own handler after this call — Flask uses the most
    specific handler registered.
    """

    @app.errorhandler(400)
    def _aj_bad_request(e):
        return jsonify({'error': 'Bad request'}), 400

    @app.errorhandler(401)
    def _aj_unauthorized(e):
        return jsonify({'error': 'Unauthorized'}), 401

    @app.errorhandler(403)
    def _aj_forbidden(e):
        return jsonify({'error': 'Forbidden'}), 403

    @app.errorhandler(404)
    def _aj_not_found(e):
        return jsonify({'error': 'Not found'}), 404

    @app.errorhandler(500)
    def _aj_server_error(e):
        logger.exception('Unhandled exception')
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# CSRF (OWASP A01:2025 — Broken Access Control, CWE-352)
# ---------------------------------------------------------------------------

def csrf_protect(fn):
    """
    Lightweight CSRF mitigation: require a custom header on mutating
    requests. A plain HTML form (the classic CSRF vector) cannot set a
    custom header, so this defeats simple cross-site form submission;
    combined with SESSION_COOKIE_SAMESITE='Lax' (set by
    configure_session_security), this covers the common case without
    requiring a token-issuance/rotation system.

    Frontend calls through aj-utils.js already send this header
    automatically on mutating fetches — no per-call change needed in apps
    already using the shared JS.

    Apply to individual mutating routes:
        @app.route('/api/thing', methods=['POST'])
        @require_auth
        @csrf_protect
        def create_thing(): ...
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if request.method in _MUTATING_METHODS:
            if not request.headers.get('X-Requested-With'):
                abort(403)
        return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Rate limiting (OWASP A07:2025 — Authentication Failures)
# ---------------------------------------------------------------------------
# In-memory sliding-window limiter. Safe under the fleet's --workers 1 hard
# rule (single process, no cross-worker state to reconcile). Intended for
# auth-adjacent endpoints (HQ's /auth/token, /login) — not a general-purpose
# API rate limiter.

class _RateLimiter:
    def __init__(self):
        self._hits = {}  # key -> list[timestamp]

    def check(self, key, max_calls, per_seconds):
        now = time.time()
        hits = [t for t in self._hits.get(key, []) if now - t < per_seconds]
        if len(hits) >= max_calls:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True


_rate_limiter = _RateLimiter()


def rate_limited(max_calls, per_seconds, key_func=None):
    """
    Decorator: rate-limit a route by remote address (default) or a custom
    key function. Returns 429 when the limit is exceeded.

        @app.route('/auth/token')
        @rate_limited(max_calls=10, per_seconds=60)
        def auth_token(): ...
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = key_func() if key_func else (request.remote_addr or 'unknown')
            if not _rate_limiter.check(f'{fn.__name__}:{key}', max_calls, per_seconds):
                return jsonify({'error': 'Too many requests'}), 429
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Auth — validate against HQ, cache locally with a TTL
# ---------------------------------------------------------------------------

def _validate_with_hq(token=None):
    """
    Call HQ /auth/validate server-side. Passes ?token= if provided (cross-app
    token from URL). Returns user dict or None.
    """
    secret = _platform_secret()
    try:
        import requests as req
        params = {'token': token} if token else {}
        r = req.get(
            f'{_HQ_BASE}/auth/validate',
            headers={'X-AJ-Key': secret},
            params=params,
            timeout=_HQ_TIMEOUT,
        )
        if r.status_code == 200:
            data = r.json()
            return data.get('user') if data.get('valid') else None
    except Exception:
        pass
    return None


def _get_or_validate_user():
    """
    Get the current user, using a two-tier approach:
    1. Local Flask session cache, trusted for _SESSION_TTL_SECONDS (fast — no
       HQ round-trip).
    2. Cross-app token in ?token= query param (first visit from HQ login, or
       the first request after the cache has expired).

    Caches validated user in Flask session so subsequent requests are fast.
    Result also cached on g for the duration of the request.

    Why a TTL instead of detecting sign-out directly: HQ's session cookie is
    scoped to HQ's own domain and never travels to this app's domain —
    different Railway/Netlify subdomain, different cookie origin — so there
    is no live signal here that says "the user just signed out of HQ."
    Instead, the cached session expires on a short clock; once it does, the
    next protected route bounces the browser to HQ's login, which is
    invisible if the person is still logged into HQ (HQ redirects straight
    back with a fresh token) or a real login screen if they signed out. This
    bounds how long a stale local session can outlive an actual HQ sign-out
    to _SESSION_TTL_SECONDS, instead of the full app session lifetime.
    """
    if hasattr(g, '_aj_user'):
        return g._aj_user

    cached = session.get(_SESSION_KEY)
    cached_at = session.get(_CACHED_AT_KEY)
    if cached and cached_at is not None:
        try:
            age = time.time() - float(cached_at)
        except (TypeError, ValueError):
            age = _SESSION_TTL_SECONDS + 1  # corrupt timestamp — treat as expired
        if age < _SESSION_TTL_SECONDS:
            g._aj_user = cached
            return g._aj_user
        session.pop(_SESSION_KEY, None)
        session.pop(_CACHED_AT_KEY, None)

    xapp_token = request.args.get('token')
    if xapp_token:
        user = _validate_with_hq(token=xapp_token)
        if user:
            session[_SESSION_KEY] = user
            session[_CACHED_AT_KEY] = time.time()
            session.permanent = True
            g._aj_user = user
            return g._aj_user

    g._aj_user = None
    return None


def get_current_user():
    """Return the current user dict or None. Safe to call from any route."""
    return _get_or_validate_user()


def has_tag(tag):
    """
    Return True if the current user has the given functional tag. Tags are
    stackable and travel with the user dict from /auth/validate — this
    module doesn't hardcode a tag vocabulary, HQ owns that.
    """
    import json
    user = _get_or_validate_user()
    if not user:
        return False
    raw = user.get('tags') or '[]'
    try:
        tags = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except (ValueError, TypeError):
        tags = []
    return tag in tags


def require_auth(fn=None, *, role=None, json=False):
    """
    Decorator that requires a valid HQ session.

    @require_auth
    def my_view(): ...

    @require_auth(role='admin')
    def admin_view(): ...

    @require_auth(role='leadership')
    def leadership_view(): ...  # passes for admin + leadership too

    @require_auth(json=True)
    def my_api_route(): ...  # see `json` below

    Unauthenticated → redirects to HQ login with ?next= current URL, unless
    json=True (see below). Wrong role → 403. Sets g.user for use in the route.

    json: use on any route that's only ever called via fetch()/XHR — i.e. a
        JSON API endpoint, never a full browser navigation. A redirect there
        gets transparently followed by fetch(), landing on HQ's login HTML
        with a 200 status: res.json() then throws, producing a misleading
        parse error or silent fallback instead of a clean re-auth signal.
        With json=True, an expired/missing session gets a real 401 JSON
        response instead — apps using aj-utils.js's shared fetch wrapper
        already have a global 401 interceptor that reacts to this correctly
        (session-expired toast + redirect to login). Page routes reached by
        full browser navigation should keep the default (redirect) so an
        expired session sends the user to a real login screen.

        Bug fix (2026-07-10): found during AbbVie's Phase 2 wave-review —
        every route in aj_proxy.py's blueprint used the redirect-only
        behavior despite being pure JSON API endpoints called via fetch()
        from every app in the fleet, reproducing exactly the failure mode
        this module's own usage docstring warns against. Fixed by switching
        aj_proxy.py's routes to json=True (see aj_proxy.py) — apps' own
        JSON-only routes (e.g. a local /api/summary) should do the same.
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            user = _get_or_validate_user()
            if not user:
                if json:
                    return jsonify({'error': 'Unauthorized'}), 401
                login_url = f'{_HQ_BASE}/login'
                next_url = request.url.split('?')[0] if request.args.get('token') else request.url
                return redirect(f'{login_url}?next={quote(next_url, safe="")}')
            if role:
                required_level = _ROLE_LEVELS.get(role, 0)
                user_level = _ROLE_LEVELS.get(user.get('role', 'staff'), 0)
                if user_level < required_level:
                    abort(403)
            g.user = user
            return f(*args, **kwargs)
        return wrapper

    if fn is not None:
        return decorator(fn)
    return decorator


# ---------------------------------------------------------------------------
# Default-deny gating (OWASP A01:2025 — Broken Access Control)
# ---------------------------------------------------------------------------
# Routes that stay public no matter which app calls this — the shared proxy's
# own intentionally-open endpoints (see aj_proxy.py's register_proxy(): every
# other proxy route already requires @require_auth; these are the exceptions,
# baked in here so an app adopting require_auth_by_default() doesn't have to
# remember to re-list them).
_AJ_ALWAYS_PUBLIC_PATHS = ('/api/apps', '/auth/validate', '/auth/logout', '/api/contract', '/static/')


def require_auth_by_default(app, public_paths=None):
    """
    Install a before_request hook that requires a valid HQ session on every
    route except an explicit public allowlist. Flips the model from "opt in
    to protection" (decorate each route with @require_auth) to "opt out to
    public" — a route a developer forgets to decorate fails safe (redirects
    to login) instead of failing open (silently public).

    public_paths: path prefixes that should stay public on THIS app — e.g.
    an unguessable-token public booking or submission surface for people
    outside the AJ ecosystem (freelancers, clients). Matched via
    str.startswith(), so '/book/' covers everything under it.

        require_auth_by_default(app, public_paths=['/book/', '/event/'])
        require_auth_by_default(app, public_paths=['/s/'])

    Call once at app startup, after register_proxy() if used. Routes still
    needing a specific role beyond "logged in at all" (e.g. admin-only pages)
    keep their own @require_auth(role=...) — this hook only enforces "is
    there a valid session," not role.

    This does not retroactively change apps still using the per-route
    @require_auth decorator only — adopting this is an explicit choice per
    app, not automatic just from installing aj-shared.
    """
    allow = tuple(public_paths or ()) + _AJ_ALWAYS_PUBLIC_PATHS

    @app.before_request
    def _aj_default_deny():
        path = request.path
        if any(path.startswith(p) for p in allow):
            return None
        user = _get_or_validate_user()
        if not user:
            login_url = f'{_HQ_BASE}/login'
            next_url = request.url.split('?')[0] if request.args.get('token') else request.url
            return redirect(f'{login_url}?next={quote(next_url, safe="")}')
        g.user = user
        return None
