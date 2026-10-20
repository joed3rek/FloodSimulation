// The designer's NbS elements drawn on the ground (outlines, swale lines, wells), the selected one
// highlighted, plus the shape being drawn with the design tools.
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SpongePark
{
    public class DesignOverlay : MonoBehaviour
    {
        GameObject elements, preview;
        Material material;
        int unityLayer;
        static readonly Color Selected = new Color32(0xC1, 0x8C, 0x5D, 0xFF);

        public static DesignOverlay Create(string name, Transform parent, int layer)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            var v = go.AddComponent<DesignOverlay>();
            v.unityLayer = layer;
            v.material = new Material(Shader.Find("SpongePark/VertexLit"));
            return v;
        }

        public static Color TypeColour(string type) => type switch
        {
            "rain_garden" => new Color(0.18f, 0.55f, 0.24f),
            "bioswale" => new Color(0.1f, 0.62f, 0.48f),
            "detention_pond" => new Color(0.16f, 0.47f, 0.84f),
            "retention_pond" => new Color(0.08f, 0.3f, 0.62f),
            "recharge_well" => new Color(0.38f, 0.31f, 0.84f),
            _ => new Color(0.4f, 0.4f, 0.4f)
        };

        /// fc: the scenario's elements (GeoJSON); ground: level at a survey point (m).
        public void Build(JToken fc, SiteFrame frame, System.Func<float, float, float> ground, string selectedId)
        {
            if (elements != null) Destroy(elements);
            if (fc == null || frame == null) return;
            var m = new MeshBuilder();
            float lift = 0.08f + 0.03f * frame.Exaggeration;
            foreach (var f in fc["features"] ?? new JArray())
            {
                var p = f["properties"];
                var type = (string)p["type"];
                bool sel = (string)p["id"] == selectedId;
                var col = sel ? Selected : TypeColour(type);
                var g = f["geometry"];
                var gt = (string)g["type"];
                if (gt == "Point")
                {
                    float x = (float)g["coordinates"][0], y = (float)g["coordinates"][1];
                    float d = p["well_diameter_m"] != null && p["well_diameter_m"].Type != JTokenType.Null ? (float)p["well_diameter_m"] : 1.2f;
                    var c = frame.World(x, y, ground(x, y));
                    m.Prism(c, d / 2, 0.35f, 16, col);
                    m.Prism(c + Vector3.up * 0.35f, d / 2 * 0.8f, 0.02f, 16, col * 0.6f);
                    continue;
                }
                var coords = gt == "Polygon" ? g["coordinates"][0] : g["coordinates"];
                var pts = coords.Select(q => { float x = (float)q[0], y = (float)q[1]; return frame.World(x, y, ground(x, y)); }).ToList();
                float w = gt == "LineString"
                    ? (p["top_width_m"] != null && p["top_width_m"].Type != JTokenType.Null ? (float)p["top_width_m"] : 3f)
                    : (sel ? 0.5f : 0.3f);
                if (gt == "LineString") m.Ribbon(pts, w, lift, new Color(col.r, col.g, col.b) * 0.9f);
                m.Ribbon(pts, sel ? 0.45f : 0.25f, lift + 0.02f, col);
                if (sel)   // handles to drag: the corners, or a curve's fit points
                {
                    var grips = p["fit_points"] is JArray fp
                        ? fp.Select(q => { float x = (float)q[0], y = (float)q[1]; return frame.World(x, y, ground(x, y)); }).ToList()
                        : pts;
                    foreach (var q in grips) m.Box(q + Vector3.up * lift, 0.7f, 0.5f, Color.white);
                }
            }
            elements = Make("elements", m);
        }

        /// The shape being drawn or reshaped: the placed points, and the line through them (to the pointer, closed
        /// for an outline; straight or smooth, worked out by the caller). Nulls clear it.
        public void Preview(List<Vector3> pts, List<Vector3> path, Color col)
        {
            if (preview != null) Destroy(preview);
            if (pts == null || path == null || path.Count == 0) return;
            var m = new MeshBuilder();
            var up = Vector3.up * 0.15f;
            if (path.Count >= 2) m.Ribbon(path.Select(q => q + up).ToList(), 0.3f, 0, col);
            foreach (var q in pts) m.Prism(q, 0.25f, 0.4f, 8, col);
            preview = Make("preview", m);
        }

        GameObject Make(string name, MeshBuilder m)
        {
            var go = new GameObject(name) { layer = unityLayer };
            go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = m.ToMesh();
            go.AddComponent<MeshRenderer>().sharedMaterial = material;
            return go;
        }
    }
}
