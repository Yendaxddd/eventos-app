"""The web client's own logic (QTE windows, where the floating buttons go, latency maths, settings) is plain JavaScript with
its tests in activity_client/test. They run with Node's built-in test runner; this runs them with the rest of the suite."""
import shutil
import subprocess
from pathlib import Path

import pytest

CLIENT = Path(__file__).resolve().parents[1] / "activity_client"


@pytest.mark.skipif(shutil.which("node") is None or not (CLIENT / "test").is_dir(), reason="Node.js is not installed")
def test_the_clients_logic_tests_pass():
    files = sorted(str(p) for p in (CLIENT / "test").glob("*.test.mjs"))
    assert files
    result = subprocess.run([shutil.which("node"), "--test", *files], cwd=CLIENT, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, (result.stdout + result.stderr)[-4000:]
