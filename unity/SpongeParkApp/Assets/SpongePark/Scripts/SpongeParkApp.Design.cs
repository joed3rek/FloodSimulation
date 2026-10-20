// Flow and flooding (Analyse and Simulate tabs) and design (Design tab) of the workspace.
// Step 2 shows where water runs and collects on the existing ground (engine /flow), in 3D or as a plan,
// and runs the flood simulation once rainfall and infiltration are in the project.
// Step 3 places NbS by hand: draw on the ground (polygon: rain garden, ponds; line: bioswale; click:
// recharge well), select, move, change sizes, delete, undo and redo. Every change is sent to the engine
// (/design/design), which carves the elements into the ground and checks them; the view then shows the
// carved ground. Elements are stored in the project's "design" scenario.
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace SpongePark
{
    public partial class SpongeParkApp
    {
        const string DesignScenario = "design";
        static readonly string[] ToolTypes = { "rain_garden", "bioswale", "detention_pond", "retention_pond", "recharge_well" };
        static readonly Dictionary<string, string> ToolNames = new Dictionary<string, string>
        {
            ["rain_garden"] = "Rain garden", ["bioswale"] = "Bioswale", ["detention_pond"] = "Detention pond",
            ["retention_pond"] = "Retention pond", ["recharge_well"] = "Recharge well",
        };
        static readonly Dictionary<string, string> Prefix = new Dictionary<string, string>
        {
            ["rain_garden"] = "RG", ["bioswale"] = "SW", ["detention_pond"] = "DP", ["retention_pond"] = "RP", ["recharge_well"] = "RW",
        };
        static readonly Dictionary<string, string> FieldNames = new Dictionary<string, string>
        {
            ["max_ponding_depth_m"] = "Ponding depth (m)", ["soil_media_depth_m"] = "Soil media depth (m)",
            ["top_width_m"] = "Top width (m)", ["side_slope_h_v"] = "Side slope (H:V)", ["check_dam_spacing_m"] = "Check dam spacing (m)",
            ["outlet_diameter_m"] = "Outlet diameter (m)", ["permanent_pool_depth_m"] = "Permanent pool depth (m)",
            ["safety_bench_width_m"] = "Safety bench width (m)", ["well_diameter_m"] = "Well diameter (m)", ["well_depth_m"] = "Well depth (m)",
        };

        VisualElement hotspotList, propsBox, warnBox, budgetFill, budgetBar;
        Label flowText, floodText, drawHint, budgetLabel;
        JToken flowData, designTools, designResult;
        JObject designFc;
        string designFor;                     // project the design state belongs to
        string viewsFor;                      // project the site frame and views were loaded for
        string tool;                          // null = select
        string selectedId;
        readonly List<Vector2> drawPts = new List<Vector2>();
        readonly Stack<string> undoStack = new Stack<string>(), redoStack = new Stack<string>();
        float lastClick, budgetUsed, budgetLimit = 10;
        Vector2 lastClickXY;
        bool dragging;
        Vector2 dragFrom;
        int vertexDrag = -1;   // corner of the selected element being dragged

        // ------------------------------------------------------------ parts placed in the workspace
        /// The controls of the flow and design steps, placed by the workspace (Properties, Checks, Results, viewport).
        void BuildFlowAndDesignParts()
        {
            flowText = Text("Confirm the site model to see where water runs.", "muted");
            hotspotList = new VisualElement();
            hotspotList.AddToClassList("layer-list");
            floodText = Text("", "muted");
            drawHint = Text("", "vp-hint");
            budgetLabel = Text("", "muted");
            budgetBar = new VisualElement();
            budgetBar.AddToClassList("budget-bar");
            budgetFill = new VisualElement();
            budgetFill.AddToClassList("budget-fill");
            budgetBar.Add(budgetFill);
            warnBox = new VisualElement();
            propsBox = new VisualElement();
        }

        bool FloodReady => (bool?)info?["has_rainfall"] == true && ((bool?)info?["has_ground"] == true || (bool?)info?["has_soils"] == true);

        void SyncFlowAndDesign()
        {
            if (flowText == null) return;
            SyncGroundAndRain();
            bool rain = (bool?)info?["has_rainfall"] == true, soils = (bool?)info?["has_ground"] == true || (bool?)info?["has_soils"] == true;
            floodText.text = rain && soils
                ? $"Runs the {CurrentRp}-year storm over the existing ground: depths, flooded area and the water animation."
                : "First " + (rain ? "" : "use the design rainfall") + (!rain && !soils ? " and " : "") + (soils ? "" : "answer the ground questions") +
                  " (Site > Site setup). The flow lines and hotspots need neither.";
            drawHint.text = tool == null
                ? (selectedId != null
                    ? $"{selectedId} selected: drag {(Feature(selectedId)?["properties"]?["fit_points"] != null ? "a point to reshape the curve" : "a corner to change its shape")}, " +
                      "drag inside to move it, Delete to remove; Curve / Straight changes its lines; sizes in Properties."
                    : "")
                : DrawOf(tool) == "point" ? $"Click on the ground to place a {ToolNames[tool].ToLower()}."
                : DrawOf(tool) == "line" ? "Click along the swale's line; double-click or Enter to finish, Backspace removes the last point, Esc cancels."
                : "Click the corners on the ground; double-click or Enter to finish, Backspace removes the last corner, Esc cancels.";
            if (siteConfirmed && info != null && designFor != projectPath && !busy) StartCoroutine(LoadDesign());
        }

        bool FlowOn(string key) => !layerVisible.TryGetValue("flow:" + key, out var on) || on;

        void SetFlow(string key, bool on)
        {
            layerVisible["flow:" + key] = on;
            left.Flow.SetVisible(key, on);
            right.Flow.SetVisible(key, on);
        }

        // ------------------------------------------------------------ step 2: flow
        IEnumerator LoadFlow()
        {
            if (bundle || info == null || frame == null) yield break;
            JToken a = null;
            yield return api.Get(api.P("/flow"), x => a = x, 600);
            if (a == null) { flowText.text = "Could not work out the flow: " + api.LastError; yield break; }
            flowData = a;
            PlanFirst();
            left.Flow.Build(a, frame, layerVisible);
            right.Flow.Build(a, frame, layerVisible);
            var s = a["summary"];
            int exits = (int)s["exits"];
            flowText.text = $"Blue lines: where water runs (wider where more ground drains to it). " +
                            $"{(int)s["hotspots"]} place{((int)s["hotspots"] == 1 ? "" : "s")} where water collects (up to {(float)s["deepest_m"] * 100:0} cm deep, " +
                            $"{(float)s["ponding_volume_m3"]:0.#} m³ in all); water leaves the park at {exits} point{(exits == 1 ? "" : "s")} (red). From the ground alone: no rainfall needed.";
            hotspotList.Clear();
            foreach (var h in a["hotspots"].Take(8))
            {
                float x = (float)h["x"], y = (float)h["y"], z = (float)h["z"];
                var b = new Button(() => FocusOn(x, y, z, 30));
                b.AddToClassList("layer-row");
                var sw = new VisualElement { pickingMode = PickingMode.Ignore };
                sw.AddToClassList("layer-swatch");
                sw.style.backgroundColor = new Color(0.29f, 0.61f, 0.79f);
                b.Add(sw);
                var w = new VisualElement { pickingMode = PickingMode.Ignore };
                w.AddToClassList("layer-words");
                w.Add(Text($"{h["id"]} · ponding, {(float)h["max_depth_m"] * 100:0.#} cm deep", "layer-title"));
                w.Add(Text($"{(float)h["area_m2"]:0} m² · holds {(float)h["volume_m3"]:0.##} m³ · {(float)h["draining_area_m2"]:0} m² drains to it", "layer-source"));
                b.Add(w);
                b.tooltip = "Show it";
                hotspotList.Add(b);
            }
            foreach (var e in a["exits"].Take(4))
            {
                if (e["z"] == null || e["z"].Type == JTokenType.Null) continue;
                float x = (float)e["x"], y = (float)e["y"], z = (float)e["z"];
                var b = new Button(() => FocusOn(x, y, z, 30));
                b.AddToClassList("layer-row");
                var sw = new VisualElement { pickingMode = PickingMode.Ignore };
                sw.AddToClassList("layer-swatch");
                sw.style.backgroundColor = new Color(0.76f, 0.29f, 0.23f);
                b.Add(sw);
                var w = new VisualElement { pickingMode = PickingMode.Ignore };
                w.AddToClassList("layer-words");
                w.Add(Text($"{e["id"]} · water leaves the park", "layer-title"));
                w.Add(Text($"{(float)e["draining_area_m2"]:0} m² of the park drains here", "layer-source"));
                b.Add(w);
                hotspotList.Add(b);
            }
        }

        void FocusOn(float x, float y, float z, float distance)
        {
            if (frame == null) return;
            rigLeft.Target = frame.World(x, y, z);
            rigLeft.Distance = distance;
        }

        IEnumerator RunFlood()
        {
            var rp = CurrentRp;
            JToken r = null;
            yield return api.RunJob("POST", api.P($"/options/baseline/sim2d/{rp}"), null, x => r = x, s => status = "flood simulation: " + s);
            if (r == null) yield break;
            yield return LoadViews();
            status = $"Flood simulation of the {rp}-year storm ready ({r["model"] ?? "2D model"}). Press Play to watch it.";
        }

        // ------------------------------------------------------------ step 3: design state
        static string DrawOf(string type) => type == "recharge_well" ? "point" : type == "bioswale" ? "line" : "polygon";

        IEnumerator LoadDesign()
        {
            // the site frame comes with LoadViews: until then try again later (an opened project that is already
            // confirmed gets here before its site model has loaded)
            if (bundle || frame == null || viewsFor != projectPath) yield break;
            designFor = projectPath;
            JToken tools = null, cur = null;
            yield return api.Get(api.P("/design/tools"), x => tools = x);
            yield return api.Get(api.P($"/design/{DesignScenario}"), x => cur = x);
            if (tools == null || cur == null) { designFor = null; yield break; }
            designTools = tools;
            designFc = (JObject)cur["features"];
            designResult = cur;
            undoStack.Clear();
            redoStack.Clear();
            yield return ShowDesignGround();
            RefreshDesign();
        }

        /// The view shows the design scenario's ground (carved), with the survey layers and flow on it.
        IEnumerator ShowDesignGround()
        {
            right.Option = DesignScenario;
            sideBySide = false;
            showProposed = true;
            ApplyViewports();
            yield return right.Load(api, frame, CurrentRp, false);
            right.Survey.Build(surveyLayers, frame, layerVisible, left.Terrain.GroundAt, left.Terrain.InPark);
            right.Terrain.SetContours(!layerVisible.TryGetValue(ContoursLayer, out var con) || con);
            if (flowData != null) right.Flow.Build(flowData, frame, layerVisible);
        }

        float GroundZ(float x, float y)
        {
            float z = right.Terrain.Grid != null ? right.Terrain.GroundAt(x, y) : float.NaN;
            if (float.IsNaN(z) && left.Terrain.Grid != null) z = left.Terrain.GroundAt(x, y);
            return float.IsNaN(z) ? frame.ZRef : z;
        }

        void RefreshDesign()
        {
            right.Design.Build(designFc, frame, GroundZ, selectedId);
            if (designResult == null) return;
            var bud = designResult["budget"];
            float used = bud?["used_pct"] != null && bud["used_pct"].Type != JTokenType.Null ? (float)bud["used_pct"] : 0;
            float limit = bud?["limit_pct"] != null ? (float)bud["limit_pct"] : 10;
            float m2 = bud?["used_m2"] != null ? (float)bud["used_m2"] : 0;
            budgetLabel.text = $"Area used: {used:0.0} % of the park ({m2:0} m²); budget {limit:0.#} %";
            budgetFill.style.width = Length.Percent(Mathf.Clamp01(limit > 0 ? used / limit : 0) * 100);
            budgetFill.EnableInClassList("budget-fill--over", used > limit);
            budgetUsed = used;
            budgetLimit = limit;
            warnBox.Clear();
            foreach (var w in designResult["warnings"] ?? new JArray())
            {
                var l = Text("Check: " + (string)w["text"], "warn-item");
                warnBox.Add(l);
            }
            contentsDirty = true;   // the Design group of Contents lists the elements
            BuildProps();
        }

        void BuildProps()
        {
            propsBox.Clear();
            var f = Feature(selectedId);
            if (f == null || designTools == null) return;
            var p = (JObject)f["properties"];
            var type = (string)p["type"];
            var card = new VisualElement();
            card.Add(Text($"{selectedId} · {ToolNames[type].ToUpper()}", "eyebrow"));
            var pending = new Dictionary<string, float>();
            foreach (var kv in ((JObject)designTools[type]["defaults"]).Properties())
            {
                var key = kv.Name;
                float cur = p[key] != null && p[key].Type != JTokenType.Null ? (float)p[key] : (float)kv.Value;
                card.Add(TextInput(FieldNames.TryGetValue(key, out var lab) ? lab : key, cur.ToString("0.###"),
                    v => { if (float.TryParse(v, out var x)) pending[key] = x; }));
            }
            var range = designTools[type]["depth_range_m"];
            if (range != null && range.Type == JTokenType.Array)
                card.Add(Text($"Safe ponding depth {(float)range[0]:0.00}–{(float)range[1]:0.00} m (default limits).", "muted"));
            card.Add(Btn("Apply sizes", () =>
            {
                if (pending.Count == 0) return;
                var before = designFc.ToString();
                foreach (var kv in pending) p[kv.Key] = kv.Value;
                p["source"] = "designer";
                StartCoroutine(Run(SendDesign("resize", selectedId, before), "Carving"));
            }));
            propsBox.Add(card);
        }

        JObject Feature(string id) =>
            id == null || designFc == null ? null : designFc["features"].Children<JObject>().FirstOrDefault(f => (string)f["properties"]["id"] == id);

        void Select(string id, bool focus)
        {
            selectedId = id;
            RefreshDesign();
            if (focus && id != null)
            {
                var c = Centre(Feature(id));
                FocusOn(c.x, c.y, GroundZ(c.x, c.y), 25);
            }
        }

        // ------------------------------------------------------------ curve or straight (swales and outlines)
        // Curve: the clicked points are fit points and the element follows the smooth curve through them (like a
        // CAD spline); Straight: straight segments between them. Remembered between sessions.
        bool DrawCurve
        {
            get => PlayerPrefs.GetInt("spongepark.drawcurve", 1) == 1;
            set => PlayerPrefs.SetInt("spongepark.drawcurve", value ? 1 : 0);
        }

        /// The element's outline or line through pts: smooth (curve) or as placed (straight).
        static List<Vector2> ShapeThrough(List<Vector2> pts, bool closed, bool curve) =>
            curve && pts.Count >= 3 ? Spline.Through(pts, closed) : new List<Vector2>(pts);

        static JArray Coords(IEnumerable<Vector2> pts) => new JArray(pts.Select(p => new JArray(Round(p.x), Round(p.y))));

        /// Sets a line's or outline's geometry from its points; curve keeps the points as fit points.
        static void SetShape(JToken f, List<Vector2> pts, bool curve)
        {
            var g = (JObject)f["geometry"];
            var props = (JObject)f["properties"];
            bool closed = (string)g["type"] == "Polygon";
            curve &= pts.Count >= 3;
            var shape = ShapeThrough(pts, closed, curve);
            if (closed)
            {
                var ring = Coords(shape);
                ring.Add(new JArray(Round(shape[0].x), Round(shape[0].y)));
                var rings = new JArray();
                rings.Add(ring);   // new JArray(ring) would copy the ring's points instead of nesting it
                g["coordinates"] = rings;
            }
            else g["coordinates"] = Coords(shape);
            if (curve) props["fit_points"] = Coords(pts);
            else props.Remove("fit_points");
        }

        /// Curve or Straight pressed: the drawing mode, and the selected swale or outline changes to match.
        void SetCurve(bool curve)
        {
            DrawCurve = curve;
            var f = Feature(selectedId);
            if (tool != null || f == null || Corners(f) == null || (f["properties"]["fit_points"] != null) == curve) return;
            var before = designFc.ToString();
            SetShape(f, Corners(f), curve);
            f["properties"]["source"] = "designer";
            StartCoroutine(Run(SendDesign("reshape", selectedId, before), curve ? "Smoothing" : "Straightening"));
        }

        void SetTool(string t)
        {
            tool = t;
            drawPts.Clear();
            right.Design.Preview(null, null, Color.white);
            if (t != null) selectedId = null;
            RefreshDesign();
        }

        // ------------------------------------------------------------ step 3: changes (each one carves and checks)
        IEnumerator SendDesign(string action, string elementId, string before, bool history = true)
        {
            JToken r = null;
            yield return api.RunJob("PUT", api.P($"/design/{DesignScenario}"),
                new { features = designFc, action, element_id = elementId }, x => r = x, s => status = "carving: " + s);
            if (r == null)
            {
                designFc = JObject.Parse(before);   // the engine refused it: back to how it was
                RefreshDesign();
                yield break;
            }
            designResult = r;
            if (history) { undoStack.Push(before); redoStack.Clear(); }
            if (selectedId != null && Feature(selectedId) == null) selectedId = null;
            yield return ShowDesignGround();
            RefreshDesign();
            status = $"{ActionWord(action)} {elementId}".Trim() + ". Ground carved and checked; the storm replays on it.";
            StartCoroutine(AfterDesignChange());
        }

        static string ActionWord(string a) => a switch
        {
            "create" => "Placed", "move" => "Moved", "resize" => "Resized", "delete" => "Deleted", "reshape" => "Reshaped",
            "undo" => "Undone", "redo" => "Redone", _ => "Changed"
        };

        void Undo()
        {
            if (busy || undoStack.Count == 0) return;
            var cur = designFc.ToString();
            designFc = JObject.Parse(undoStack.Pop());
            redoStack.Push(cur);
            StartCoroutine(Run(SendDesign("undo", null, cur, false), "Undoing"));
        }

        void Redo()
        {
            if (busy || redoStack.Count == 0) return;
            var cur = designFc.ToString();
            designFc = JObject.Parse(redoStack.Pop());
            undoStack.Push(cur);
            StartCoroutine(Run(SendDesign("redo", null, cur, false), "Redoing"));
        }

        void DeleteSelected()
        {
            var f = Feature(selectedId);
            if (busy || f == null) return;
            var before = designFc.ToString();
            var id = selectedId;
            f.Remove();
            selectedId = null;
            StartCoroutine(Run(SendDesign("delete", id, before), "Deleting"));
        }

        string NextId(string type)
        {
            var used = new HashSet<string>(designFc["features"].Select(f => (string)f["properties"]["id"]));
            for (int i = 1; ; i++)
                if (!used.Contains(Prefix[type] + i)) return Prefix[type] + i;
        }

        void AddElement(string type, JObject geometry, JObject props = null)
        {
            var before = designFc.ToString();
            var id = NextId(type);
            props ??= new JObject();
            props["id"] = id;
            props["type"] = type;
            ((JArray)designFc["features"]).Add(new JObject
            {
                ["type"] = "Feature", ["geometry"] = geometry, ["properties"] = props,
            });
            selectedId = id;
            StartCoroutine(Run(SendDesign("create", id, before), "Carving " + ToolNames[type].ToLower()));
        }

        void FinishShape()
        {
            if (tool == null) return;
            var kind = DrawOf(tool);
            if ((kind == "polygon" && drawPts.Count >= 3) || (kind == "line" && drawPts.Count >= 2))
            {
                var f = new JObject
                {
                    ["geometry"] = new JObject { ["type"] = kind == "polygon" ? "Polygon" : "LineString" },
                    ["properties"] = new JObject(),
                };
                SetShape(f, drawPts, DrawCurve);
                AddElement(tool, (JObject)f["geometry"], (JObject)f["properties"]);
            }
            else return;
            drawPts.Clear();
            right.Design.Preview(null, null, Color.white);
        }

        static double Round(float v) => System.Math.Round(v, 3);

        /// Test hook (-spDraw type:x,y;x,y;...): draws a shape through the same path as clicking and finishing.
        IEnumerator DrawForTest(string spec)
        {
            var parts = spec.Split(':');
            SetTool(parts[0]);
            foreach (var p in parts[1].Split(';'))
            {
                var v = p.Split(',');
                drawPts.Add(new Vector2(float.Parse(v[0], System.Globalization.CultureInfo.InvariantCulture), float.Parse(v[1], System.Globalization.CultureInfo.InvariantCulture)));
            }
            if (DrawOf(parts[0]) == "point")
            {
                var q = drawPts[0];
                drawPts.Clear();
                AddElement(parts[0], new JObject { ["type"] = "Point", ["coordinates"] = new JArray(Round(q.x), Round(q.y)) });
            }
            else FinishShape();
            yield return null;
            float until = Time.realtimeSinceStartup + 120;
            while (busy && Time.realtimeSinceStartup < until) yield return null;
            if (busy) Debug.Log($"draw test: still busy after 2 minutes; status: {status}");
            SetTool(null);
            var centre = new Vector3(camLeft.pixelRect.center.x, camLeft.pixelRect.center.y, 0);
            Debug.Log(PickAt(centre, out var xy, out _) ? $"pick at screen centre: {xy.x:0.0}, {xy.y:0.0}" : "pick at screen centre: nothing");
            Debug.Log($"design elements: {string.Join(", ", designFc["features"].Select(f => (string)f["properties"]["id"]))}; warnings {designResult?["warnings"]?.Count()}");
        }

        // ------------------------------------------------------------ step 3: pointer and keys
        bool PickGround(out Vector2 xy, out Vector3 world) => PickAt(Input.mousePosition, out xy, out world);

        bool PickAt(Vector3 screen, out Vector2 xy, out Vector3 world)
        {
            xy = default;
            world = default;
            if (frame == null || !camLeft.pixelRect.Contains(screen)) return false;
            var ray = camLeft.ScreenPointToRay(screen);
            if (!Physics.Raycast(ray, out var hit, 20000f, camLeft.cullingMask)) return false;
            world = hit.point;
            xy = new Vector2(hit.point.x + frame.X0, hit.point.z + frame.Y0);
            return true;
        }

        Vector3 WorldOf(Vector2 xy) => frame.World(xy.x, xy.y, GroundZ(xy.x, xy.y));

        void DesignInput()
        {
            if (!siteConfirmed || designFc == null || busy || frame == null) return;
            if (CameraRig.BlockInput != null && CameraRig.BlockInput()) return;
            bool ctrl = Input.GetKey(KeyCode.LeftControl) || Input.GetKey(KeyCode.RightControl);
            if (ctrl && Input.GetKeyDown(KeyCode.Z)) { Undo(); return; }
            if (ctrl && Input.GetKeyDown(KeyCode.Y)) { Redo(); return; }
            bool onGround = PickGround(out var xy, out var world);

            if (tool != null)
            {
                var col = DesignOverlay.TypeColour(tool);
                if (Input.GetKeyDown(KeyCode.Escape)) { if (drawPts.Count > 0) drawPts.Clear(); else SetTool(null); }
                if (Input.GetKeyDown(KeyCode.Backspace) && drawPts.Count > 0) drawPts.RemoveAt(drawPts.Count - 1);
                if (Input.GetKeyDown(KeyCode.Return) || Input.GetKeyDown(KeyCode.KeypadEnter)) { FinishShape(); return; }
                if (onGround && Input.GetMouseButtonDown(0))
                {
                    if (DrawOf(tool) == "point")
                    {
                        AddElement(tool, new JObject { ["type"] = "Point", ["coordinates"] = new JArray(Round(xy.x), Round(xy.y)) });
                        return;
                    }
                    bool dbl = Time.unscaledTime - lastClick < 0.35f && (xy - lastClickXY).magnitude < 1.5f;
                    lastClick = Time.unscaledTime;
                    lastClickXY = xy;
                    if (dbl) { FinishShape(); return; }
                    drawPts.Add(xy);
                }
                // the shape so far with the pointer as the next point: smooth through the points (Curve) or straight
                bool closed = DrawOf(tool) == "polygon";
                var fits = new List<Vector2>(drawPts);
                if (onGround) fits.Add(xy);
                var shape = ShapeThrough(fits, closed, DrawCurve);
                if (closed && shape.Count >= 3) shape.Add(shape[0]);
                right.Design.Preview(drawPts.Select(WorldOf).ToList(), shape.Select(WorldOf).ToList(), col);
                if (onGround && drawPts.Count > 0)
                    status = closed ? $"{ToolNames[tool]}: {Area(shape):0.0} m²" : $"{ToolNames[tool]}: {PathLength(shape):0.0} m";
                return;
            }

            // select and move
            if (Input.GetKeyDown(KeyCode.Delete)) { DeleteSelected(); return; }
            if (onGround && Input.GetMouseButtonDown(0))
            {
                vertexDrag = NearCorner(Feature(selectedId), xy);
                if (vertexDrag >= 0) { dragFrom = xy; }
                else
                {
                    var hitId = HitElement(xy);
                    if (hitId != null && hitId == selectedId) { dragging = true; dragFrom = xy; }
                    else Select(hitId, false);
                }
            }
            if (vertexDrag >= 0 && onGround)
            {
                var sel = Feature(selectedId);
                var pts = Corners(sel);
                if (pts != null && vertexDrag < pts.Count)
                {
                    pts[vertexDrag] = xy;
                    bool closed = (string)sel["geometry"]["type"] == "Polygon";
                    var shape = ShapeThrough(pts, closed, sel["properties"]["fit_points"] != null);
                    if (closed && shape.Count >= 3) shape.Add(shape[0]);
                    right.Design.Preview(pts.Select(WorldOf).ToList(), shape.Select(WorldOf).ToList(), new Color(0.76f, 0.55f, 0.36f));
                    status = $"Reshaping {selectedId}: corner {vertexDrag + 1}";
                }
            }
            if (vertexDrag >= 0 && Input.GetMouseButtonUp(0))
            {
                var sel = Feature(selectedId);
                int k = vertexDrag;
                vertexDrag = -1;
                right.Design.Preview(null, null, Color.white);
                if (sel != null && onGround && (xy - dragFrom).magnitude > 0.2f)
                {
                    var before = designFc.ToString();
                    MoveCorner(sel, k, xy);
                    sel["properties"]["source"] = "designer";
                    StartCoroutine(Run(SendDesign("reshape", selectedId, before), "Reshaping"));
                }
                return;
            }
            if (dragging && onGround)
                status = $"Moving {selectedId} {(xy - dragFrom).magnitude:0.0} m";
            if (dragging && Input.GetMouseButtonUp(0))
            {
                dragging = false;
                var d = onGround ? xy - dragFrom : Vector2.zero;
                var f = Feature(selectedId);
                if (f != null && d.magnitude > 0.3f)
                {
                    var before = designFc.ToString();
                    Translate(f["geometry"]["coordinates"], d);
                    if (f["properties"]["fit_points"] != null) Translate(f["properties"]["fit_points"], d);
                    f["properties"]["source"] = "designer";
                    StartCoroutine(Run(SendDesign("move", selectedId, before), "Moving"));
                }
            }
        }

        /// The corners of a polygon (without the closing repeat) or the points of a line, or a curve's fit points;
        /// null for points.
        static List<Vector2> Corners(JToken f)
        {
            if (f == null) return null;
            if (f["properties"]?["fit_points"] is JArray fp && fp.Count >= 2)
                return fp.Select(q => new Vector2((float)q[0], (float)q[1])).ToList();
            var g = f["geometry"];
            var t = (string)g["type"];
            if (t == "Polygon")
            {
                var ring = g["coordinates"][0].Select(q => new Vector2((float)q[0], (float)q[1])).ToList();
                if (ring.Count > 1 && (ring[0] - ring[ring.Count - 1]).sqrMagnitude < 1e-6f) ring.RemoveAt(ring.Count - 1);
                return ring;
            }
            if (t == "LineString") return g["coordinates"].Select(q => new Vector2((float)q[0], (float)q[1])).ToList();
            return null;
        }

        static int NearCorner(JToken f, Vector2 p)
        {
            var pts = Corners(f);
            if (pts == null) return -1;
            int best = -1;
            float bd = 1.2f;   // metres
            for (int i = 0; i < pts.Count; i++)
            {
                float d = (pts[i] - p).magnitude;
                if (d < bd) { bd = d; best = i; }
            }
            return best;
        }

        static void MoveCorner(JToken f, int k, Vector2 p)
        {
            if (f["properties"]?["fit_points"] != null)   // a curve: move the fit point, the curve follows
            {
                var pts = Corners(f);
                pts[k] = p;
                SetShape(f, pts, true);
                return;
            }
            var g = f["geometry"];
            var pt = new JArray(Round(p.x), Round(p.y));
            if ((string)g["type"] == "Polygon")
            {
                var ring = (JArray)g["coordinates"][0];
                ring[k] = pt;
                if (k == 0) ring[ring.Count - 1] = new JArray(Round(p.x), Round(p.y));   // keep the ring closed
            }
            else ((JArray)g["coordinates"])[k] = pt;
        }

        /// Moves every [x, y] in coords (any nesting) by d.
        static void Translate(JToken coords, Vector2 d)
        {
            void Shift(JToken c)
            {
                if (c is JArray a && a.Count >= 2 && a[0].Type != JTokenType.Array)
                {
                    a[0] = Round((float)a[0] + d.x);
                    a[1] = Round((float)a[1] + d.y);
                }
                else if (c is JArray arr) foreach (var x in arr) Shift(x);
            }
            Shift(coords);
        }

        string HitElement(Vector2 p)
        {
            foreach (var f in designFc["features"].Reverse())
            {
                var g = f["geometry"];
                var t = (string)g["type"];
                if (t == "Point")
                {
                    var c = new Vector2((float)g["coordinates"][0], (float)g["coordinates"][1]);
                    if ((c - p).magnitude < 1.5f) return (string)f["properties"]["id"];
                }
                else if (t == "LineString")
                {
                    var pts = g["coordinates"].Select(q => new Vector2((float)q[0], (float)q[1])).ToList();
                    float w = f["properties"]["top_width_m"] != null && f["properties"]["top_width_m"].Type != JTokenType.Null ? (float)f["properties"]["top_width_m"] : 3f;
                    for (int i = 0; i + 1 < pts.Count; i++)
                        if (SegDist(p, pts[i], pts[i + 1]) < w / 2 + 0.5f) return (string)f["properties"]["id"];
                }
                else if (t == "Polygon")
                {
                    var ring = g["coordinates"][0].Select(q => new Vector2((float)q[0], (float)q[1])).ToList();
                    if (InRing(ring, p)) return (string)f["properties"]["id"];
                }
            }
            return null;
        }

        static Vector2 Centre(JToken f)
        {
            if (f == null) return Vector2.zero;
            var pts = new List<Vector2>();
            void Collect(JToken c)
            {
                if (c is JArray a && a.Count >= 2 && a[0].Type != JTokenType.Array) pts.Add(new Vector2((float)a[0], (float)a[1]));
                else if (c is JArray arr) foreach (var x in arr) Collect(x);
            }
            Collect(f["geometry"]["coordinates"]);
            return pts.Count == 0 ? Vector2.zero : pts.Aggregate(Vector2.zero, (s, q) => s + q) / pts.Count;
        }

        static float SegDist(Vector2 p, Vector2 a, Vector2 b)
        {
            var ab = b - a;
            float t = ab.sqrMagnitude < 1e-9f ? 0 : Mathf.Clamp01(Vector2.Dot(p - a, ab) / ab.sqrMagnitude);
            return (a + ab * t - p).magnitude;
        }

        static bool InRing(List<Vector2> r, Vector2 p)
        {
            bool inside = false;
            for (int i = 0, j = r.Count - 1; i < r.Count; j = i++)
                if ((r[i].y > p.y) != (r[j].y > p.y) && p.x < (r[j].x - r[i].x) * (p.y - r[i].y) / (r[j].y - r[i].y) + r[i].x)
                    inside = !inside;
            return inside;
        }

        static float PathLength(List<Vector2> pts)
        {
            float s = 0;
            for (int i = 0; i + 1 < pts.Count; i++) s += (pts[i + 1] - pts[i]).magnitude;
            return s;
        }

        static float Area(List<Vector2> pts)
        {
            float a = 0;
            for (int i = 0; i < pts.Count; i++) { var p = pts[i]; var q = pts[(i + 1) % pts.Count]; a += p.x * q.y - q.x * p.y; }
            return Mathf.Abs(a) / 2;
        }
    }
}
