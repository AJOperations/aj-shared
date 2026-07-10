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

from flask import Blueprint, request, jsonify, session
from flask_cors import CORS

from .aj_auth import get_current_user, require_auth, csrf_protect
from .contract import register_contract_route

logger = logging.getLogger(__name__)

_HQ_BASE = os.environ.get('AJ_HQ_BASE', 'https://aj-hq.up.railway.app')
_HQ_TIMEOUT = 5
_HQ_UPLOAD_TIMEOUT = 15  # multipart forwarding (feedback screenshots, dropbox uploads) needs more headroom


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
    "https://invoicebuilder.up.railway.app",
    "https://aj-abbvie-invoice-builder-staging.up.railway.app",
    "https://aj-invoicing.up.railway.app",  # Invoice Tracker, confirmed by Christine 2026-07-10
    "https://ajstaffingmodel.netlify.app",  # current live Staffing (Netlify) — not being touched, eventual Railway migration is separate/future
    "https://ajstaffingmodel-testing.up.railway.app",
    "https://ajbookings.up.railway.app",  # confirmed by Christine 2026-07-10
    "https://aj-shows.up.railway.app",    # confirmed by Christine 2026-07-10
    "https://aj-bid.up.railway.app",      # confirmed by Christine 2026-07-10
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

def _hq_get(path):
    secret = os.environ.get('PLATFORM_SECRET', '')
    try:
        import requests as req
        r = req.get(
            f'{_HQ_BASE}{path}',
            headers={'X-AJ-Key': secret},
            timeout=_HQ_TIMEOUT,
        )
        return r.json(), r.status_code
    except Exception as e:
        return {'error': str(e)}, 502


