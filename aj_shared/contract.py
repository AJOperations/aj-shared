"""
contract.py — contract versioning for AJ internal tools.

CONTRACT_VERSION describes the shape of the standard proxy contract
(routes, request/response formats) this package's aj_proxy.py implements.
Bump on any breaking change to that contract shape — apps report this
version so HQ admin can see fleet drift at a glance without every app
needing a simultaneous deploy when the contract changes.

This is independent of aj-shared's own package version (see CHANGELOG.md /
setup.py), which can bump for non-contract reasons (bug fixes, new helpers).
"""

import os
import re
from collections.abc import Mapping
from typing import Optional

from flask import jsonify, request

# Bump on any breaking change to the proxy contract's routes or shapes.
CONTRACT_VERSION = '1.0.0'

_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_RUNTIME_ENVIRONMENTS = frozenset({
    "local",
    "development",
    "test",
    "testing",
    "preview",
    "staging",
    "production",
})


def get_aj_shared_version():
    """Read the installed aj-shared package version from its own metadata,
    so apps can't misreport it (matches WAVE-PLAN's Resolved decision:
    "version reported from the package itself so apps can't misreport")."""
    try:
        from importlib.metadata import version
        return version('aj-shared')
    except Exception:
        return 'unknown'


def get_runtime_identity(
    environ: Optional[Mapping[str, str]] = None,
):
    """Return validated build identity without reflecting arbitrary env values."""
    source = os.environ if environ is None else environ

    def commit(name):
        value = str(source.get(name, "")).strip().lower()
        return value if _COMMIT_PATTERN.fullmatch(value) else None

    environment = str(
        source.get("AJ_RUNTIME_ENVIRONMENT", "")
    ).strip().lower()
    if environment not in _RUNTIME_ENVIRONMENTS:
        environment = None

    identity = {
        "app_commit": commit("AJ_APP_COMMIT"),
        "shared_commit": commit("AJ_SHARED_COMMIT"),
        "environment": environment,
    }
    identity["all_fields_supplied"] = all(identity.values())
    identity["provenance"] = "externally_supplied_build_metadata"
    return identity


def register_contract_route(app, app_name):
    """
    Register GET /api/contract, gated by X-AJ-Key (same PLATFORM_SECRET
    mechanism already used fleet-wide). Returns:
        {app_name, contract_version, aj_shared_version, runtime_identity}

    Called automatically by aj_proxy.register_proxy() — apps don't call this
    directly under normal use.
    """

    @app.route('/api/contract')
    def _aj_contract():
        secret = os.environ.get('PLATFORM_SECRET', '')
        key = request.headers.get('X-AJ-Key', '')
        import hmac
        if not secret or not hmac.compare_digest(key, secret):
            return jsonify({'error': 'Unauthorized'}), 401
        return jsonify({
            'app_name': app_name,
            'contract_version': CONTRACT_VERSION,
            'aj_shared_version': get_aj_shared_version(),
            'runtime_identity': get_runtime_identity(),
        })
