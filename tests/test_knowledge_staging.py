"""Staged rules carry their provenance and SI units, and the checker finds each snippet on its page."""

import json

import pytest

from spongepark.engine.knowledge import registry, staging, textstore


def _rule(**kw):
    base = dict(id="src.rg.x", source="src", file="doc.pdf", page=3, snippet="ponding depth of 150 to 300 mm",
                element="rain_garden", category="geometry", parameter="max_ponding_depth_m", unit="mm", min=150, max=300)
    return staging.StagedRule(**{**base, **kw})


def test_units_are_normalised_and_the_original_kept():
    r = _rule()
    assert (r.min, r.max, r.unit) == (150, 300, "mm") and (r.min_si, r.max_si, r.unit_si) == (0.15, 0.3, "m")
    assert _rule(unit="in/hr", min=0.5, max=None, parameter="infiltration_rate_mm_hr").min_si == pytest.approx(12.7)
    assert _rule(unit="ha", min=None, max=0.8, parameter="contributing_area_m2").max_si == 8000
    assert _rule(unit="ac", min=1, max=None).min_si == pytest.approx(4046.856, rel=1e-6)


def test_rules_need_provenance_and_known_terms():
    with pytest.raises(ValueError, match="snippet"):
        _rule(snippet="one")
    with pytest.raises(ValueError, match="snippet"):
        _rule(snippet=" ".join(["word"] * 15))
    with pytest.raises(ValueError, match="unit"):
        _rule(unit="furlong")
    with pytest.raises(ValueError, match="element"):
        _rule(element="moat")
    with pytest.raises(ValueError):
        _rule(min=None, max=None)   # no value, range or text
    assert _rule().status == "unreviewed"


def test_snippets_are_checked_on_their_page(tmp_path):
    raw = tmp_path / "raw" / "src"
    (raw / "index").mkdir(parents=True)
    pages = [{"file": "doc.pdf", "page": 3, "label": "3", "text": "Swales operate best with a ponding\n depth of 150 to 300 mm."},
             {"file": "doc.pdf", "page": 4, "label": "4", "text": "located 10m from a non-\npotable water supply well"}]
    (raw / "index" / "doc.pdf.jsonl").write_text("".join(json.dumps(p) + "\n" for p in pages), encoding="utf-8")
    assert textstore.contains("src", "doc.pdf", 3, "ponding depth of 150 to 300 mm", tmp_path)   # across a line break
    assert textstore.contains("src", "doc.pdf", 4, "10m from a non-potable water supply well", tmp_path)   # hyphen at line end
    assert not textstore.contains("src", "doc.pdf", 3, "ponding depth of 150 to 450 mm", tmp_path)
    staging.save("src", [_rule(), _rule(id="src.rg.y", page=3, snippet="depth of 150 to 450 mm")], tmp_path)
    probs = staging.check("src", tmp_path)
    assert len(probs) == 1 and "src.rg.y" in probs[0]


def test_committed_staging_files_are_valid():
    base = registry.root()
    ids = {s.id for s in registry.sources()}
    files = sorted((base / "staging").glob("*.jsonl"))
    assert files, "no staged rules committed"
    for f in files:
        rules = staging.load(f.stem, base)
        assert f.stem in ids and rules and all(r.source == f.stem and r.status == "unreviewed" for r in rules)
        assert len({r.id for r in rules}) == len(rules)
