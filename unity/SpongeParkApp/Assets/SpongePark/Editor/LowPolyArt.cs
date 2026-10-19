// Lists the low-poly art the app places (taken in by `spongepark unity lowpoly-assets`) in
// Resources/LowPoly/LowPolyKit.asset. Builds call it; also Sponge Park > List low-poly art.
// Preview renders the candidate pieces side by side into a PNG, to choose them by eye:
//   Unity -batchmode -quit -projectPath ... -executeMethod SpongePark.EditorTools.LowPolyArt.Preview -spOut out.png -spSet trees
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace SpongePark.EditorTools
{
    /// In the editor: list the art once scripts load (when the packs are in).
    [InitializeOnLoad]
    static class LowPolyAutoList
    {
        static LowPolyAutoList()
        {
            EditorApplication.delayCall += () =>
            {
                if (Application.isBatchMode || EditorApplication.isPlayingOrWillChangePlaymode) return;
                LowPolyArt.List();   // the kit follows the packs and this list (cheap)
            };
        }
    }

    public static class LowPolyArt
    {
        const string KitPath = "Assets/SpongePark/Resources/LowPoly/LowPolyKit.asset";
        const string Synty = "Assets/Synty/PolygonGeneric/Prefabs/Environment/";
        const string SyntyProps = "Assets/Synty/PolygonGeneric/Prefabs/Props/";
        const string Starter = "Assets/Synty/PolygonStarter/Prefabs/";
        const string Nature = "Assets/SimpleNaturePack/Prefabs/";
        const string Trees = "Assets/BrokenVector/LowPolyTreePack/Prefabs/";
        const string Tree9 = "Assets/Tree9/";
        // the low-poly bushes, grass, flowers, rocks, palms and sky dome: off (the designer chose the app's own trees)
        const bool LowPolyExtras = false;

        // broadleaf, wide-crowned trees only (Bengaluru's park trees are deciduous: rain trees and the like; no pines)
        static readonly string[] TreeNames =
        {
            // none: the app draws its own trees (a round broadleaf crown, all the same size)
        };
        static readonly string[] PalmNames = { Trees + "Tree Type7 02", Trees + "Tree Type7 03", Trees + "Tree Type7 04" };
        static readonly string[] BushNames =
        {
            Synty + "SM_Gen_Env_Bush_01", Synty + "SM_Gen_Env_Bush_02", Synty + "SM_Gen_Env_Bush_03", Synty + "SM_Gen_Env_Bush_04",
            Nature + "Bush_01", Nature + "Bush_02",
        };
        static readonly string[] GrassNames =
        {
            Synty + "SM_Gen_Env_Grass_01", Synty + "SM_Gen_Env_Grass_02", Synty + "SM_Gen_Env_Grass_03",
            Nature + "Grass_01", Nature + "Grass_02",
        };
        static readonly string[] FlowerNames =
        {
            Synty + "SM_Gen_Env_Flowers_01", Synty + "SM_Gen_Env_Flowers_02", Synty + "SM_Gen_Env_Flowers_03",
            Nature + "Flowers_01", Nature + "Flowers_02",
        };
        static readonly string[] RockNames =
        {
            Starter + "SM_Generic_Small_Rocks_01", Starter + "SM_Generic_Small_Rocks_02", Starter + "SM_Generic_Small_Rocks_03",
            Nature + "Rock_01", Nature + "Rock_02", Nature + "Rock_03",
        };
        static readonly string[] LilypadNames = { Synty + "SM_Gen_Env_Lilypads_01", Synty + "SM_Gen_Env_Lilypads_02", Synty + "SM_Gen_Env_Lilypads_03" };

        static GameObject Load(string path)
        {
            var go = AssetDatabase.LoadAssetAtPath<GameObject>(path + ".prefab");
            return go != null && go.GetComponent<Tree>() != null ? BakeTree(path + ".prefab") : go;
        }

        /// A Tree Creator tree (Realistic Tree 9) keeps its mesh and materials inside its prefab without its renderer
        /// pointing to them (Unity's tree editor regenerates them): a ready prefab assembled from those parts.
        static GameObject BakeTree(string path)
        {
            Mesh mesh = null;
            Material bark = null, leaf = null;
            foreach (var o in AssetDatabase.LoadAllAssetsAtPath(path))
            {
                if (o is Mesh m) mesh = m;
                if (o is Material mat && mat.name.Contains("Bark")) bark = mat;
                if (o is Material mat2 && mat2.name.Contains("Leaf")) leaf = mat2;
            }
            if (mesh == null) return null;
            const string folder = "Assets/SpongePark/Resources/LowPoly/Trees";
            Directory.CreateDirectory(folder);
            var go = new GameObject(Path.GetFileNameWithoutExtension(path));
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mats = mesh.subMeshCount >= 2 ? new[] { bark, leaf } : new[] { leaf ?? bark };
            go.AddComponent<MeshRenderer>().sharedMaterials = mats;
            var baked = PrefabUtility.SaveAsPrefabAsset(go, $"{folder}/{go.name}.prefab");
            Object.DestroyImmediate(go);
            Debug.Log($"Tree baked: {baked.name}, {mesh.vertexCount} vertices, {mesh.subMeshCount} parts, " +
                      $"materials {bark?.shader?.name} / {leaf?.shader?.name}, size {mesh.bounds.size}");
            return baked;
        }
        static GameObject[] LoadAll(IEnumerable<string> paths) => paths.Select(Load).Where(g => g != null).ToArray();

        [MenuItem("Sponge Park/List low-poly art")]
        public static void Menu() => List();

        /// Writes the kit when the packs are in the project; returns false (and leaves no kit) when they are not.
        public static bool List()
        {
            var trees = LoadAll(TreeNames);
            if (Load(SyntyProps + "SM_Gen_Prop_Manhole_01") == null) { Debug.Log("Low-poly art: the packs are not in the project (spongepark unity lowpoly-assets)."); return false; }
            Directory.CreateDirectory(Path.GetDirectoryName(KitPath));
            var kit = AssetDatabase.LoadAssetAtPath<LowPolyKit>(KitPath);
            if (kit == null)
            {
                kit = ScriptableObject.CreateInstance<LowPolyKit>();
                AssetDatabase.CreateAsset(kit, KitPath);
            }
            kit.trees = trees;
            kit.palms = LowPolyExtras ? LoadAll(PalmNames) : new GameObject[0];
            kit.bushes = LowPolyExtras ? LoadAll(BushNames) : new GameObject[0];
            kit.grass = LowPolyExtras ? LoadAll(GrassNames) : new GameObject[0];
            kit.flowers = LowPolyExtras ? LoadAll(FlowerNames) : new GameObject[0];
            kit.rocks = LowPolyExtras ? LoadAll(RockNames) : new GameObject[0];
            kit.lilypads = LowPolyExtras ? LoadAll(LilypadNames) : new GameObject[0];
            kit.manhole = Load(SyntyProps + "SM_Gen_Prop_Manhole_01");
            kit.skyDome = LowPolyExtras ? Load(Starter + "SM_SimpleSky_Dome_01") : null;
            ConvertMaterials(kit);
            EditorUtility.SetDirty(kit);
            AssetDatabase.SaveAssets();
            Debug.Log($"Low-poly art listed: {kit.trees.Length} trees, {kit.bushes.Length} bushes, {kit.grass.Length} grass, " +
                      $"{kit.flowers.Length} flowers, {kit.rocks.Length} rocks, {kit.lilypads.Length} lily pads, " +
                      $"manhole {(kit.manhole != null ? "yes" : "no")}, sky dome {(kit.skyDome != null ? "yes" : "no")}");
            return true;
        }

        /// The app's low-poly material for every pack material the kit uses: the texture, tint and cut-out read from
        /// the material's saved properties (its own shader may not be in the project).
        static void ConvertMaterials(LowPolyKit kit)
        {
            const string folder = "Assets/SpongePark/Resources/LowPoly/Materials";
            Directory.CreateDirectory(folder);
            var prefabs = new List<GameObject>();
            foreach (var set in new[] { kit.trees, kit.palms, kit.bushes, kit.grass, kit.flowers, kit.rocks, kit.lilypads })
                if (set != null) prefabs.AddRange(set);
            prefabs.Add(kit.manhole);
            prefabs.Add(kit.skyDome);
            var src = prefabs.Where(p => p != null).SelectMany(p => p.GetComponentsInChildren<Renderer>(true))
                             .SelectMany(r => r.sharedMaterials).Where(m => m != null).Distinct().ToList();
            var shader = Shader.Find("SpongePark/LowPolyTex");
            var made = new List<Material>();
            foreach (var m in src)
            {
                var path = $"{folder}/{m.name}.mat";
                var low = AssetDatabase.LoadAssetAtPath<Material>(path);
                if (low == null) { low = new Material(shader); AssetDatabase.CreateAsset(low, path); }
                low.shader = shader;
                var so = new SerializedObject(m);
                Texture tex = null;
                Color tint = Color.white;
                float clip = 0;
                foreach (SerializedProperty e in so.FindProperty("m_SavedProperties.m_TexEnvs"))
                {
                    var name = e.FindPropertyRelative("first").stringValue;
                    var t = e.FindPropertyRelative("second.m_Texture").objectReferenceValue as Texture;
                    if (t != null && (name == "_Albedo_Map" || name == "_BaseMap" || name == "_MainTex" || name == "_Albedo") && tex == null) tex = t;
                }
                foreach (SerializedProperty e in so.FindProperty("m_SavedProperties.m_Colors"))
                {
                    var name = e.FindPropertyRelative("first").stringValue;
                    if (name == "_Color" || name == "_BaseColor") tint = e.FindPropertyRelative("second").colorValue;
                }
                foreach (SerializedProperty e in so.FindProperty("m_SavedProperties.m_Floats"))
                {
                    var name = e.FindPropertyRelative("first").stringValue;
                    float v = e.FindPropertyRelative("second").floatValue;
                    if ((name == "_AlphaClip" && v > 0.5f) || (name == "_Mode" && Mathf.Approximately(v, 1))) clip = 1;
                }
                low.SetTexture("_MainTex", tex);
                low.SetColor("_Color", tint);
                low.SetFloat("_Clip", clip);
                low.enableInstancing = true;
                EditorUtility.SetDirty(low);
                made.Add(low);
            }
            kit.sourceMaterials = src.ToArray();
            kit.lowPolyMaterials = made.ToArray();
        }

        // ------------------------------------------------------------ preview (choosing pieces by eye)
        static string Arg(string name)
        {
            var a = System.Environment.GetCommandLineArgs();
            int i = System.Array.IndexOf(a, name);
            return i >= 0 && i + 1 < a.Length ? a[i + 1] : null;
        }

        public static void Preview()
        {
            List();   // the app's materials for the pack's pieces
            var set = Arg("-spSet") ?? "trees";
            var out_ = Arg("-spOut") ?? "preview.png";
            IEnumerable<string> paths = set switch
            {
                "tree9" => AssetDatabase.FindAssets("t:Prefab", new[] { "Assets/Tree9" }).Select(AssetDatabase.GUIDToAssetPath),
                "trees" => AssetDatabase.FindAssets("t:Prefab", new[] { "Assets/BrokenVector", "Assets/SimpleNaturePack" })
                    .Select(AssetDatabase.GUIDToAssetPath).Where(p => p.Contains("Tree"))
                    .Concat(new[] { Synty + "SM_Gen_Env_Tree_01.prefab", Synty + "SM_Gen_Env_Tree_02.prefab", Synty + "SM_Gen_Env_Tree_03.prefab",
                                    Starter + "SM_Generic_Tree_01.prefab", Starter + "SM_Generic_Tree_02.prefab", Starter + "SM_Generic_Tree_03.prefab", Starter + "SM_Generic_Tree_04.prefab" }),
                _ => AssetDatabase.FindAssets("t:Prefab", new[] { "Assets/SimpleNaturePack", "Assets/Synty/PolygonGeneric/Prefabs/Environment" })
                    .Select(AssetDatabase.GUIDToAssetPath).Where(p => p.Contains(set, System.StringComparison.OrdinalIgnoreCase)),
            };
            var list = paths.Select(p => (p, g: AssetDatabase.LoadAssetAtPath<GameObject>(p))).Where(x => x.g != null).ToList();
            const int cell = 220, cols = 8;
            int rows = Mathf.Max(1, (list.Count + cols - 1) / cols);
            var sheet = new Texture2D(cell * cols, cell * rows, TextureFormat.RGB24, false);
            var rt = new RenderTexture(cell, cell, 24);
            var camGo = new GameObject("preview camera");
            var cam = camGo.AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.93f, 0.92f, 0.88f);
            cam.targetTexture = rt;
            var light = new GameObject("sun").AddComponent<Light>();
            light.type = LightType.Directional;
            light.transform.rotation = Quaternion.Euler(40, -30, 0);
            for (int i = 0; i < list.Count; i++)
            {
                var go = Object.Instantiate(list[i].g);
                LowPolyKit.Prepare(go, 0);
                var b = new Bounds(go.transform.position, Vector3.zero);
                foreach (var r in go.GetComponentsInChildren<Renderer>()) b.Encapsulate(r.bounds);
                float d = b.extents.magnitude * 2.6f;
                cam.transform.position = b.center + new Vector3(0.6f, 0.35f, -0.75f).normalized * d;
                cam.transform.LookAt(b.center);
                cam.Render();
                RenderTexture.active = rt;
                sheet.ReadPixels(new Rect(0, 0, cell, cell), (i % cols) * cell, (rows - 1 - i / cols) * cell);
                RenderTexture.active = null;
                Object.DestroyImmediate(go);
                Debug.Log($"preview {i}: {list[i].p} size {b.size.x:0.0} x {b.size.y:0.0} x {b.size.z:0.0}");
            }
            sheet.Apply();
            File.WriteAllBytes(out_, sheet.EncodeToPNG());
            EditorApplication.Exit(0);
        }
    }
}
