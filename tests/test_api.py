"""Phase 6/7: local engine API, and the Grasshopper component scripts run against a live server."""

import base64
import socket
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from spongepark.api.server import app
from spongepark.rhino.grasshopper.build import build

from .test_layout import _valley_project


@pytest.fixture(scope="module")
def project_path(tmp_path_factory):
    root = tmp_path_factory.mktemp("api")
    p, _ = _valley_project(root)
    p.parameters.set("layout.types", ["detention_pond"])
    path = root / "valley.sponge"
    p.save(path)
    p.close()
    return path


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_pipeline_through_the_api(client, project_path):
    pid = client.post("/projects/open", json={"path": str(project_path)}).json()["project"]
    assert client.get(f"/projects/{pid}").json()["has_baseline"]
    r = client.post(f"/projects/{pid}/options/auto/generate?wait=true", json={"run": True}).json()
    assert r["status"] == "done", r.get("error")
    assert r["result"]["comparison"]["rows"]
    s = client.get(f"/projects/{pid}/options/auto/summary").json()
    assert "uncalibrated" in s["calibration"]
    t = client.get(f"/projects/{pid}/terrain", params={"option": "auto"}).json()
    z = np.frombuffer(base64.b64decode(t["z"]), "<f4").reshape(t["rows"], t["cols"])
    assert np.isfinite(z).any() and t["z_max"] > t["z_min"]
    # background job + polling
    j = client.post(f"/projects/{pid}/options/auto/sim2d/5").json()
    for _ in range(600):
        st = client.get(f"/jobs/{j['job']}").json()
        if st["status"] != "running":
            break
        time.sleep(0.2)
    assert st["status"] == "done", st.get("error")
    fr = client.get(f"/projects/{pid}/options/auto/sim2d/5/frames", params={"count": 3}).json()
    assert fr["label"] == "indicative" and len(fr["times_s"]) == 3
    ts = client.get(f"/projects/{pid}/options/auto/timeseries/5").json()
    assert ts["columns"][0] == "time_hr" and ts["data"]
    q = client.put(f"/projects/{pid}/parameters/layout.max_area_pct", json={"value": 12, "unit": "%"}).json()
    assert q["source"] == "user" and q["confirmed"]
    # designer edit through the API: elements become designer elements, locked, regraded and rerun
    fc = client.get(f"/projects/{pid}/options/auto/components").json()
    r = client.put(f"/projects/{pid}/options/auto/components?wait=true", json=fc).json()
    assert r["status"] == "done", r.get("error")
    assert client.get(f"/projects/{pid}/options/auto/components").json()["features"][0]["properties"]["source"] == "designer"
    assert client.post(f"/projects/{pid}/close").json()["closed"] == pid


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_grasshopper_components_against_a_live_server(project_path, tmp_path):
    import uvicorn

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        comps = {p.stem: p.read_text(encoding="utf-8").replace("http://127.0.0.1:8765", f"http://127.0.0.1:{port}")
                 for p in build(tmp_path / "gh")}
        env = {"path": str(project_path), "create": False, "load": True}
        exec(comps["load_project"], env)
        pid = env["project"]
        assert "valley" in env["info"]
        env2 = {"project": pid, "area_budget_pct": 8.0, "design_rp": 5, "max_drawdown_hr": None,
                "target_rp_inverse": None, "apply": True}
        exec(comps["set_targets"], env2)
        assert any("layout.max_area_pct = 8.0" in d for d in env2["done"])
        env3 = {"project": pid, "option": "auto", "optimise": False, "mode": None, "run": True}
        exec(comps["generate_options"], env3)
        assert env3["options"] == ["auto"] and env3["report"]
        env4 = {"project": pid, "option": "auto", "run": True}
        exec(comps["run_swmm"], env4)
        assert any("retained" in row for row in env4["table"])
        env5 = {"project": pid, "option": "auto", "rp": 5, "t": 0.5}
        exec(comps["play_storm"], env5)
        assert env5["ids"] and all(0 <= f <= 1 for f in env5["fill"])
    finally:
        server.should_exit = True
        th.join(timeout=10)
