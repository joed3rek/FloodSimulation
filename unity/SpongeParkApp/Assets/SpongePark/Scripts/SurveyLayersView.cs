// What the survey drawing shows (walls, fences, gates, buildings, trees, paths, roads, drains, water,
// manholes, poles ...) drawn in 3D on the ground model, one child object per drawing layer so each can be
// switched on and off. Geometry comes from the engine (/site/layers), already draped on the DEM.
// Heights of walls, buildings and trees are display heights in true metres (not exaggerated).
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.Rendering;

namespace SpongePark
{
    public class SurveyLayersView : MonoBehaviour
    {
        readonly Dictionary<string, GameObject> layers = new Dictionary<string, GameObject>();
        Material material;
        int unityLayer;

        public static SurveyLayersView Create(string name, Transform parent, int layer)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            var v = go.AddComponent<SurveyLayersView>();
            v.unityLayer = layer;
            v.material = new Material(Shader.Find("SpongePark/VertexLit"));
            return v;
        }

        public void Build(JToken payload, SiteFrame frame, IDictionary<string, bool> visible)
        {
            foreach (var go in layers.Values) Destroy(go);
            layers.Clear();
            if (payload == null) return;
            foreach (var L in payload["layers"])
            {
                var name = (string)L["name"];
                var mesh = new MeshBuilder();
                var kind = (string)L["kind"];
                ColorUtility.TryParseHtmlString((string)L["color"] ?? "#9A9A90", out var col);
                float h = L["height_m"]?.Type == JTokenType.Float || L["height_m"]?.Type == JTokenType.Integer ? (float)L["height_m"] : 0;
                float w = L["width_m"]?.Type == JTokenType.Float || L["width_m"]?.Type == JTokenType.Integer ? (float)L["width_m"] : 0.15f;
                foreach (var f in L["features"])
                {
                    var a = f["xyz"].Values<float>().ToArray();
                    if ((string)f["g"] == "point")
                    {
                        var p = frame.World(a[0], a[1], a[2]);
                        float r = f["radius_m"] != null ? (float)f["radius_m"] : 0;
                        AddPoint(mesh, kind, p, r, h, col);
                    }
                    else
                    {
                        var pts = new List<Vector3>(a.Length / 3);
                        for (int i = 0; i + 2 < a.Length; i += 3) pts.Add(frame.World(a[i], a[i + 1], a[i + 2]));
                        bool closed = f["closed"] != null && (bool)f["closed"];
                        if (f["on_ground"] != null && (bool)f["on_ground"]) mesh.Ribbon(pts, 0.3f, 0.06f, col);
                        else AddLine(mesh, kind, pts, closed, h, w, col);
                    }
                }
                var go = new GameObject(name) { layer = unityLayer };
                go.transform.SetParent(transform, false);
                go.AddComponent<MeshFilter>().sharedMesh = mesh.ToMesh();
                go.AddComponent<MeshRenderer>().sharedMaterial = material;
                go.SetActive(!visible.TryGetValue(name, out var on) || on);
                layers[name] = go;
            }
        }

        public void SetVisible(string name, bool on)
        {
            if (layers.TryGetValue(name, out var go)) go.SetActive(on);
        }

        // ------------------------------------------------------------ shapes
        static readonly Color Trunk = new Color(0.42f, 0.31f, 0.23f);

        static void AddLine(MeshBuilder m, string kind, List<Vector3> pts, bool closed, float h, float w, Color col)
        {
            switch (kind)
            {
                case "wall": case "fence": case "gate":
                    m.Fence(pts, h, col, kind == "gate" ? 0.25f : 0.2f);
                    break;
                case "building":
                    if (closed && pts.Count >= 4) m.Block(pts, h, col);
                    else m.Fence(pts, h, col, 0.2f);
                    break;
                case "water":
                    if (closed && pts.Count >= 4) m.Fill(pts, 0.03f, new Color(col.r, col.g, col.b) * 1.1f);
                    m.Ribbon(pts, w, 0.06f, col);
                    break;
                case "tree": case "palm":   // a large outline on a tree layer (a grove or hedge edge)
                    m.Ribbon(pts, 0.3f, 0.06f, col);
                    break;
                default:
                    m.Ribbon(pts, w, 0.06f, col);
                    break;
            }
        }

