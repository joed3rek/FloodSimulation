"""Builds the GPU verification case for Unity: a valley site with a generated pond, its 2D engine run,
and the inputs payload the GPU port consumes.

    python -m tests.unity_case OUT_DIR

writes OUT_DIR/inputs.json and OUT_DIR/engine.json (balance and final depth of the engine run).
"""

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

from spongepark.engine.io.viewer import b64, sim2d_inputs_payload
from spongepark.engine.layout.generate import generate
from spongepark.engine.pipeline import run_option
from spongepark.engine.sim2d.run import run2d

from .test_layout import _valley_project


def build(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    p, _ = _valley_project(Path(tempfile.mkdtemp()))
    with p:
        p.parameters.set("layout.types", ["detention_pond"])
        generate(p, "auto")
        run_option(p, "auto")
        s = run2d(p, "auto", 5)
        (out / "inputs.json").write_text(json.dumps(sim2d_inputs_payload(p, "auto", 5)), encoding="utf-8")
        frames = np.load(p.path("scenarios/auto/sim2d/rp5.npz"))
        final = frames["depth_m"][-1].astype(np.float32)
        (out / "engine.json").write_text(json.dumps({"balance": s["balance"], "depth": b64(final)}), encoding="utf-8")


if __name__ == "__main__":
    build(Path(sys.argv[1]))
