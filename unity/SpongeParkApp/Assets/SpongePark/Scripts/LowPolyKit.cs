// The low-poly art the app places, when the packs have been taken in (spongepark unity lowpoly-assets): the editor
// lists the pieces in Resources/LowPoly/LowPolyKit.asset (Sponge Park > List low-poly art, and every build).
// Without it the app draws its own models. Every placed piece is drawn with the app's own low-poly shader (the
// pack's palette texture in the app's light), so the packs need no render pipeline or Shader Graph of their own.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace SpongePark
{
    public class LowPolyKit : ScriptableObject
    {
        public GameObject[] trees, palms, bushes, grass, flowers, rocks, lilypads;
        public GameObject manhole, skyDome;
        // each pack material and the app's low-poly material made from it in the editor (the packs' own shaders,
        // e.g. Synty's Shader Graphs, are not in this project, so their textures can only be read there)
        public Material[] sourceMaterials, lowPolyMaterials;

        static LowPolyKit loaded;
        static bool tried;
        static readonly Dictionary<Material, Material> converted = new Dictionary<Material, Material>();
        static readonly Dictionary<GameObject, Bounds> sizes = new Dictionary<GameObject, Bounds>();

        public static LowPolyKit Kit
        {
            get
            {
                if (!tried)
                {
                    tried = true;
                    loaded = Resources.Load<LowPolyKit>("LowPoly/LowPolyKit");
                }
                return loaded;
            }
        }

        public static bool Has(GameObject[] set) => set != null && set.Length > 0;

        /// One piece of a set, picked by seed, standing at p and turned by the seed.
        /// size: the width (m) it should have across (0 keeps the pack's own size).
        /// vary: a little bigger or smaller by the seed (not for trees: they are all the same size).
        /// height: the height (m) it should have (0 keeps its proportions).
        public static GameObject Place(GameObject[] set, Vector3 p, float size, int seed, Transform parent, int layer,
                                       bool vary = true, float height = 0)
        {
            var prefab = set[Mathf.Abs(seed) % set.Length];
            return Place(prefab, p, size, seed, parent, layer, vary, height);
        }

        public static GameObject Place(GameObject prefab, Vector3 p, float size, int seed, Transform parent, int layer,
                                       bool vary = true, float height = 0)
        {
            var go = Instantiate(prefab, parent);
            float s = 1;
            if (size > 0)
            {
                var b = Size(prefab);
                s = size / Mathf.Max(0.1f, Mathf.Max(b.size.x, b.size.z));
            }
            if (vary) s *= 0.92f + 0.16f * ((Mathf.Abs(seed) * 13) % 100) / 100f;
            go.transform.SetPositionAndRotation(p, Quaternion.Euler(0, (Mathf.Abs(seed) * 47) % 360, 0));
            var scale = prefab.transform.localScale * s;
            if (height > 0)   // taller or lower than its own proportions
                scale.y = prefab.transform.localScale.y * height / Mathf.Max(0.1f, Size(prefab).size.y);
            go.transform.localScale = scale;
            Prepare(go, layer);
            return go;
        }

        /// The app's layer, its low-poly shader and shadows on every part of a placed piece; no colliders.
        public static void Prepare(GameObject go, int layer)
        {
            foreach (var t in go.GetComponentsInChildren<Transform>(true)) t.gameObject.layer = layer;
            foreach (var c in go.GetComponentsInChildren<Collider>(true))
                if (Application.isPlaying) Destroy(c); else DestroyImmediate(c);
            foreach (var r in go.GetComponentsInChildren<Renderer>(true))
            {
                var mats = r.sharedMaterials;
                for (int i = 0; i < mats.Length; i++) mats[i] = Convert(mats[i]);
                r.sharedMaterials = mats;
                r.shadowCastingMode = ShadowCastingMode.On;
                r.receiveShadows = true;
            }
        }

        /// The pack material as the app's low-poly material: its palette texture, tint and cut-out kept.
        static Material Convert(Material src)
        {
            if (src == null) return null;
            if (converted.TryGetValue(src, out var m)) return m;
            var kit = Kit;
            if (kit != null && kit.sourceMaterials != null)
            {
                int i = System.Array.IndexOf(kit.sourceMaterials, src);
                if (i >= 0 && i < kit.lowPolyMaterials.Length && kit.lowPolyMaterials[i] != null)
                    return converted[src] = kit.lowPolyMaterials[i];
            }
            return converted[src] = src;   // a material whose shader is in the project (e.g. Unity's tree shaders): kept
        }

        /// The prefab's size (its meshes' bounds in its own space).
        public static Bounds Size(GameObject prefab)
        {
            if (sizes.TryGetValue(prefab, out var b)) return b;
            bool any = false;
            foreach (var mf in prefab.GetComponentsInChildren<MeshFilter>(true))
            {
                if (mf.sharedMesh == null) continue;
                var mb = mf.sharedMesh.bounds;
                var m = mf.transform.localToWorldMatrix;   // prefab space (root at the origin)
                var c = m.MultiplyPoint3x4(mb.center);
                var e = mb.extents;
                var ext = new Vector3(
                    Mathf.Abs(m.m00) * e.x + Mathf.Abs(m.m01) * e.y + Mathf.Abs(m.m02) * e.z,
                    Mathf.Abs(m.m10) * e.x + Mathf.Abs(m.m11) * e.y + Mathf.Abs(m.m12) * e.z,
                    Mathf.Abs(m.m20) * e.x + Mathf.Abs(m.m21) * e.y + Mathf.Abs(m.m22) * e.z);
                var wb = new Bounds(c, ext * 2);
                if (!any) { b = wb; any = true; } else b.Encapsulate(wb);
            }
            if (!any) b = new Bounds(Vector3.zero, Vector3.one);
            sizes[prefab] = b;
            return b;
        }
    }
}
