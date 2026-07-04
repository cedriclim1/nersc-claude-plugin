import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None,
    reason="bash is required for the bootstrap harness",
)


def test_bootstrap_harness():
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["bash", "tests/test_bootstrap.sh"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert result.returncode == 0, result.stdout
