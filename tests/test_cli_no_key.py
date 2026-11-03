import os
import subprocess
import sys


def test_exits_without_api_key(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("OPENROUTER_API_KEY", "MODEL")}
    run = subprocess.run(
        [sys.executable, "-m", "emporio.cli"],
        env=env,
        cwd=tmp_path,
        input="oi\n",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run.returncode != 0
    assert "OPENROUTER_API_KEY" in run.stderr
    assert ".env" in run.stderr
    assert "Traceback" not in run.stderr
    assert "Olá!" not in run.stdout