        static void AddPoint(MeshBuilder m, string kind, Vector3 p, float r, float h, Color col)
        {
            switch (kind)
            {
                case "tree":
                {
                    float cr = r > 0 ? Mathf.Clamp(r, 1f, 7f) : 2.5f, trunkH = Mathf.Max(1.5f, h - 1.6f * cr);
                    m.Prism(p, 0.18f, trunkH + 0.3f, 6, Trunk);
                    m.Sphere(p + Vector3.up * (trunkH + cr * 0.8f), cr, cr * 0.8f, col);
                    break;
                }
                case "palm":
                {
                    float cr = r > 0 ? Mathf.Clamp(r, 1.5f, 5f) : 3f;
                    m.Prism(p, 0.15f, h, 6, new Color(0.55f, 0.45f, 0.35f));
                    m.Sphere(p + Vector3.up * h, cr, 0.9f, col);
                    break;
                }
                case "manhole": m.Prism(p, 0.4f, 0.12f, 8, col); break;
                case "pole": m.Prism(p, 0.1f, h > 0 ? h : 7f, 4, col); break;
                case "furniture": m.Box(p, 0.6f, h > 0 ? h : 0.6f, col); break;
                default: m.Box(p, 0.3f, 0.3f, col); break;
            }
        }
    }

    /// Collects triangles with vertex colours and normals (flat shaded) for one mesh.
    public class MeshBuilder
    {
        readonly List<Vector3> v = new List<Vector3>();
        readonly List<Vector3> n = new List<Vector3>();
        readonly List<Color> c = new List<Color>();
        readonly List<int> t = new List<int>();

        /// Every triangle is added both ways round with its own normal, so it shows (and is lit) from either side.
        void Tri(Vector3 a, Vector3 b, Vector3 d, Color col)
        {
            var nn = Vector3.Cross(b - a, d - a);
            if (nn.sqrMagnitude < 1e-12f) return;
            nn.Normalize();
            One(a, b, d, nn, col);
            One(a, d, b, -nn, col);
        }

        void One(Vector3 a, Vector3 b, Vector3 d, Vector3 nn, Color col)
        {
            int i = v.Count;
            v.Add(a); v.Add(b); v.Add(d);
            n.Add(nn); n.Add(nn); n.Add(nn);
            c.Add(col); c.Add(col); c.Add(col);
            t.Add(i); t.Add(i + 1); t.Add(i + 2);
        }

        void Quad(Vector3 a, Vector3 b, Vector3 d, Vector3 e, Color col) { Tri(a, b, d, col); Tri(a, d, e, col); }

        void TwoSided(Vector3 a, Vector3 b, Vector3 d, Vector3 e, Color col) => Quad(a, b, d, e, col);

        /// A thin upright wall along a line, from the ground up h metres, with a top cap.
        public void Fence(List<Vector3> pts, float h, Color col, float thick)
        {
            var up = Vector3.up * h;
            var top = col * 0.85f;
            top.a = 1;
            for (int i = 0; i + 1 < pts.Count; i++)
            {
                Vector3 a = pts[i], b = pts[i + 1];
                var dir = b - a;
                dir.y = 0;
                if (dir.sqrMagnitude < 1e-8f) continue;
                var side = Vector3.Cross(Vector3.up, dir.normalized) * (thick / 2);
                TwoSided(a + side, b + side, b + side + up, a + side + up, col);
                TwoSided(a - side, b - side, b - side + up, a - side + up, col);
                Quad(a - side + up, a + side + up, b + side + up, b - side + up, top);
            }
        }

        /// A flat strip lying on the ground (paths, roads, drains, contours), lifted slightly.
        public void Ribbon(List<Vector3> pts, float w, float lift, Color col)
        {
            var up = Vector3.up * lift;
            for (int i = 0; i + 1 < pts.Count; i++)
            {
                Vector3 a = pts[i] + up, b = pts[i + 1] + up;
                var dir = b - a;
                dir.y = 0;
                if (dir.sqrMagnitude < 1e-8f) continue;
                var side = Vector3.Cross(Vector3.up, dir.normalized) * (w / 2);
                Quad(a - side, a + side, b + side, b - side, col);
            }
        }

        /// A building: the outline extruded from its lowest ground point to h above its highest.
        public void Block(List<Vector3> ring, float h, Color col)
        {
            var pts = Open(ring);
            float baseY = pts.Min(p => p.y), topY = pts.Max(p => p.y) + h;
            var wall = col * 0.9f;
            wall.a = 1;
            for (int i = 0; i < pts.Count; i++)
            {
                var a = pts[i]; var b = pts[(i + 1) % pts.Count];
                TwoSided(new Vector3(a.x, baseY, a.z), new Vector3(b.x, baseY, b.z), new Vector3(b.x, topY, b.z), new Vector3(a.x, topY, a.z), wall);
            }
            Fill(pts.Select(p => new Vector3(p.x, topY, p.z)).ToList(), 0, col);
        }

        /// A flat polygon (roof, water surface) at the height of its lowest point plus lift.
        public void Fill(List<Vector3> ring, float lift, Color col)
        {
            var pts = Open(ring);
            if (pts.Count < 3) return;
            float y = pts.Min(p => p.y) + lift;
            var xz = pts.Select(p => new Vector2(p.x, p.z)).ToList();
            foreach (var (i, j, k) in EarClip(xz))
            {
                var a = new Vector3(xz[i].x, y, xz[i].y); var b = new Vector3(xz[j].x, y, xz[j].y); var d = new Vector3(xz[k].x, y, xz[k].y);
                Tri(a, b, d, col);
            }
        }

        public void Prism(Vector3 p, float r, float h, int sides, Color col)
        {
            for (int i = 0; i < sides; i++)
            {
                float a0 = i * Mathf.PI * 2 / sides, a1 = (i + 1) * Mathf.PI * 2 / sides;
                var o0 = new Vector3(Mathf.Cos(a0), 0, Mathf.Sin(a0)) * r;
                var o1 = new Vector3(Mathf.Cos(a1), 0, Mathf.Sin(a1)) * r;
                Quad(p + o0, p + o0 + Vector3.up * h, p + o1 + Vector3.up * h, p + o1, col);
                Tri(p + Vector3.up * h, p + o1 + Vector3.up * h, p + o0 + Vector3.up * h, col);
            }
        }

        public void Box(Vector3 p, float s, float h, Color col) => Prism(p, s * 0.7f, h, 4, col);

        /// A low-poly ellipsoid (tree canopy): horizontal radius r, vertical radius ry, centred at c.
        public void Sphere(Vector3 c, float r, float ry, Color col)
        {
            const int seg = 8, rings = 5;
            var dark = col * 0.8f;
            dark.a = 1;
            for (int i = 0; i < rings; i++)
            {
                float t0 = Mathf.PI * i / rings, t1 = Mathf.PI * (i + 1) / rings;
                for (int j = 0; j < seg; j++)
                {
                    float p0 = 2 * Mathf.PI * j / seg, p1 = 2 * Mathf.PI * (j + 1) / seg;
                    Vector3 P(float t, float p) => c + new Vector3(r * Mathf.Sin(t) * Mathf.Cos(p), ry * Mathf.Cos(t), r * Mathf.Sin(t) * Mathf.Sin(p));
                    var shade = Color.Lerp(col, dark, (float)i / rings);
                    Quad(P(t0, p0), P(t0, p1), P(t1, p1), P(t1, p0), shade);
                }
            }
        }

        static List<Vector3> Open(List<Vector3> ring)
        {
            var pts = new List<Vector3>(ring);
            if (pts.Count > 1 && (pts[0] - pts[pts.Count - 1]).sqrMagnitude < 1e-6f) pts.RemoveAt(pts.Count - 1);
            return pts;
        }

        /// Triangles of a simple polygon (ear clipping); falls back to a fan if the outline is odd.
        static IEnumerable<(int, int, int)> EarClip(List<Vector2> p)
        {
            var idx = Enumerable.Range(0, p.Count).ToList();
            float area = 0;
            for (int i = 0; i < p.Count; i++) { var a = p[i]; var b = p[(i + 1) % p.Count]; area += a.x * b.y - b.x * a.y; }
            if (area < 0) idx.Reverse();
            var tris = new List<(int, int, int)>();
            int guard = 0;
            while (idx.Count > 3 && guard++ < 10000)
            {
                bool clipped = false;
                for (int i = 0; i < idx.Count; i++)
                {
                    int a = idx[(i + idx.Count - 1) % idx.Count], b = idx[i], d = idx[(i + 1) % idx.Count];
                    if (Cross(p[a], p[b], p[d]) <= 0) continue;
                    bool inside = false;
                    foreach (var q in idx)
                        if (q != a && q != b && q != d && InTri(p[q], p[a], p[b], p[d])) { inside = true; break; }
                    if (inside) continue;
                    tris.Add((a, b, d));
                    idx.RemoveAt(i);
                    clipped = true;
                    break;
                }
                if (!clipped) break;
            }
            if (idx.Count == 3) tris.Add((idx[0], idx[1], idx[2]));
            else for (int i = 1; i + 1 < idx.Count; i++) tris.Add((idx[0], idx[i], idx[i + 1]));
            return tris;
        }

        static float Cross(Vector2 a, Vector2 b, Vector2 c) => (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);

        static bool InTri(Vector2 p, Vector2 a, Vector2 b, Vector2 c) =>
            Cross(a, b, p) >= 0 && Cross(b, c, p) >= 0 && Cross(c, a, p) >= 0;

        public Mesh ToMesh()
        {
            var m = new Mesh { indexFormat = IndexFormat.UInt32 };
            m.SetVertices(v);
            m.SetNormals(n);
            m.SetColors(c);
            m.SetTriangles(t, 0);
            m.RecalculateBounds();
            return m;
        }
    }
}
