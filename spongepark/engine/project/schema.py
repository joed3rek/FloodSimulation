"""The ``.sponge`` file schema: one pydantic model per JSON file (brief section 7).

These models are the single source of the shared JSON Schema (``schema/sponge.schema.json``,
written by ``spongepark schema export``) and of the C# data classes the Unity app uses
(``SpongeSchema.g.cs``, generated from that schema). A test fails if the committed schema and these
models drift apart, so Python and Unity always read and write the same files.

Every model accepts and keeps fields it does not know (``extra="allow"``), so a file written by a
newer version survives a round trip through an older one.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from spongepark import __version__

SCHEMA_VERSION = "1.1"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SpongeModel(BaseModel):
    model_config = ConfigDict(extra="allow")


# ------------------------------------------------------------------ manifest.json
class Units(SpongeModel):
    length: str = "m"
    rainfall: str = "mm"
    time: str = "hr"
    flow: str = "m3/s"
    volume: str = "m3"


class Manifest(SpongeModel):
    """manifest.json: what the project is and which versions wrote it."""

    schema_version: str = SCHEMA_VERSION
    project_name: str
    city: str = "Bengaluru"
    crs: str = "EPSG:32643"  # UTM 43N; "LOCAL" allowed for local survey metres
    units: Units = Field(default_factory=Units)
    created: str = Field(default_factory=utcnow)
    modified: str = Field(default_factory=utcnow)
    engine_version: str = __version__
    app_version: Optional[str] = None  # the Unity app version that last saved the file
    calibration_status: str = "uncalibrated"


# ------------------------------------------------------------------ parameters.json
class ParameterRecord(SpongeModel):
    """One entry of parameters.json (keyed by parameter name)."""

    value: Any = None
    unit: str = "-"
    source: Literal["default", "site measured", "literature", "designer"] = "default"
    note: str = ""
    confirmed: bool = False


# ------------------------------------------------------------------ history.json, locks.json
class HistoryEntry(SpongeModel):
    time: str = Field(default_factory=utcnow)
    action: str
    detail: Dict[str, Any] = Field(default_factory=dict)
    engine_version: str = __version__


class History(SpongeModel):
    """history.json: run and change log."""

    entries: List[HistoryEntry] = Field(default_factory=list)

    def log(self, action: str, **detail: Any) -> None:
        self.entries.append(HistoryEntry(action=action, detail=detail))


class Locks(SpongeModel):
    """locks.json: element ids locked by the designer, per scenario (mirrors each element's ``locked``)."""

    locked: Dict[str, List[str]] = Field(default_factory=dict)
    note: Optional[str] = None


# ------------------------------------------------------------------ scenarios/<id>/elements.json
class Geometry(SpongeModel):
    """GeoJSON geometry in project metres: Point (well), LineString (spline: swale, edge), Polygon (basins)."""

    type: Literal["Point", "LineString", "Polygon", "MultiPolygon"]
    coordinates: Any


class Outlet(SpongeModel):
    type: Optional[Literal["orifice", "weir", "none"]] = None
    diameter_m: Optional[float] = None
    weir_length_m: Optional[float] = None
    coefficient: Optional[float] = None


class ElementParameters(SpongeModel):
    """Design parameters of an element (metres, mm/hr, H:V). Absent = taken from project parameters."""

    width_m: Optional[float] = None  # top width (swales, edges)
    depth_m: Optional[float] = None  # ponding / live storage depth
    side_slope_h_v: Optional[float] = None
    soil_media_depth_m: Optional[float] = None
    storage_layer_depth_m: Optional[float] = None
    permanent_pool_depth_m: Optional[float] = None
    safety_bench_width_m: Optional[float] = None
    freeboard_m: Optional[float] = None
    invert_elev_m: Optional[float] = None
    longitudinal_slope_pct: Optional[float] = None
    manning_n: Optional[float] = None
    vegetation_volume_fraction: Optional[float] = None
    check_dam_spacing_m: Optional[float] = None
    dam_height_m: Optional[float] = None
    diameter_m: Optional[float] = None  # recharge well
    well_depth_m: Optional[float] = None
    seepage_rate_mm_hr: Optional[float] = None
    overflow_weir_length_m: Optional[float] = None
    outlet: Optional[Outlet] = None


class Connections(SpongeModel):
    inflow_from: List[str] = Field(default_factory=list)  # subcatchments draining here
    outflow_to: Optional[str] = None
    overflow_to: Optional[str] = None


class ElementRecord(SpongeModel):
    """One NbS element (brief section 8.3)."""

    id: str
    type: str  # bioswale | rain_garden | detention_pond | retention_pond | recharge_well | ...
    geometry: Geometry
    parameters: ElementParameters = Field(default_factory=ElementParameters)
    infiltration_rate_mm_hr: Optional[float] = None
    area_m2: Optional[float] = None
    storage_volume_m3: Optional[float] = None
    contributing_area_m2: Optional[float] = None
    drawdown_time_hr: Optional[float] = None
    connections: Connections = Field(default_factory=Connections)
    locked: bool = False
    source: Literal["proposal", "designer"] = "proposal"
    soil_zone: Optional[str] = None
    param_sources: Dict[str, str] = Field(default_factory=dict)
    notes: str = ""
    results: Dict[str, Dict[str, Any]] = Field(default_factory=dict)  # return period -> verified metrics


class ElementsFile(SpongeModel):
    """scenarios/<id>/elements.json"""

    schema_version: str = SCHEMA_VERSION
    elements: List[ElementRecord] = Field(default_factory=list)


class Scenario(SpongeModel):
    """scenarios/<id>/scenario.json"""

    id: str
    name: str = ""
    created: str = Field(default_factory=utcnow)
    based_on: Optional[str] = None  # proposal id it started from, if any
    status: Literal["draft", "proposal", "accepted", "baseline"] = "draft"
    note: str = ""


# ------------------------------------------------------------------ terrain/edits.json
class TerrainEdit(SpongeModel):
    """A terrain shaping operation; the working terrain = existing ground + edits + NbS carving."""

    id: str
    kind: Literal["raise", "lower", "smooth", "flatten", "berm", "check_dam"]
    geometry: Geometry
    radius_m: Optional[float] = None
    strength_m: Optional[float] = None
    target_level_m: Optional[float] = None
    height_m: Optional[float] = None
    width_m: Optional[float] = None
    scenario: Optional[str] = None  # None = applies to every scenario
    created: str = Field(default_factory=utcnow)


class TerrainEdits(SpongeModel):
    schema_version: str = SCHEMA_VERSION
    edits: List[TerrainEdit] = Field(default_factory=list)


# ------------------------------------------------------------------ edit_log.json, proposals/
class EditLogEntry(SpongeModel):
    """A designer decision about a proposal (training data for learning from designers)."""

    time: str = Field(default_factory=utcnow)
    scenario: str
    action: Literal["accept", "accept_and_edit", "reject", "create", "edit", "move", "resize", "delete", "lock", "unlock"]
    element_id: Optional[str] = None
    proposal_id: Optional[str] = None
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None


class EditLog(SpongeModel):
    entries: List[EditLogEntry] = Field(default_factory=list)


class Proposal(SpongeModel):
    """proposals/<id>.json: an optimiser proposal kept for comparison (elements plus verified summary)."""

    id: str
    created: str = Field(default_factory=utcnow)
    mode: str = "forward"
    elements: List[ElementRecord] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    settings: Dict[str, Any] = Field(default_factory=dict)


# ------------------------------------------------------------------ site/survey_layers.json
class SurveyFeature(SpongeModel):
    """One drawn object on the ground: a line (x, y, z triples), a point (x, y, z), or a mesh (a surface)."""

    g: Literal["line", "point", "mesh"]
    xyz: List[float]
    tri: Optional[List[int]] = None  # mesh: vertex indices, three per triangle (a surface lying on the ground)
    width_m: Optional[float] = None  # gate: opening width
    angle_deg: Optional[float] = None  # gate: direction along the fence, degrees from east, anticlockwise
    color: Optional[str] = None  # this feature's colour where it differs from the layer's (kerbs, path edges)
    closed: Optional[bool] = None
    radius_m: Optional[float] = None  # tree canopy or symbol size
    on_ground: Optional[bool] = None  # draw flat on the ground although the layer is upright (e.g. a long "gate")
    block: Optional[str] = None


class SurveyLayer(SpongeModel):
    """A layer of the cleaned survey drawing (SP-* standard) as the 3D view draws it."""

    name: str
    title: str = ""
    source_layers: List[str] = Field(default_factory=list)  # the surveyor's layer names linked to it
    kind: str  # wall | fence | gate | building | tree | palm | path | road | drain | water | manhole | pole | ...
    color: str = "#9A9A90"
    visible: bool = True
    height_m: Optional[float] = None  # display height only
    width_m: Optional[float] = None  # display width of lines on the ground
    count: int = 0
    sized: Optional[int] = None  # trees with a canopy size from the drawing
    note: Optional[str] = None  # something about this layer the designer should check
    fenced: Optional[bool] = None  # boundary: drawn as fencing (no wall or fence along it in the drawing)
    features: List[SurveyFeature] = Field(default_factory=list)


class SurveyLayers(SpongeModel):
    """site/survey_layers.json: what the survey drawing shows, layer by layer, on the ground model."""

    schema_version: str = SCHEMA_VERSION
    drawing: str = ""
    extent: Optional[List[float]] = None  # x_min, y_min, x_max, y_max of what the drawing shows (m)
    note: str = ""
    layers: List[SurveyLayer] = Field(default_factory=list)


# the files and the model that describes each (used for the schema and for validation)
FILES: Dict[str, type] = {
    "manifest.json": Manifest,
    "parameters.json": ParameterRecord,  # a map of name -> ParameterRecord
    "history.json": History,
    "locks.json": Locks,
    "edit_log.json": EditLog,
    "terrain/edits.json": TerrainEdits,
    "scenarios/<id>/scenario.json": Scenario,
    "scenarios/<id>/elements.json": ElementsFile,
    "proposals/<id>.json": Proposal,
    "site/survey_layers.json": SurveyLayers,
}
