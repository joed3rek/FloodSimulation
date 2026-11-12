// Where water goes on the existing ground (engine /flow): main flow lines (wider where more ground drains
// to them), downhill arrows, ponding hotspots as pools at the level they fill to, and the exits where water
// leaves the park. One child object per group so each can be shown or hidden.
// Flow lines are dark, solid and smoothed; pools light and see-through with a crisp edge, so a line can be followed
// from end to end even where it runs through a pool.
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SpongePark
{
    public class FlowView : MonoBehaviour
    {
        public const string Lines = "lines", Arrows = "arrows", Ponding = "ponding", Exits = "exits";
        readonly Dictionary<string, GameObject> groups = new Dictionary<string, GameObject>();
        Material material, seeThrough;
        int unityLayer;
        static readonly Color Water = new Color32(0x2F, 0x67, 0x9E, 0xFF);
        static readonly Color DeepWater = new Color32(0x0B, 0x2A, 0x4E, 0xFF);
        static readonly Color Casing = new Color32(0xEE, 0xF6, 0xFB, 0xFF);           // a pale edge under each line
        public static readonly Color Pool = new Color32(0x7C, 0xCB, 0xEA, 0x6B);      // alpha: see-through
        public static readonly Color PoolEdge = new Color32(0x2A, 0x8C, 0xC4, 0xFF);
        static readonly Color Exit = new Color32(0xD2, 0x3F, 0x2C, 0xFF);
        static readonly Color HeldExit = new Color32(0xE8, 0x9B, 0x1C, 0xFF);   // no way out: held against the edge

        public static FlowView Create(string name, Transform parent, int layer)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            var v = go.AddComponent<FlowView>();
            v.unityLayer = layer;
            v.material = OnTopOfWater();
            v.seeThrough = new Material(Shader.Find("SpongePark/VertexLitAlpha"));
            return v;
        }

        /// Solid marks drawn after the see-through water (which writes no depth), so lines, arrows and edges inside a
        /// pool show on top of it, crisp, while the ground and models still hide them where they should.
        public static Material OnTopOfWater() => new Material(Shader.Find("SpongePark/VertexLit")) { renderQueue = 3100 };

        /// The analysis lines, traced cell by cell on the ground grid (cell: its size in m), drawn as a CAD-style spline:
        /// the stair-steps averaged out, the few points that carry the shape kept as fit points, and a smooth curve
        /// through them, so long runs are clean sweeps rather than wobbles.
        /// Light on purpose: just enough to take out the stair-steps, keeping the path where the water really runs.
        public static List<Vector4> CalmLine(IList<Vector4> pts, float cell)
        {
            var even = MeshBuilder.Relax(pts, false, cell * 0.5f, cell * 1.2f);
            return Spline.Through(Spline.FitPoints(even, cell * 0.35f, false), false, cell * 0.4f);
        }

        public static List<Vector3> CalmRing(IList<Vector3> pts, float cell)
        {
            var even = MeshBuilder.Relax(pts.Select(p => (Vector4)p).ToList(), true, cell * 0.5f, cell * 1.0f);
            var fit = Spline.FitPoints(even, cell * 0.3f, true);
            return (fit.Count >= 4 ? Spline.Through(fit, true, cell * 0.5f) : even).Select(p => (Vector3)p).ToList();
        }
        public static float Cell(JToken a) => a?["cell_m"] != null && a["cell_m"].Type != JTokenType.Null ? Mathf.Max(0.1f, (float)a["cell_m"]) : 1f;

        /// rp: the storm whose filling the pools show (the hollow's brim when the engine has no storms yet).
        /// ground (survey x, y -> ground level m; NaN where unknown): the lines and arrows are laid on it, so a smoothed
        /// line or a flat arrow never dips under the ground on a rise (the view's height is exaggerated).
        public void Build(JToken a, SiteFrame frame, IDictionary<string, bool> visible, int rp = 0, System.Func<float, float, float> ground = null)
        {
            foreach (var g in groups.Values) Destroy(g);
            groups.Clear();
            if (a == null) return;
            float lift = 0.06f + 0.03f * frame.Exaggeration;
            float thr = a["min_line_area_m2"] != null ? (float)a["min_line_area_m2"] : 40f;
            float cell = Cell(a);
            Vector3 Drape(Vector3 w) => OnGround(w, frame, ground);

            // flow lines: width and colour grow with the peak flow in this storm, on one scale across the storms
            // (with the area draining to each point until SWMM has run); each line one smoothed strip
            var m = new MeshBuilder();
            float maxA = a["flow_lines"].SelectMany(f => f["area_m2"].Values<float>()).DefaultIfEmpty(thr).Max();
            var rates = rp > 0 ? a["storm_summary"]?[rp.ToString()]?["line_cms_per_m2"] as JObject : null;
            float maxQ = a["flow_peak_cms"]?.Type == JTokenType.Float ? (float)a["flow_peak_cms"] : 0f;
            var lines = new List<(List<Vector3> pts, List<float> w, List<Color> col)>();
            foreach (var f in a["flow_lines"])
            {
                var xyz = f["xyz"].Values<float>().ToArray();
                var area = f["area_m2"].Values<float>().ToArray();
                float rate = rates != null && maxQ > 0 && rates[(string)f["exit"] ?? ""] != null ? (float)rates[(string)f["exit"]] : -1f;
                var raw = new List<Vector4>();
                for (int i = 0; i < area.Length && 3 * i + 2 < xyz.Length; i++)
                {
                    float t = rate >= 0 ? Mathf.Sqrt(Mathf.Clamp01(area[i] * rate / maxQ))
                                        : Mathf.Clamp01(Mathf.Log(area[i] / thr + 1, 2) / Mathf.Log(maxA / thr + 1, 2));
                    var p = frame.World(xyz[3 * i], xyz[3 * i + 1], xyz[3 * i + 2]);
                    raw.Add(new Vector4(p.x, p.y, p.z, t));
                }
                if (raw.Count < 2) continue;
                var sm = CalmLine(raw, cell);
                float wide = rate >= 0 ? 2.0f : 1.6f;
                // thin where a stream starts, thick where the streams have joined
                lines.Add((sm.Select(q => Drape((Vector3)q)).ToList(),
                           sm.Select(q => Mathf.Lerp(0.12f, wide, q.w)).ToList(),
                           sm.Select(q => Color.Lerp(Water, DeepWater, q.w)).ToList()));
            }
            foreach (var l in lines)   // the pale edges first, so where lines meet the dark of each stays on top
                m.Strip(l.pts, l.w.Select(w => w * 1.3f + 0.1f).ToList(), Enumerable.Repeat(Casing, l.pts.Count).ToList(), lift);
            foreach (var l in lines)
                m.Strip(l.pts, l.w, l.col, lift + 0.015f);
            Add(Lines, m, visible);

            // arrows: small flat chevrons pointing downhill, longer on steeper ground
            m = new MeshBuilder();
            foreach (var r in a["arrows"])
            {
                var v = r.Values<float>().ToArray();
                var p = frame.World(v[0], v[1], v[2]);
                var d = new Vector3(v[3], 0, v[4]);
                float len = Mathf.Lerp(0.9f, 1.9f, Mathf.Clamp01(v[5] / 5f));
                m.Arrow(p, d, len, 0.7f, new Color(0.17f, 0.35f, 0.5f), q => Drape(q) + Vector3.up * (lift + 0.04f));
            }
            Add(Arrows, m, visible);

            // ponding hotspots: a see-through pool at the level the hollow fills to in this storm (the ground hides
            // the part of the outline above that level), with a crisp edge
            m = new MeshBuilder();
            var pools = new MeshBuilder();
            void PoolAt(float[] o, float level)
            {
                var ring = new List<Vector3>();
                for (int i = 0; i + 1 < o.Length; i += 2) ring.Add(frame.World(o[i], o[i + 1], level));
                if (ring.Count < 4) return;
                ring = CalmRing(ring, cell);
                pools.Fill(ring, lift * 0.5f, Pool);
                m.Strip(new List<Vector3>(ring) { ring[0] }, 0.22f, PoolEdge, lift * 0.5f + 0.01f);
            }
            foreach (var h in a["hotspots"])
            {
                var st = StormFill(h, rp);
                if (st != null && (float)st["volume_m3"] <= 0) continue;
                PoolAt(h["outline"].Values<float>().ToArray(), st != null ? (float)st["water_level_m"] : (float)h["water_level_m"]);
                var c = frame.World((float)h["x"], (float)h["y"], (float)h["z"]);
                m.Prism(c, 0.08f, 2.5f, 6, PoolEdge);                                 // a pin to find it from afar
                m.RoundCrown(c + Vector3.up * 2.7f, 0.35f, PoolEdge);
            }
            // water held against a closed edge, at SWMM's peak level in this storm
            foreach (var e in a["exits"])
            {
                var o = rp > 0 ? e["held"]?["storms"]?[rp.ToString()]?["outline"]?.Values<float>().ToArray() : null;
                if (o == null) continue;
                PoolAt(o, (float)e["held"]["storms"][rp.ToString()]["water_level_m"]);
            }
            Add(Ponding, m, visible, pools);

            // where the ground drains to the park's edge. The model proposes no way out: only where the designer placed
            // an outlet or said water leaves is it an outlet (a target and a tall pin); everywhere else the water is
            // held against the edge (a small amber ring, no pin)
            m = new MeshBuilder();
            foreach (var e in a["exits"])
            {
                if (e["z"] == null || e["z"].Type == JTokenType.Null) continue;
                var c = frame.World((float)e["x"], (float)e["y"], (float)e["z"]);
                var foot = c + Vector3.up * (lift + 0.03f);
                if ((string)e["state"] != "open") continue;   // held: its pool shows; nothing that looks like a drain
                m.Ring(foot, 0f, 1.2f, Exit);
                m.Ring(foot, 1.2f, 1.6f, Color.white);
                m.Ring(foot, 1.6f, 2.3f, Exit);
                m.Prism(c, 0.14f, 4.5f, 8, Exit);
                m.RoundCrown(c + Vector3.up * 4.8f, 0.75f, Exit);
            }
            Add(Exits, m, visible);
        }

        /// A point in the view put on the ground at its place (its own height where the ground is unknown).
        public static Vector3 OnGround(Vector3 w, SiteFrame frame, System.Func<float, float, float> ground)
        {
            if (ground == null) return w;
            float z = ground(w.x + frame.X0, w.z + frame.Y0);
            return float.IsNaN(z) ? w : new Vector3(w.x, (z - frame.ZRef) * frame.Exaggeration, w.z);
        }

        /// How full a hollow gets in storm rp (volume, depth, area, level, spill); null without storm results.
        public static JToken StormFill(JToken hotspot, int rp) => rp > 0 ? hotspot["storms"]?[rp.ToString()] : null;

        void Add(string name, MeshBuilder m, IDictionary<string, bool> visible, MeshBuilder see = null)
        {
            var go = new GameObject("flow " + name) { layer = unityLayer };
            go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = m.ToMesh();
            go.AddComponent<MeshRenderer>().sharedMaterial = material;
            if (see != null)   // the see-through part, shown and hidden with the rest
            {
                var s = new GameObject("flow " + name + " see-through") { layer = unityLayer };
                s.transform.SetParent(go.transform, false);
                s.AddComponent<MeshFilter>().sharedMesh = see.ToMesh();
                var r = s.AddComponent<MeshRenderer>();
                r.sharedMaterial = seeThrough;
                r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            }
            go.SetActive(!visible.TryGetValue("flow:" + name, out var on) || on);
            groups[name] = go;
        }

        public void SetVisible(string name, bool on)
        {
            if (groups.TryGetValue(name, out var go)) go.SetActive(on);
        }
    }
}
