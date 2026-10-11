"""Runs the frontend's unit tests (display-name cleaner, deterministic hero pick, short-title and
direction helpers) through Node's built-in test runner, so `uv run pytest` covers them too."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_web_unit_tests_pass():
    out = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "--test",
            "--test-reporter=tap",
            "src/lib/__tests__/*.test.ts",
        ],
        cwd=ROOT / "web",
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert out.returncode == 0, out.stdout[-3000:] + out.stderr[-2000:]
    assert "# fail 0" in out.stdout
