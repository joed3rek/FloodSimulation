// Water surface mesh on the 2D model grid: height = ground + depth, colour and opacity by depth.
// Updated on the CPU from replayed engine frames or from the GPU simulation's depth readback, so the
// same renderer works on desktop and WebGL.
using UnityEngine;
using UnityEngine.Rendering;

namespace SpongePark
{
    public class WaterView : MonoBehaviour
    {
        public float showFromDepth = 0.01f;    // m; thinner sheet flow is not drawn
        public float fullColourDepth = 0.3f;   // m
        int rows, cols;
        float[] ground;   // survey m per cell, NaN outside
        Vector3[] verts;
        Color[] colours;
        Vector2[] depths;   // water depth (m) per vertex, for the shader
        Mesh mesh;
        SiteFrame frame;
        float originX, originY, cell;

        public static WaterView Create(string name, Transform parent, int layer)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            var w = go.AddComponent<WaterView>();
            go.AddComponent<MeshFilter>();
            var mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = new Material(Shader.Find("SpongePark/Water"));
            mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            return w;
        }

        public void Build(int rows, int cols, float cell, Vector2 origin, TerrainView terrain, SiteFrame frame)
        {
            this.rows = rows; this.cols = cols; this.cell = cell; this.frame = frame;
            originX = origin.x; originY = origin.y;
            ground = new float[rows * cols];
            verts = new Vector3[rows * cols];
            colours = new Color[rows * cols];
            depths = new Vector2[rows * cols];
            var tris = new System.Collections.Generic.List<int>();
            for (int r = 0; r < rows; r++)
            for (int c = 0; c < cols; c++)
            {
                int k = r * cols + c;
                float x = originX + (c + 0.5f) * cell, y = originY - (r + 0.5f) * cell;
                ground[k] = terrain.GroundAt(x, y);
                verts[k] = frame.World(x, y, float.IsNaN(ground[k]) ? frame.ZRef : ground[k]);
                if (r < rows - 1 && c < cols - 1)
                {
                    int b = k + 1, d = k + cols, e = k + cols + 1;
                    tris.Add(k); tris.Add(b); tris.Add(d);
                    tris.Add(b); tris.Add(e); tris.Add(d);
                }
            }
            mesh = new Mesh { indexFormat = IndexFormat.UInt32 };
            mesh.MarkDynamic();
            mesh.vertices = verts;
            mesh.colors = colours;
            mesh.SetTriangles(tris, 0);
            mesh.RecalculateBounds();
            GetComponent<MeshFilter>().sharedMesh = mesh;
        }

        float[] shown;   // the depths last shown (m)

        /// Water depth (m) at a survey point, as last shown; NaN outside the grid or before any water.
        public float DepthAt(float x, float y)
        {
            if (shown == null) return float.NaN;
            int c = Mathf.FloorToInt((x - originX) / cell), r = Mathf.FloorToInt((originY - y) / cell);
            if (r < 0 || c < 0 || r >= rows || c >= cols) return float.NaN;
            return shown[r * cols + c];
        }

        public void Show(float[] depth)
        {
            if (mesh == null) return;
            shown = depth;
            var shallow = new Color(0.55f, 0.78f, 0.95f, 0f);
            var deep = new Color(0.08f, 0.32f, 0.72f, 0.85f);
            for (int k = 0; k < verts.Length; k++)
            {
                float g = ground[k];
                float d = depth[k];
                if (float.IsNaN(g) || d < showFromDepth)
                {
                    colours[k] = shallow;
                    depths[k] = Vector2.zero;
                    verts[k].y = float.IsNaN(g) ? 0f : (g - frame.ZRef) * frame.Exaggeration - 0.02f;
                    continue;
                }
                verts[k].y = (g + d - frame.ZRef) * frame.Exaggeration + 0.01f;
                var t = Mathf.Clamp01(d / fullColourDepth);
                var col = Color.Lerp(new Color(0.55f, 0.78f, 0.95f, 0.45f), deep, t);
                colours[k] = col;
                depths[k] = new Vector2(d, 0);
            }
            mesh.vertices = verts;
            mesh.colors = colours;
            mesh.uv = depths;
            mesh.RecalculateNormals();
        }
    }
}
