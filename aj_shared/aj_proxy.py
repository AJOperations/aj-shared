"""
aj_proxy.py — HQ data proxy blueprint for AJ internal tools.

Registers the full standard HQ Data Proxy route set on a Flask app in one
call, replacing the copy-pasted proxy block previously hand-maintained in
each app. Apps configure origin/CORS and hit `/api/contract` for free.

Usage (once, in app.py):
    from aj_shared import register_proxy
    register_proxy(app, app_name='Invoice Tracker')

That's it — no more pasting individual @app.route proxy functions per app.
"""

import os
import json
import logging
import uuid

from flask import Blueprint, request, jsonify, session
from flask_cors import CORS

from .aj_auth import get_current_user, require_auth, csrf_protect
from .contract import register_contract_route

logger = logging.getLogger(__name__)

_HQ_BASE = os.environ.get('AJ_HQ_BASE', 'https://aj-hq.up.railway.app')
_HQ_TIMEOUT = 5
_HQ_UPLOAD_TIMEOUT = 15  # multipart forwarding (feedback screenshots, dropbox uploads) needs more headroom
_MAX_JSON_RESPONSE_BYTES = 2 * 1024 * 1024
_FEEDBACK_MAX_BYTES = 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# CORS (OWASP A02:2025 — Security Misconfiguration)
# ---------------------------------------------------------------------------
# A fixed allowlist of AJ's own app hostnames — never a wildcard, never a
# regex that matches an entire hosting provider's domain (which would let
# any other developer's throwaway Railway/Netlify project pass the origin
# check). Extend this list as new apps join the fleet; source of truth is
# HQ's own /api/apps roster, mirrored here as a static list rather than
# fetched at request time (avoids CORS breaking if HQ is briefly unreachable
# at boot).
AJ_FLEET_ORIGINS = [
    "https://aj-hq.up.railway.app",
    "https://aj-tools.up.railway.app",  # confirmed live by Christine 2026-07-10; repo renamed AJFilemaker -> AJTools
    "https://aj-tools-staging.up.railway.app",  # confirmed by Christine 2026-07-11
    "https://invoicebuilder.up.railway.app",
    "https://aj-abbvie-invoice-builder-staging.up.railway.app",
    "https://aj-invoicing.up.railway.app",  # Invoice Tracker, confirmed by Christine 2026-07-10
    "https://ajstaffingmodel.netlify.app",  # current live Staffing (Netlify) — not being touched, eventual Railway migration is separate/future
    "https://ajstaffingmodel-testing.up.railway.app",
    "https://ajbookings.up.railway.app",  # confirmed by Christine 2026-07-10
    "https://aj-shows.up.railway.app",    # confirmed by Christine 2026-07-10
    "https://aj-bid.up.railway.app",      # confirmed by Christine 2026-07-10
    "https://aj-budgets.up.railway.app",  # Budget Builder, confirmed by Christine 2026-07-12
    # Rooms doesn't need an entry — no auth, no backend, excluded from the
    # wave entirely (see audit/rooms.md).
    #
    # Bug fix (2026-07-10): this list was originally built partly from
    # inference rather than confirmed values — "aj-staffing.up.railway.app"
    # didn't exist at all, and the Invoice Tracker URL sourced from its own
    # audit's "historical Railway service slug" mention was also wrong.
    # Every entry above is now either the long-standing HQ URL or something
    # Christine confirmed directly. Add any future app's URL(s) — both
    # production and any active staging/testing subdomain — the same way:
    # confirmed, never guessed, never widened to a wildcard/provider-domain
    # regex.
]


def configure_cors(app, extra_origins=None):
    """
    Call once at app startup instead of a bare CORS(app) or a
    provider-domain regex. extra_origins lets an app add its own
    non-fleet origins (e.g. a local dev port) without widening the shared
    default list.
    """
    origins = list(AJ_FLEET_ORIGINS)
    if extra_origins:
        origins.extend(extra_origins)
    CORS(app, origins=origins, supports_credentials=True)


# ---------------------------------------------------------------------------
# Safe dynamic SQL helper (OWASP A05:2025 — Injection)
# ---------------------------------------------------------------------------

