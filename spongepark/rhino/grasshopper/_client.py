"""Shared helper pasted at the top of every Grasshopper component (Rhino 8, Python 3).

Rhino 8 runs CPython 3.9 and the engine needs 3.10+, so components do not import the engine: they
call the local engine API started with ``spongepark serve`` (http://127.0.0.1:8765). Only the
standard library is used, so no ``# r:`` package installs are needed inside Rhino.
"""

import json
import time
import urllib.request

API = "http://127.0.0.1:8765"


def call(method, path, body=None, timeout=3600):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def run_job(method, path, body=None, poll_s=1.0):
    """Start an engine job and wait for it (Grasshopper blocks while it runs)."""
    j = call(method, path, body)
    if "job" not in j:
        return j
    while True:
        s = call("GET", "/jobs/" + j["job"])
        if s["status"] == "done":
            return s["result"]
        if s["status"] == "error":
            raise RuntimeError(s["error"])
        time.sleep(poll_s)
