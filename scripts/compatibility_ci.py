"""Run representative cross-framework contract groups for aj-shared."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence


CONTRACT_GROUPS: dict[str, tuple[str, ...]] = {
    "flask": (
        "tests/test_flask_compat.py",
        "tests/test_auth.py",
        "tests/test_proxy.py",
    ),
    "fastapi": (
        "tests/test_package_metadata.py",
        "tests/test_fastapi_auth.py",
        "tests/test_fastapi_csrf.py",
        "tests/test_fastapi_proxy.py",
    ),
    "open-app": (
        "tests/test_open_app_compat.py",
    ),
    "file-processing": (
        "tests/test_proxy.py",
        "tests/test_fastapi_proxy.py",
        "tests/test_hq_client.py",
    ),
    "identity": (
        "tests/test_auth.py",
        "tests/test_fastapi_auth.py",
    ),
}


def run_groups(groups: Sequence[str]) -> int:
    failures: list[str] = []
    for group in groups:
        print(f"\n== aj-shared compatibility: {group} ==", flush=True)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                *CONTRACT_GROUPS[group],
            ],
            check=False,
        )
        if result.returncode:
            failures.append(group)
    if failures:
        print(
            f"\nCompatibility groups failed: {', '.join(failures)}",
            file=sys.stderr,
        )
        return 1
    print(f"\nCompatibility groups passed: {', '.join(groups)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--group",
        action="append",
        choices=tuple(CONTRACT_GROUPS),
        help="Run only the named group; repeat for more than one",
    )
    args = parser.parse_args()
    groups = tuple(args.group or CONTRACT_GROUPS)
    return run_groups(groups)


if __name__ == "__main__":
    raise SystemExit(main())