def build_set_clause(payload, allowed_columns):
    """
    Build a parameterized `col1=?, col2=?` SET clause from a request payload,
    restricted to an explicit allowlist of column names.

    Replaces the fleet-wide pattern of building `SET {", ".join(sets)}` via
    f-string from dict keys — safe only if the keys are pre-filtered against
    a fixed allowlist, which was easy to get wrong by hand across ~40+ call
    sites fleet-wide. This helper makes the allowlist mandatory, not optional.

        set_clause, values = build_set_clause(request.get_json(), ['name', 'email', 'role'])
        if not set_clause:
            return jsonify({'error': 'No valid fields to update'}), 400
        db.execute(f'UPDATE users SET {set_clause} WHERE id=?', values + [user_id])

    Returns (set_clause: str, values: list) — set_clause is '' and values is
    [] if no key in payload matches allowed_columns.
    """
    allowed = set(allowed_columns)
    keys = [k for k in payload.keys() if k in allowed]
    set_clause = ', '.join(f'{k}=?' for k in keys)
    values = [payload[k] for k in keys]
    return set_clause, values


# ---------------------------------------------------------------------------
# Proxy blueprint
# ---------------------------------------------------------------------------

def _proxy_failure(operation, *, exc=None, detail=None):
    """Return a stable public response and log only redacted diagnostics."""
    reference_id = uuid.uuid4().hex[:12]
    fields = {
        'operation': operation,
        'reference_id': reference_id,
    }
    if exc is not None:
        fields['exception_type'] = type(exc).__name__
    if detail is not None:
        fields['detail'] = detail
    logger.error(
        'proxy_failure %s',
        ' '.join(f'{key}={value}' for key, value in fields.items()),
    )
    return {
        'error': 'HQ is temporarily unavailable. It is safe to retry.',
        'reference_id': reference_id,
    }, 502


def _read_json_response(response, operation):
    """Read a bounded, non-redirect HQ response and decode JSON safely."""
    if 300 <= response.status_code < 400:
        response.close()
        return _proxy_failure(operation, detail='unexpected_redirect')

    declared_length = response.headers.get('Content-Length')
    if declared_length:
        try:
            if int(declared_length) > _MAX_JSON_RESPONSE_BYTES:
                response.close()
                return _proxy_failure(operation, detail='response_too_large')
        except (TypeError, ValueError):
            response.close()
            return _proxy_failure(operation, detail='invalid_content_length')

    body = bytearray()
    try:
        for chunk in response.iter_content(chunk_size=65536):
            if not chunk:
                continue
            body.extend(chunk)
            if len(body) > _MAX_JSON_RESPONSE_BYTES:
                return _proxy_failure(operation, detail='response_too_large')
    except Exception as exc:
        return _proxy_failure(operation, exc=exc)
    finally:
        response.close()

    if response.status_code == 204 and not body:
        return {}, 204
    try:
        return json.loads(body.decode('utf-8')), response.status_code
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _proxy_failure(operation, exc=exc)


def _request_json(method, url, operation, **kwargs):
    """Send one bounded HQ request with redirects disabled."""
    try:
        import requests as req
        response = req.request(
            method,
            url,
            allow_redirects=False,
            stream=True,
            **kwargs,
        )
        return _read_json_response(response, operation)
    except Exception as exc:
        return _proxy_failure(operation, exc=exc)


def _hq_get(path):
    secret = os.environ.get('PLATFORM_SECRET', '')
    return _request_json(
        'GET',
        f'{_HQ_BASE}{path}',
        f'hq_get:{path.split("?", 1)[0]}',
        headers={'X-AJ-Key': secret},
        timeout=_HQ_TIMEOUT,
    )


