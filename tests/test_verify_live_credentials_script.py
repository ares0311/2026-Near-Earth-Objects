"""Policy tests for the macOS Keychain credential bridge script."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path("Skills/verify_live_credentials.sh")


def test_credential_bridge_localizes_shell_options():
    """Sourced credential loading must not leak errexit into the operator shell."""
    text = SCRIPT.read_text(encoding="utf-8")

    assert "_neo_verify_live_credentials_main()" in text
    assert "emulate -L zsh" in text
    assert "set -euo pipefail" not in text


def test_credential_bridge_uses_uv_python_runtime():
    """The live connection check must use the project-managed Python runtime."""
    text = SCRIPT.read_text(encoding="utf-8")

    assert "PYTHONPATH=src uv run python Skills/_live_connection_test.py" in text
    assert "PYTHONPATH=src python Skills/_live_connection_test.py" not in text


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh not available on this platform")
def test_credential_bridge_does_not_kill_calling_zsh(tmp_path, monkeypatch):
    """Even a failed sourced live test must not exit the operator's shell."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "security").write_text("#!/bin/zsh\nprint fake-secret\n", encoding="utf-8")
    (fake_bin / "uv").write_text(
        "#!/bin/zsh\nprint '{\"ztf\":{\"status\":\"FAIL\"}}'\nexit 9\n",
        encoding="utf-8",
    )
    (fake_bin / "security").chmod(0o755)
    (fake_bin / "uv").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    probe = (
        "source Skills/verify_live_credentials.sh || print sourced_failed;"
        "false;"
        "print shell_survived"
    )
    result = subprocess.run(
        ["zsh", "-c", probe],
        check=False,
        capture_output=True,
        cwd=Path.cwd(),
        text=True,
    )

    assert result.returncode == 0
    assert "sourced_failed" in result.stdout
    assert "shell_survived" in result.stdout
