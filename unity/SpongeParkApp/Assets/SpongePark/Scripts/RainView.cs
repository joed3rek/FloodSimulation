// Falling rain in front of one camera, as thick as the storm is at that moment (mm/h). The streaks are moved
// by the Rain shader; this only places the box in front of the camera and sets how many streaks show.
using UnityEngine;
using UnityEngine.Rendering;

namespace SpongePark
{
    public class RainView : MonoBehaviour
    {
        const int Streaks = 16000;
        Material material;
        Camera cam;

        public static RainView Create(string name, Transform parent, int layer, Camera cam)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            var v = go.AddComponent<RainView>();
            v.cam = cam;
            v.material = new Material(Shader.Find("SpongePark/Rain"));
            var mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = v.material;
            mr.shadowCastingMode = ShadowCastingMode.Off;
            mr.receiveShadows = false;
            go.AddComponent<MeshFilter>().sharedMesh = Streak();
            return v;
        }

        static Mesh Streak()
        {
            var rnd = new System.Random(7);
            var pos = new Vector3[Streaks * 4];
            var corner = new Vector2[Streaks * 4];
            var id = new Vector2[Streaks * 4];
            var tris = new int[Streaks * 6];
            for (int i = 0; i < Streaks; i++)
            {
                var p = new Vector3((float)rnd.NextDouble(), (float)rnd.NextDouble(), (float)rnd.NextDouble());
                float k = (float)rnd.NextDouble();
                for (int j = 0; j < 4; j++)
                {
                    pos[i * 4 + j] = p;
                    id[i * 4 + j] = new Vector2(k, 0);
                }
                corner[i * 4] = new Vector2(-1, 0);
                corner[i * 4 + 1] = new Vector2(1, 0);
                corner[i * 4 + 2] = new Vector2(1, 1);
                corner[i * 4 + 3] = new Vector2(-1, 1);
                int b = i * 4, t = i * 6;
                tris[t] = b; tris[t + 1] = b + 1; tris[t + 2] = b + 2;
                tris[t + 3] = b; tris[t + 4] = b + 2; tris[t + 5] = b + 3;
            }
            var m = new Mesh { indexFormat = IndexFormat.UInt32, vertices = pos, uv = corner, uv2 = id, triangles = tris };
            m.bounds = new Bounds(Vector3.zero, Vector3.one * 1e6f);   // moved in the shader: never culled
            return m;
        }

        /// rate: rainfall now (mm/h); 0 hides the rain. distance: the camera's distance to what it looks at (m).
        public void Show(float rate, float distance)
        {
            bool on = rate > 0.05f && cam != null && cam.enabled;
            gameObject.SetActive(on);
            if (!on) return;
            // the box sits between the camera and the ground it looks at, sized to the view
            float size = Mathf.Clamp(distance * 0.55f, 18f, 260f);
            var centre = cam.transform.position + cam.transform.forward * size * 0.55f;
            material.SetVector("_BoxCentre", centre);
            material.SetVector("_BoxSize", new Vector3(size, size * 0.8f, size));
            material.SetVector("_Wind", new Vector3(0.12f, 0, 0.05f));
            // light rain a sparse drizzle, a downpour (about 60 mm/h and more) the full box
            material.SetFloat("_Density", Mathf.Clamp01(0.04f + (rate / 80f) * 0.96f));
            material.SetFloat("_StreakLength", size * 0.017f);
            material.SetFloat("_StreakWidth", size * 0.0009f);
            material.SetFloat("_FallSpeed", Mathf.Max(9f, size * 0.12f));
        }
    }
}
