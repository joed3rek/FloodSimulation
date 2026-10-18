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
                bool fenced = kind == "boundary" && L["fenced"] != null && (bool)L["fenced"];
                if (fenced) kind = "fence";   // the park is fenced
                ColorUtility.TryParseHtmlString((string)L["color"] ?? "#9A9A90", out var col);
                if (fenced) col = new Color32(0x2F, 0x3A, 0x33, 0xFF);   // fencing is dark metal, whatever the layer colour
                float h = L["height_m"]?.Type == JTokenType.Float || L["height_m"]?.Type == JTokenType.Integer ? (float)L["height_m"] : 0;
                float w = L["width_m"]?.Type == JTokenType.Float || L["width_m"]?.Type == JTokenType.Integer ? (float)L["width_m"] : 0.15f;
                // surfaces lie just above the ground; more lift when heights are exaggerated
                float lift = 0.03f + 0.02f * frame.Exaggeration;
                foreach (var f in L["features"])
                {
                    var a = f["xyz"].Values<float>().ToArray();
                    var fc = col;
                    if (f["color"] != null) ColorUtility.TryParseHtmlString((string)f["color"], out fc);
                    var g = (string)f["g"];
                    if (g == "mesh")
                    {
                        var vs = new List<Vector3>(a.Length / 3);
                        for (int i = 0; i + 2 < a.Length; i += 3) vs.Add(frame.World(a[i], a[i + 1], a[i + 2]) + Vector3.up * lift);
                        mesh.Surface(vs, f["tri"].Values<int>().ToArray(), fc);
                    }
                    else if (g == "point")
                    {
                        var p = frame.World(a[0], a[1], a[2]);
                        if (kind == "gate" && f["width_m"] != null)
                            mesh.Gate(p, (float)f["width_m"], f["angle_deg"] != null ? (float)f["angle_deg"] : 0, h > 0 ? h : 2.1f, fc);
                        else
                            AddPoint(mesh, kind, p, f["radius_m"] != null ? (float)f["radius_m"] : 0, h, fc);
                    }
                    else
                    {
                        var pts = new List<Vector3>(a.Length / 3);
                        for (int i = 0; i + 2 < a.Length; i += 3) pts.Add(frame.World(a[i], a[i + 1], a[i + 2]));
                        bool closed = f["closed"] != null && (bool)f["closed"];
                        if (f["on_ground"] != null && (bool)f["on_ground"]) mesh.Ribbon(pts, 0.12f, lift + 0.02f, new Color(0.6f, 0.58f, 0.52f));
                        else AddLine(mesh, kind, pts, closed, h, w, fc, lift + 0.02f);
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

        static void AddLine(MeshBuilder m, string kind, List<Vector3> pts, bool closed, float h, float w, Color col, float lift)
        {
            switch (kind)
            {
                case "wall": case "fence":   // boundary walls are shown as metal fencing
                    m.MetalFence(pts, h > 0 ? h : 2f, col);
                    break;
                case "gate":
                    m.Ribbon(pts, 0.3f, lift, col);
                    break;
                case "building":
                    if (closed && pts.Count >= 4) m.Block(pts, h, col);
                    else m.Fence(pts, h, col, 0.2f);
                    break;
                case "water":
                    if (closed && pts.Count >= 4) m.Fill(pts, 0.03f, new Color(col.r, col.g, col.b) * 1.1f);
                    m.Ribbon(pts, w, lift, col);
                    break;
                case "tree": case "palm":   // a large outline on a tree layer (a grove or hedge edge)
                    m.Ribbon(pts, 0.3f, lift, col);
                    break;
                default:
                    m.Ribbon(pts, w, lift, col);
                    break;
            }
        }

        static void AddPoint(MeshBuilder m, string kind, Vector3 p, float r, float h, Color col)
        {
            switch (kind)
            {
                case "tree":
                {
                    // a round crown: one full sphere with two smaller ones blended in, on a tapered trunk
                    float cr = r > 0 ? Mathf.Clamp(r, 1.5f, 6f) : 2.8f, trunkH = Mathf.Max(1.8f, h - 1.7f * cr);
                    m.Trunk(p, 0.22f, 0.14f, trunkH + cr * 0.5f, Trunk);
                    var c0 = p + Vector3.up * (trunkH + cr * 0.85f);
                    m.RoundCrown(c0, cr, col);
                    m.RoundCrown(c0 + new Vector3(cr * 0.45f, -cr * 0.2f, cr * 0.15f), cr * 0.62f, col * 0.95f);
                    m.RoundCrown(c0 + new Vector3(-cr * 0.35f, -cr * 0.15f, -cr * 0.4f), cr * 0.58f, col * 1.05f);
                    break;
                }
                case "palm":
                {
                    float cr = r > 0 ? Mathf.Clamp(r, 1.5f, 3.5f) : 2.5f;
                    m.Trunk(p, 0.18f, 0.13f, h, new Color(0.55f, 0.45f, 0.35f));
                    m.RoundCrown(p + Vector3.up * (h + cr * 0.35f), cr, col);
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

        /// A smooth-shaded triangle (normals per corner), both sides.
        void SmoothTri(Vector3 a, Vector3 b, Vector3 d, Vector3 na, Vector3 nb, Vector3 nd, Color ca, Color cb, Color cd)
        {
            int i = v.Count;
            v.Add(a); v.Add(b); v.Add(d);
            n.Add(na); n.Add(nb); n.Add(nd);
            c.Add(ca); c.Add(cb); c.Add(cd);
            t.Add(i); t.Add(i + 1); t.Add(i + 2);
            t.Add(i); t.Add(i + 2); t.Add(i + 1);
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

        /// A box from a to b with a square cross-section of side `size` (rails, posts, bars).
        public void Beam(Vector3 a, Vector3 b, float size, Color col)
        {
            var d = b - a;
            if (d.sqrMagnitude < 1e-8f) return;
            var axis = d.normalized;
            var u = Vector3.Cross(axis, Mathf.Abs(axis.y) > 0.9f ? Vector3.forward : Vector3.up).normalized * (size / 2);
            var w = Vector3.Cross(axis, u).normalized * (size / 2);
            Vector3[] q = { u + w, u - w, -u - w, -u + w };
            for (int i = 0; i < 4; i++) Quad(a + q[i], b + q[i], b + q[(i + 1) % 4], a + q[(i + 1) % 4], col);
            Quad(b + q[0], b + q[1], b + q[2], b + q[3], col);
        }

        /// Park fencing along a line: a low stone plinth, posts every 2.5 m, top and bottom rails and
        /// vertical bars, `h` metres high in all.
        public void MetalFence(List<Vector3> pts, float h, Color metal)
        {
            const float plinthH = 0.3f, plinthW = 0.28f, postEvery = 2.5f, barEvery = 0.15f;
            var stone = new Color(0.72f, 0.68f, 0.6f);
            float run = 0;
            for (int i = 0; i + 1 < pts.Count; i++)
            {
                Vector3 a = pts[i], b = pts[i + 1];
                var flat = b - a;
                flat.y = 0;
                float len = flat.magnitude;
                if (len < 1e-4f) continue;
                var dir = flat / len;
                var side = Vector3.Cross(Vector3.up, dir) * (plinthW / 2);
                var up = Vector3.up;
                // plinth
                Quad(a + side, b + side, b + side + up * plinthH, a + side + up * plinthH, stone);
                Quad(a - side, b - side, b - side + up * plinthH, a - side + up * plinthH, stone);
                Quad(a - side + up * plinthH, a + side + up * plinthH, b + side + up * plinthH, b - side + up * plinthH, stone * 1.08f);
                // rails
                Beam(a + up * (plinthH + 0.12f), b + up * (plinthH + 0.12f), 0.05f, metal);
                Beam(a + up * (h - 0.08f), b + up * (h - 0.08f), 0.05f, metal);
                // posts and bars at even spacing along the whole fence
                for (float s0 = Mathf.Ceil(run / barEvery) * barEvery; s0 < run + len; s0 += barEvery)
                {
                    var p = Vector3.Lerp(a, b, (s0 - run) / len);
                    bool post = Mathf.Abs(s0 / postEvery - Mathf.Round(s0 / postEvery)) * postEvery < barEvery / 2;
                    if (post) Beam(p + up * plinthH, p + up * (h + 0.05f), 0.09f, metal * 0.85f);
                    else Beam(p + up * plinthH, p + up * (h - 0.03f), 0.022f, metal);
                }
                run += len;
            }
        }

        /// A metal park gate: two stone pillars and two barred leaves, `width` across, facing along
        /// `angleDeg` (degrees from east, anticlockwise in plan), `h` high.
        public void Gate(Vector3 p, float width, float angleDeg, float h, Color metal)
        {
            var u = new Vector3(Mathf.Cos(angleDeg * Mathf.Deg2Rad), 0, Mathf.Sin(angleDeg * Mathf.Deg2Rad));
            var up = Vector3.up;
            var pillar = new Color(0.78f, 0.74f, 0.66f);
            float half = width / 2, pw = 0.4f;
            foreach (var sgn in new[] { -1f, 1f })
            {
                var c0 = p + u * sgn * (half + pw / 2);
                Beam(c0, c0 + up * (h + 0.25f), pw, pillar);
                Beam(c0 + up * (h + 0.25f), c0 + up * (h + 0.35f), pw + 0.08f, pillar * 0.9f);   // cap
            }
            float gap = 0.04f, leaf = half - gap * 1.5f;
            foreach (var sgn in new[] { -1f, 1f })
            {
                var hinge = p + u * sgn * (half - gap);
                var tip = p + u * sgn * (gap / 2);
                // frame
                Beam(hinge + up * 0.08f, tip + up * 0.08f, 0.06f, metal);
                Beam(hinge + up * (h - 0.05f), tip + up * (h - 0.05f), 0.06f, metal);
                Beam(hinge + up * (h * 0.45f), tip + up * (h * 0.45f), 0.04f, metal);
                Beam(hinge + up * 0.05f, hinge + up * h, 0.07f, metal);
                Beam(tip + up * 0.05f, tip + up * h, 0.07f, metal);
                // bars with a short spike above the top rail
                int bars = Mathf.Max(2, Mathf.RoundToInt(leaf / 0.12f));
                for (int i = 1; i < bars; i++)
                {
                    var b = Vector3.Lerp(hinge, tip, i / (float)bars);
                    Beam(b + up * 0.08f, b + up * (h + 0.12f), 0.025f, metal);
                }
            }
        }

        /// A tapered round trunk.
        public void Trunk(Vector3 p, float r0, float r1, float h, Color col)
        {
            const int sides = 10;
            for (int i = 0; i < sides; i++)
            {
                float a0 = i * Mathf.PI * 2 / sides, a1 = (i + 1) * Mathf.PI * 2 / sides;
                var d0 = new Vector3(Mathf.Cos(a0), 0, Mathf.Sin(a0));
                var d1 = new Vector3(Mathf.Cos(a1), 0, Mathf.Sin(a1));
                SmoothTri(p + d0 * r0, p + d1 * r0, p + d1 * r1 + Vector3.up * h, d0, d1, d1, col, col, col * 1.1f);
                SmoothTri(p + d0 * r0, p + d1 * r1 + Vector3.up * h, p + d0 * r1 + Vector3.up * h, d0, d1, d0, col, col * 1.1f, col * 1.1f);
            }
        }

        /// A round, smooth-shaded tree crown of radius r centred at c, lighter on top.
        public void RoundCrown(Vector3 c, float r, Color col)
        {
            const int seg = 16, rings = 10;
            var top = Color.Lerp(col, Color.white, 0.12f);
            var bottom = col * 0.72f;
            top.a = bottom.a = 1;
            Vector3 N(int i, int j) => new Vector3(Mathf.Sin(Mathf.PI * i / rings) * Mathf.Cos(2 * Mathf.PI * j / seg),
                                                   Mathf.Cos(Mathf.PI * i / rings),
                                                   Mathf.Sin(Mathf.PI * i / rings) * Mathf.Sin(2 * Mathf.PI * j / seg));
            Color C(int i) => Color.Lerp(top, bottom, i / (float)rings);
            for (int i = 0; i < rings; i++)
                for (int j = 0; j < seg; j++)
                {
                    Vector3 n00 = N(i, j), n01 = N(i, j + 1), n10 = N(i + 1, j), n11 = N(i + 1, j + 1);
                    SmoothTri(c + n00 * r, c + n01 * r, c + n11 * r, n00, n01, n11, C(i), C(i), C(i + 1));
                    SmoothTri(c + n00 * r, c + n11 * r, c + n10 * r, n00, n11, n10, C(i), C(i + 1), C(i + 1));
                }
        }

        /// A surface lying on the ground (road, path), triangulated by the engine.
        public void Surface(List<Vector3> verts, int[] tris, Color col)
        {
            for (int i = 0; i + 2 < tris.Length; i += 3)
            {
                Vector3 a = verts[tris[i]], b = verts[tris[i + 1]], d = verts[tris[i + 2]];
                var nn = Vector3.Cross(b - a, d - a);
                if (nn.sqrMagnitude < 1e-12f) continue;
                nn.Normalize();
                if (nn.y < 0) nn = -nn;
                SmoothTri(a, b, d, nn, nn, nn, col, col, col);
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
