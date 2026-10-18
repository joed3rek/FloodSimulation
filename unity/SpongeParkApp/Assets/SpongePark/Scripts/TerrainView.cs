// Terrain mesh from an engine height grid, coloured by height, with NbS footprints tinted.
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.Rendering;

namespace SpongePark
{
    public class TerrainView : MonoBehaviour
    {
        public HeightGrid Grid;
        MeshFilter mf;

        public static TerrainView Create(string name, Transform parent, int layer)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            var t = go.AddComponent<TerrainView>();
            t.mf = go.AddComponent<MeshFilter>();
            go.AddComponent<MeshRenderer>().sharedMaterial = new Material(Shader.Find("SpongePark/VertexLit"));
            return t;
        }

        /// components: GeoJSON FeatureCollection of the option's elements (may be null).
        public void Build(HeightGrid g, SiteFrame frame, JToken components)
        {
            Grid = g;
            var polys = Footprints(components);
            var verts = new List<Vector3>();
            var cols = new List<Color>();
            var index = new int[g.Rows * g.Cols];
            for (int r = 0; r < g.Rows; r++)
            for (int c = 0; c < g.Cols; c++)
            {
                int k = r * g.Cols + c;
                if (!g.Valid(r, c)) { index[k] = -1; continue; }
                float x = g.Origin.x + (c + 0.5f) * g.Cell, y = g.Origin.y - (r + 0.5f) * g.Cell;
                index[k] = verts.Count;
                verts.Add(frame.World(x, y, g.Z[k]));
                float t = Mathf.InverseLerp(g.ZMin, g.ZMax, g.Z[k]);
                var col = Color.Lerp(new Color(0.42f, 0.55f, 0.32f), new Color(0.72f, 0.68f, 0.52f), t);
                // ground beyond the survey levels (widened for display): pale, so it reads as not surveyed
                if (g.Surveyed != null && g.Surveyed[k] == 0) col = Color.Lerp(col, new Color(0.86f, 0.84f, 0.78f), 0.75f);
                foreach (var (type, ring) in polys)
                    if (Inside(ring, x, y)) { col = Color.Lerp(col, TypeColour(type), 0.7f); break; }
                cols.Add(col);
            }
            var tris = new List<int>();
            for (int r = 0; r < g.Rows - 1; r++)
            for (int c = 0; c < g.Cols - 1; c++)
            {
                int a = index[r * g.Cols + c], b = index[r * g.Cols + c + 1];
                int d = index[(r + 1) * g.Cols + c], e = index[(r + 1) * g.Cols + c + 1];
                if (a < 0 || b < 0 || d < 0 || e < 0) continue;
                // rows run north to south (-Z); clockwise seen from above = front face in Unity
                tris.Add(a); tris.Add(b); tris.Add(d);
                tris.Add(b); tris.Add(e); tris.Add(d);
            }
            var m = new Mesh { indexFormat = IndexFormat.UInt32 };
            m.SetVertices(verts);
            m.SetColors(cols);
            m.SetTriangles(tris, 0);
            m.RecalculateNormals();
            m.RecalculateBounds();
            mf.sharedMesh = m;
        }

        public static Color TypeColour(string type) => type switch
        {
            "rain_garden" => new Color(0.0f, 0.51f, 0.0f),
            "bioswale" => new Color(0.1f, 0.69f, 0.48f),
            "recharge_well" => new Color(0.38f, 0.31f, 0.84f),
            _ => new Color(0.16f, 0.47f, 0.84f)
        };

        static List<(string, List<Vector2>)> Footprints(JToken fc)
        {
            var list = new List<(string, List<Vector2>)>();
            if (fc == null) return list;
            foreach (var f in fc["features"])
            {
                var type = (string)f["properties"]["type"];
                var geom = f["geometry"];
                var ring = new List<Vector2>();
                switch ((string)geom["type"])
                {
                    case "Polygon":
                        foreach (var p in geom["coordinates"][0]) ring.Add(new Vector2((float)p[0], (float)p[1]));
                        break;
                    case "LineString":   // swale centreline: a thin band
                    {
                        float w = ((float?)f["properties"]["top_width_m"] ?? 3f) / 2f;
                        var pts = new List<Vector2>();
                        foreach (var p in geom["coordinates"]) pts.Add(new Vector2((float)p[0], (float)p[1]));
                        for (int i = 0; i < pts.Count - 1; i++)
                        {
                            var dir = (pts[i + 1] - pts[i]).normalized;
                            var nrm = new Vector2(-dir.y, dir.x) * w;
                            list.Add((type, new List<Vector2> { pts[i] + nrm, pts[i + 1] + nrm, pts[i + 1] - nrm, pts[i] - nrm }));
                        }
                        continue;
                    }
                    case "Point":
                    {
                        float rad = ((float?)f["properties"]["well_diameter_m"] ?? 1.2f) / 2f;
                        var c = new Vector2((float)geom["coordinates"][0], (float)geom["coordinates"][1]);
                        for (int i = 0; i < 16; i++)
                            ring.Add(c + rad * new Vector2(Mathf.Cos(i * Mathf.PI / 8), Mathf.Sin(i * Mathf.PI / 8)));
                        break;
                    }
                }
                if (ring.Count > 2) list.Add((type, ring));
            }
            return list;
        }

        static bool Inside(List<Vector2> ring, float x, float y)
        {
            bool inside = false;
            for (int i = 0, j = ring.Count - 1; i < ring.Count; j = i++)
                if ((ring[i].y > y) != (ring[j].y > y) &&
                    x < (ring[j].x - ring[i].x) * (y - ring[i].y) / (ring[j].y - ring[i].y) + ring[i].x)
                    inside = !inside;
            return inside;
        }

        /// Ground level (survey m) at a survey point, nearest cell; NaN outside.
        public float GroundAt(float x, float y)
        {
            int c = Mathf.FloorToInt((x - Grid.Origin.x) / Grid.Cell), r = Mathf.FloorToInt((Grid.Origin.y - y) / Grid.Cell);
            if (r < 0 || c < 0 || r >= Grid.Rows || c >= Grid.Cols) return float.NaN;
            return Grid.Z[r * Grid.Cols + c];
        }
    }
}