def register_proxy(app, app_name, hq_base=None, extra_origins=None, configure_cors_now=True):
    """
    Register the full HQ Data Proxy route set plus /api/contract on `app`.

    app_name: this app's display name, reported by /api/contract.
    hq_base: override HQ's base URL (defaults to AJ_HQ_BASE env var or the
        production HQ URL) — mainly for local dev against a staging HQ.
    configure_cors_now: set False if the app wants to call configure_cors()
        itself with custom extra_origins timing.
    """
    global _HQ_BASE
    if hq_base:
        _HQ_BASE = hq_base

    if configure_cors_now:
        configure_cors(app, extra_origins=extra_origins)

    bp = Blueprint('aj_proxy', __name__)

    @bp.route('/api/apps')
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

    @bp.route('/api/apps/all')
    @require_auth(role='admin', json=True)
    def proxy_apps_all():
        data, status = _hq_get('/api/apps/all')
        return jsonify(data), status

    @bp.route('/auth/validate')
    def proxy_auth_validate():
        cached = session.get('_aj_user')
        if cached:
            return jsonify({'valid': True, 'user': cached}), 200
        secret = os.environ.get('PLATFORM_SECRET', '')
        token = request.args.get('token', '')
        try:
            import requests as req
            r = req.get(
                f'{_HQ_BASE}/auth/validate',
                headers={'X-AJ-Key': secret},
                params={'token': token} if token else {},
                timeout=_HQ_TIMEOUT,
            )
            return jsonify(r.json()), r.status_code
        except Exception as e:
            return jsonify({'valid': False, 'error': str(e)}), 502

    @bp.route('/auth/logout', methods=['POST'])
    def proxy_auth_logout():
        session.pop('_aj_user', None)
        session.pop('_aj_user_cached_at', None)
        return jsonify({'ok': True})

    @bp.route('/api/users')
    @require_auth(json=True)
    def proxy_users():
        data, status = _hq_get('/api/users')
        return jsonify(data), status

    @bp.route('/api/rates')
    @require_auth(json=True)
    def proxy_rates():
        client = request.args.get('client', '')
        path = f'/api/rates?client={client}' if client else '/api/rates'
        data, status = _hq_get(path)
        return jsonify(data), status

    @bp.route('/api/rates/lookup')
    @require_auth(json=True)
    def proxy_rates_lookup():
        qs = request.query_string.decode()
        data, status = _hq_get(f'/api/rates/lookup?{qs}')
        return jsonify(data), status

    @bp.route('/api/people')
    @require_auth(json=True)
    def proxy_people():
        item_type = request.args.get('item_type', '')
        path = f'/api/people?item_type={item_type}' if item_type else '/api/people'
        data, status = _hq_get(path)
        return jsonify(data), status

    @bp.route('/api/codes')
    @require_auth(json=True)
    def proxy_codes():
        data, status = _hq_get('/api/codes')
        return jsonify(data), status

    @bp.route('/api/codes/fees')
    @require_auth(json=True)
    def proxy_codes_fees():
        data, status = _hq_get('/api/codes/fees')
        return jsonify(data), status

    @bp.route('/api/codes/expenses')
    @require_auth(json=True)
    def proxy_codes_expenses():
        data, status = _hq_get('/api/codes/expenses')
        return jsonify(data), status

    @bp.route('/api/jobs')
    @require_auth(json=True)
    def proxy_jobs():
        qs = request.query_string.decode()
        path = f'/api/jobs?{qs}' if qs else '/api/jobs'
        data, status = _hq_get(path)
        return jsonify(data), status

    @bp.route('/api/jobs/<job_number>')
    @require_auth(json=True)
    def proxy_jobs_single(job_number):
        data, status = _hq_get(f'/api/jobs/{job_number}')
        return jsonify(data), status

    @bp.route('/api/clients')
    @require_auth(json=True)
    def proxy_clients():
        qs = request.query_string.decode()
        path = f'/api/clients?{qs}' if qs else '/api/clients'
        data, status = _hq_get(path)
        return jsonify(data), status

    @bp.route('/api/contracts')
    @require_auth(json=True)
    def proxy_contracts():
        qs = request.query_string.decode()
        path = f'/api/contracts?{qs}' if qs else '/api/contracts'
        data, status = _hq_get(path)
        return jsonify(data), status

    @bp.route('/api/users/me/password', methods=['POST'])
    @require_auth(json=True)
    @csrf_protect
    def proxy_user_change_password():
        secret = os.environ.get('PLATFORM_SECRET', '')
        try:
            import requests as req
            r = req.post(
                f'{_HQ_BASE}/api/users/me/password',
                headers={
                    'X-AJ-Key': secret,
                    'Content-Type': 'application/json',
                    'Cookie': f'aj_session={request.cookies.get("aj_session", "")}',
                },
                json=request.get_json(force=True, silent=True) or {},
                timeout=_HQ_TIMEOUT,
            )
            return jsonify(r.json()), r.status_code
        except Exception as e:
            return jsonify({'error': str(e)}), 502

    @bp.route('/api/feedback', methods=['POST'])
    @require_auth(json=True)
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
            files = {'screenshot': (f.filename, f.stream, f.mimetype)}
        try:
            import requests as req
            r = req.post(
                f'{_HQ_BASE}/api/feedback',
                headers={'X-AJ-Key': secret},
                data=request.form.to_dict(),
                files=files,
                timeout=_HQ_UPLOAD_TIMEOUT,
            )
            return jsonify(r.json()), r.status_code
        except Exception as e:
            return jsonify({'error': str(e)}), 502

    @bp.route('/api/dropbox/list')
    @require_auth(json=True)
    def proxy_dropbox_list():
        secret = os.environ.get('PLATFORM_SECRET', '')
        qs = request.query_string.decode()
        try:
            import requests as req
            r = req.get(
                f'{_HQ_BASE}/api/dropbox/list{"?" + qs if qs else ""}',
                headers={'X-AJ-Key': secret},
                timeout=_HQ_TIMEOUT,
            )
            return jsonify(r.json()), r.status_code
        except Exception as e:
            return jsonify({'error': str(e)}), 502

    @bp.route('/api/dropbox/upload', methods=['POST'])
    @require_auth(json=True)
    @csrf_protect
    def proxy_dropbox_upload():
        secret = os.environ.get('PLATFORM_SECRET', '')
        f = request.files.get('file')
        files = {'file': (f.filename, f.stream, f.mimetype)} if f else None
        try:
            import requests as req
            r = req.post(
                f'{_HQ_BASE}/api/dropbox/upload',
                headers={'X-AJ-Key': secret},
                data=request.form.to_dict(),
                files=files,
                timeout=60,
            )
            return jsonify(r.json()), r.status_code
        except Exception as e:
            return jsonify({'error': str(e)}), 502

    @bp.route('/api/email/send', methods=['POST'])
    @require_auth(json=True)
    @csrf_protect
    def proxy_email_send():
        secret = os.environ.get('PLATFORM_SECRET', '')
        try:
            import requests as req
            r = req.post(
                f'{_HQ_BASE}/api/email/send',
                headers={'X-AJ-Key': secret, 'Content-Type': 'application/json'},
                json=request.get_json(force=True, silent=True) or {},
                timeout=_HQ_TIMEOUT,
            )
            return jsonify(r.json()), r.status_code
        except Exception as e:
            return jsonify({'error': str(e)}), 502

    app.register_blueprint(bp)

    # /api/contract — registered automatically, zero app code, per
    # WAVE-PLAN's Resolved decision (2026-07-09).
    register_contract_route(app, app_name)
