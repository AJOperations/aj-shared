from pathlib import Path

from scripts.compatibility_ci import CONTRACT_GROUPS


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_GROUPS = {
    "flask",
    "fastapi",
    "open-app",
    "file-processing",
    "identity",
}


def test_compatibility_runner_covers_every_required_contract_group():
    assert set(CONTRACT_GROUPS) == EXPECTED_GROUPS
    assert all(CONTRACT_GROUPS[group] for group in EXPECTED_GROUPS)


def test_pull_request_workflow_runs_compatibility_and_full_package_suites():
    workflow = (ROOT / ".github/workflows/compatibility.yml").read_text()

    assert "pull_request:" in workflow
    assert "python scripts/compatibility_ci.py" in workflow
    assert "python -m pytest -q" in workflow
    assert '"3.9"' in workflow
    assert '"3.14"' in workflow


def test_compatibility_documentation_names_local_command_and_cost_boundary():
    documentation = (ROOT / "COMPATIBILITY.md").read_text()
    plain_text = " ".join(documentation.replace("**", "").split())

    assert "python scripts/compatibility_ci.py" in documentation
    assert "runner-minutes" in documentation
    assert "Unknown until the first hosted run" in plain_text
