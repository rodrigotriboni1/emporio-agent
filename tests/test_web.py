import os
import subprocess
import sys


def test_web_app_builds_without_api_key(tmp_path):
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("OPENROUTER_API_KEY", "MODEL", "EMPORIO_NOW")
    }
    code = (
        "import emporio.web, starlette.applications as s; "
        "assert isinstance(emporio.web.app, s.Starlette)"
    )
    run = subprocess.run([sys.executable, "-c", code], env=env, cwd=tmp_path)
    assert run.returncode == 0
