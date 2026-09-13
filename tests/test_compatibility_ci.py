from pathlib import Path

from scripts.compatibility_ci import CONTRACT_GROUPS


ROOT = Path(__file__).resolve().parents[1]


def test_compatibility_runner_covers_every_required_contract_group():
    assert set(CONTRACT_GROUPS) == {
        "flask", "fastapi", "open-app", "file-processing", "identity", "suite",
    }
    assert all(CONTRACT_GROUPS[group] for group in CONTRACT_GROUPS)


def test_workflow_runs_compatibility_and_full_package_suites():
    workflow = (ROOT / ".github/workflows/compatibility.yml").read_text()

    assert "pull_request:" in workflow
    assert "python scripts/compatibility_ci.py" in workflow
    assert "python -m pytest -q" in workflow
    assert '"3.9"' in workflow
    assert '"3.14"' in workflow
