// Where water goes on the existing ground (engine /flow): main flow lines (wider where more ground drains
// to them), downhill arrows, ponding hotspots as pools at the level they fill to, and the exits where water
// leaves the park. One child object per group so each can be shown or hidden.
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
        Material material;
        int unityLayer;
        static readonly Color Water = new Color32(0x3E, 0x86, 0xB5, 0xFF);
        static readonly Color DeepWater = new Color32(0x1F, 0x4E, 0x79, 0xFF);
        static readonly Color Pool = new Color32(0x4A, 0x9C, 0xC9, 0xFF);
        static readonly Color Exit = new Color32(0xC1, 0x4B, 0x3A, 0xFF);
        static readonly Color HeldExit = new Color32(0xD9, 0x9A, 0x2B, 0xFF);   // no way out: held against the edge

        public static FlowView Create(string name, Transform parent, int layer)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            var v = go.AddComponent<FlowView>();
            v.unityLayer = layer;
            v.material = new Material(Shader.Find("SpongePark/VertexLit"));
            return v;
        }

        /// rp: the storm whose filling the pools show (the hollow's brim when the engine has no storms yet).
        public void Build(JToken a, SiteFrame frame, IDictionary<string, bool> visible, int rp = 0)
        {
            foreach (var g in groups.Values) Destroy(g);
            groups.Clear();
            if (a == null) return;
            float lift = 0.06f + 0.03f * frame.Exaggeration;
            float thr = a["min_line_area_m2"] != null ? (float)a["min_line_area_m2"] : 40f;

            // flow lines: width and colour grow with the area draining to each point
            var m = new MeshBuilder();
            float maxA = a["flow_lines"].SelectMany(f => f["area_m2"].Values<float>()).DefaultIfEmpty(thr).Max();
            foreach (var f in a["flow_lines"])
            {
                var xyz = f["xyz"].Values<float>().ToArray();
                var area = f["area_m2"].Values<float>().ToArray();
                for (int i = 0; i + 1 < area.Length; i++)
                {
                    var p0 = frame.World(xyz[3 * i], xyz[3 * i + 1], xyz[3 * i + 2]) + Vector3.up * lift;
                    var p1 = frame.World(xyz[3 * i + 3], xyz[3 * i + 4], xyz[3 * i + 5]) + Vector3.up * lift;
                    float t = Mathf.Clamp01(Mathf.Log(area[i] / thr + 1, 2) / Mathf.Log(maxA / thr + 1, 2));
                    m.Ribbon(new List<Vector3> { p0, p1 }, Mathf.Lerp(0.25f, 1.2f, t), 0, Color.Lerp(Water, DeepWater, t));
                }
            }
            Add(Lines, m, visible);

            // arrows: small flat chevrons pointing downhill, longer on steeper ground
            m = new MeshBuilder();
            foreach (var r in a["arrows"])
            {
                var v = r.Values<float>().ToArray();
                var p = frame.World(v[0], v[1], v[2]) + Vector3.up * lift;
                var d = new Vector3(v[3], 0, v[4]);
                float len = Mathf.Lerp(0.6f, 1.6f, Mathf.Clamp01(v[5] / 5f));
                m.Arrow(p, d, len, 0.45f, new Color(0.17f, 0.35f, 0.5f));
            }
            Add(Arrows, m, visible);

            // ponding hotspots: a pool at the level the hollow fills to in this storm (the ground hides the
            // part of the outline above that level)
            m = new MeshBuilder();
            foreach (var h in a["hotspots"])
            {
                var o = h["outline"].Values<float>().ToArray();
                var st = StormFill(h, rp);
                if (st != null && (float)st["volume_m3"] <= 0) continue;
                float level = st != null ? (float)st["water_level_m"] : (float)h["water_level_m"];
                var ring = new List<Vector3>();
                for (int i = 0; i + 1 < o.Length; i += 2) ring.Add(frame.World(o[i], o[i + 1], level));
                if (ring.Count >= 4) m.Fill(ring, lift * 0.5f, Pool);
                var c = frame.World((float)h["x"], (float)h["y"], (float)h["z"]);
                m.Prism(c, 0.08f, 2.5f, 6, Pool);                                     // a pin to find it from afar
                m.RoundCrown(c + Vector3.up * 2.7f, 0.35f, Pool);
            }
            Add(Ponding, m, visible);

            // exits: where flow leaves the surveyed park
            m = new MeshBuilder();
            foreach (var e in a["exits"])
            {
                if (e["z"] == null || e["z"].Type == JTokenType.Null) continue;
                var c = frame.World((float)e["x"], (float)e["y"], (float)e["z"]);
                var col = (string)e["state"] == "closed" ? HeldExit : Exit;
                m.Prism(c, 0.1f, 3f, 6, col);
                m.RoundCrown(c + Vector3.up * 3.2f, 0.4f, col);
            }
            Add(Exits, m, visible);
        }

        /// How full a hollow gets in storm rp (volume, depth, area, level, spill); null without storm results.
        public static JToken StormFill(JToken hotspot, int rp) => rp > 0 ? hotspot["storms"]?[rp.ToString()] : null;

        void Add(string name, MeshBuilder m, IDictionary<string, bool> visible)
        {
            var go = new GameObject("flow " + name) { layer = unityLayer };
            go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = m.ToMesh();
            go.AddComponent<MeshRenderer>().sharedMaterial = material;
            go.SetActive(!visible.TryGetValue("flow:" + name, out var on) || on);
            groups[name] = go;
        }

        public void SetVisible(string name, bool on)
        {
            if (groups.TryGetValue(name, out var go)) go.SetActive(on);
        }
    }
}
