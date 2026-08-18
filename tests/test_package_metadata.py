import subprocess
import sys
from importlib.metadata import version


def test_package_version_is_1_5_0():
    assert version("aj-shared") == "1.5.0"


def test_base_package_import_does_not_import_fastapi():
    code = "import sys, aj_shared; assert 'fastapi' not in sys.modules"

    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_opt_in_fastapi_module_imports_when_extra_is_installed():
    from aj_shared.fastapi_integration import FastAPIHQ

    assert FastAPIHQ.__name__ == "FastAPIHQ"
