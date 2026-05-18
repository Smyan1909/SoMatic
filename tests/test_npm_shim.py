from __future__ import annotations

import json
import shutil
import subprocess


def test_node_shim_invokes_python_core():
    if shutil.which("node") is None:
        return
    completed = subprocess.run(["node", "bin/somatic.js", "wait", "0"], text=True, capture_output=True, check=True)
    payload = json.loads(completed.stdout)

    assert payload["ok"] is True
    assert payload["command"] == "wait"