def register_proxy(app, app_name, hq_base=None, extra_origins=None, configure_cors_now=True,
                    exclude_routes=None, open_app=False):
    """
    Register the full HQ Data Proxy route set plus /api/contract on `app`.

    app_name: this app's display name, reported by /api/contract.
    hq_base: override HQ's base URL (defaults to AJ_HQ_BASE env var or the
        production HQ URL) — mainly for local dev against a staging HQ.
    configure_cors_now: set False if the app wants to call configure_cors()
        itself with custom extra_origins timing.
    exclude_routes: iterable of route rules (e.g. '/api/jobs',
        '/api/jobs/<job_number>') to skip entirely, so an app with its own
        business-logic route at that path can register it without relying on
        Werkzeug's first-registered-wins collision behavior. Replaces the
        "define your own route, then call register_proxy()" ordering trick
        used by Budget Builder, Intelligence/BID, and Project Invoices —
        that trick still works and isn't being removed, but this is the
        explicit, documented way going forward.
    open_app: set True for an app with no login at all (the fleet's
        intentionally-open apps, e.g. Tools). When True, every route that
        would normally require a valid HQ session is registered without that
        gate, and /auth/validate always returns {'valid': False} without a
        round-trip to HQ, instead of the standard proxy behavior. Mirrors the
        hand-rolled "define /auth/validate and /api/feedback before
        register_proxy() so they win on route precedence" workaround Tools'
        retrofit needed — an open app can now just pass open_app=True instead
        of rediscovering that trick.
    """
    global _HQ_BASE
    if hq_base:
        _HQ_BASE = hq_base

    if configure_cors_now:
        configure_cors(app, extra_origins=extra_origins)

    bp = Blueprint('aj_proxy', __name__)
    exclude_set = set(exclude_routes or [])

    def _route(rule, **options):
        if rule in exclude_set:
            def _skip(fn):
                return fn
            return _skip
        return bp.route(rule, **options)

    def _guard(role=None):
        # open_app apps have no session/login concept at all — every route
        # that would otherwise require a valid HQ session is left ungated.
        if open_app:
            def _noop(fn):
                return fn
            return _noop
        return require_auth(role=role, json=True)

    @_route('/api/apps')
    def proxy_apps():
        # Forward the already-validated local user's role so HQ's
        # min_visibility filtering (apps.min_role, migration v20) actually
        # has something to filter against — omitting this silently falls
        # back to HQ's least-privileged default, not an error, but every
        # retrofitted app should send it.
        user = get_current_user()
        role = (user or {}).get('role', 'staff')
        data, status = _hq_get(f'/api/apps?role={role}')
        return jsonify(data), status
    # Note: pass data through directly — aj-utils.js expects { apps: [...] }.
    # Do NOT unwrap with .get('apps', data).

    @_route('/api/apps/all')
    @_guard(role='admin')
    def proxy_apps_all():
        data, status = _hq_get('/api/apps/all')
        return jsonify(data), status

    @_route('/auth/validate')
    def proxy_auth_validate():
        if open_app:
            # No login exists for this app — always report "not logged in"
            # rather than proxying to HQ, so ajInitShell()/aj-utils.js render
            # an empty user zone instead of crashing or redirecting.
            return jsonify({'valid': False}), 200
        cached = session.get('_aj_user')
        if cached:
            return jsonify({'valid': True, 'user': cached}), 200
        secret = os.environ.get('PLATFORM_SECRET', '')
        token = request.args.get('token', '')
        data, status = _request_json(
            'GET',
            f'{_HQ_BASE}/auth/validate',
            'auth_validate',
            headers={'X-AJ-Key': secret},
            params={'token': token} if token else {},
            timeout=_HQ_TIMEOUT,
        )
        if status == 502:
            data = {
                'valid': False,
                'error': data['error'],
                'reference_id': data['reference_id'],
            }
        return jsonify(data), status

    @_route('/auth/logout', methods=['POST'])
    @csrf_protect
    def proxy_auth_logout():
        session.pop('_aj_user', None)
        session.pop('_aj_user_cached_at', None)
        return jsonify({'ok': True})

    @_route('/api/users')
    @_guard()
    def proxy_users():
        data, status = _hq_get('/api/users')
        return jsonify(data), status

    @_route('/api/rates')
    @_guard()
    def proxy_rates():
        client = request.args.get('client', '')
        path = f'/api/rates?client={client}' if client else '/api/rates'
        data, status = _hq_get(path)
        return jsonify(data), status

    @_route('/api/rates/lookup')
    @_guard()
    def proxy_rates_lookup():
        qs = request.query_string.decode()
        data, status = _hq_get(f'/api/rates/lookup?{qs}')
        return jsonify(data), status

    @_route('/api/people')
    @_guard()
    def proxy_people():
        item_type = request.args.get('item_type', '')
        path = f'/api/people?item_type={item_type}' if item_type else '/api/people'
        data, status = _hq_get(path)
        return jsonify(data), status

    @_route('/api/codes')
    @_guard()
    def proxy_codes():
        data, status = _hq_get('/api/codes')
        return jsonify(data), status

    @_route('/api/codes/fees')
    @_guard()
    def proxy_codes_fees():
        data, status = _hq_get('/api/codes/fees')
        return jsonify(data), status

    @_route('/api/codes/expenses')
    @_guard()
    def proxy_codes_expenses():
        data, status = _hq_get('/api/codes/expenses')
        return jsonify(data), status

    @_route('/api/jobs')
    @_guard()
    def proxy_jobs():
        qs = request.query_string.decode()
        path = f'/api/jobs?{qs}' if qs else '/api/jobs'
        data, status = _hq_get(path)
        return jsonify(data), status

    @_route('/api/jobs/<job_number>')
    @_guard()
    def proxy_jobs_single(job_number):
        data, status = _hq_get(f'/api/jobs/{job_number}')
        return jsonify(data), status

    @_route('/api/clients')
    @_guard()
    def proxy_clients():
        qs = request.query_string.decode()
        path = f'/api/clients?{qs}' if qs else '/api/clients'
        data, status = _hq_get(path)
        return jsonify(data), status

    @_route('/api/contracts')
    @_guard()
    def proxy_contracts():
        qs = request.query_string.decode()
        path = f'/api/contracts?{qs}' if qs else '/api/contracts'
        data, status = _hq_get(path)
        return jsonify(data), status

    @_route('/api/users/me/password', methods=['POST'])
    @_guard()
    @csrf_protect
    def proxy_user_change_password():
        secret = os.environ.get('PLATFORM_SECRET', '')
        data, status = _request_json(
            'POST',
            f'{_HQ_BASE}/api/users/me/password',
            'change_password',
            headers={
                'X-AJ-Key': secret,
                'Content-Type': 'application/json',
                'Cookie': f'aj_session={request.cookies.get("aj_session", "")}',
            },
            json=request.get_json(force=True, silent=True) or {},
            timeout=_HQ_TIMEOUT,
        )
        return jsonify(data), status

    @_route('/api/feedback', methods=['POST'])
    @_guard()
    @csrf_protect
    def proxy_feedback():
        """Forward a feedback widget submission (multipart, optional
        screenshot) to HQ. Session-gated (2026-07-09) — the feedback widget
        only ever renders for a logged-in user anyway, so this just stops
        the endpoint being spammable by an anonymous visitor."""
        secret = os.environ.get('PLATFORM_SECRET', '')
        files = None
        if 'screenshot' in request.files and request.files['screenshot'].filename:
            f = request.files['screenshot']
            original_position = f.stream.tell()
            f.stream.seek(0, os.SEEK_END)
            size = f.stream.tell()
            f.stream.seek(original_position)
            if size > _FEEDBACK_MAX_BYTES:
                return jsonify({'error': 'Screenshot must be 5 MB or smaller.'}), 413
            files = {'screenshot': (f.filename, f.stream, f.mimetype)}
        data, status = _request_json(
            'POST',
            f'{_HQ_BASE}/api/feedback',
            'feedback',
            headers={'X-AJ-Key': secret},
            data=request.form.to_dict(),
            files=files,
            timeout=_HQ_UPLOAD_TIMEOUT,
        )
        return jsonify(data), status

    @_route('/api/dropbox/list')
    @_guard()
    def proxy_dropbox_list():
        secret = os.environ.get('PLATFORM_SECRET', '')
        qs = request.query_string.decode()
        data, status = _request_json(
            'GET',
            f'{_HQ_BASE}/api/dropbox/list{"?" + qs if qs else ""}',
            'dropbox_list',
            headers={'X-AJ-Key': secret},
            timeout=_HQ_TIMEOUT,
        )
        return jsonify(data), status

    @_route('/api/dropbox/upload', methods=['POST'])
    @_guard()
    @csrf_protect
    def proxy_dropbox_upload():
        secret = os.environ.get('PLATFORM_SECRET', '')
        f = request.files.get('file')
        files = {'file': (f.filename, f.stream, f.mimetype)} if f else None
        data, status = _request_json(
            'POST',
            f'{_HQ_BASE}/api/dropbox/upload',
            'dropbox_upload',
            headers={'X-AJ-Key': secret},
            data=request.form.to_dict(),
            files=files,
            timeout=60,
        )
        return jsonify(data), status

    @_route('/api/email/send', methods=['POST'])
    @_guard()
    @csrf_protect
    def proxy_email_send():
        secret = os.environ.get('PLATFORM_SECRET', '')
        data, status = _request_json(
            'POST',
            f'{_HQ_BASE}/api/email/send',
            'email_send',
            headers={'X-AJ-Key': secret, 'Content-Type': 'application/json'},
            json=request.get_json(force=True, silent=True) or {},
            timeout=_HQ_TIMEOUT,
        )
        return jsonify(data), status

    app.register_blueprint(bp)

    # /api/contract — registered automatically, zero app code, per
    # WAVE-PLAN's Resolved decision (2026-07-09). Respect exclude_routes here
    # too, for an app that wants to hand-roll its own /api/contract.
    if '/api/contract' not in exclude_set:
        register_contract_route(app, app_name)
