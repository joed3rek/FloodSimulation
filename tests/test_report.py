"""Phase 8: the full report is generated end to end from stored results."""

from spongepark.engine.layout.generate import generate
from spongepark.engine.pipeline import compare, run_option
from spongepark.engine.report.html import build_report
from spongepark.engine.sim2d.run import run2d

from .test_layout import _valley_project


def test_report_end_to_end(tmp_path):
    p, _ = _valley_project(tmp_path)
    with p:
        p.parameters.set("layout.types", ["detention_pond"])
        generate(p, "auto")
        run_option(p, "auto")
        compare(p, "auto")
        run2d(p, "auto", 5)
        r = build_report(p, None, tmp_path / "report", pdf=False)
    html = (tmp_path / "report" / "valley_report.html").read_text(encoding="utf-8")
    for must in ("Headline results", "Component schedule", "Earthworks", "Water balance (SWMM)",
                 "Parameters and their sources", "SWMM input files", "uncalibrated", "indicative", "DP_1"):
        assert must in html, must
    assert r["options"] == ["auto"] and r["swmm_files"]
    assert (tmp_path / "report" / r["swmm_files"][0]).exists()
    assert "data:image/png;base64," in html  # charts embedded: one self-contained file
