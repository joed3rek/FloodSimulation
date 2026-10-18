// Phase 0 acceptance: a project created in Python opens in Unity and round trips without loss.
//   Unity -batchmode -projectPath unity/SpongeParkApp -executeMethod SpongePark.EditorTools.RoundTrip.Run
//         -in project.sponge -out roundtrip.sponge -report report.json -quit
// Opens the package with the C# classes, writes it back to a new file, and reports what it read.
using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using SpongePark.Data;
using UnityEngine;

namespace SpongePark.EditorTools
{
    public static class RoundTrip
    {
        static string Arg(string name)
        {
            var a = Environment.GetCommandLineArgs();
            int i = Array.IndexOf(a, name);
            return i >= 0 && i + 1 < a.Length ? a[i + 1] : null;
        }

        public static void Run()
        {
            var report = Arg("-report") ?? "roundtrip_report.json";
            try
            {
                using var p = SpongePackage.Open(Arg("-in"));
                var read = new
                {
                    ok = true,
                    schema = p.Manifest.SchemaVersion,
                    project = p.Manifest.ProjectName,
                    parameters = p.Parameters.Count,
                    history = p.History.Entries.Count,
                    scenarios = p.Scenarios.ToDictionary(kv => kv.Key, kv => kv.Value.Elements?.Elements?.Count ?? 0),
                    proposals = p.Proposals.Count,
                    terrain_edits = p.TerrainEdits?.Edits?.Count ?? 0,
                    edit_log = p.EditLog?.Entries?.Count ?? 0,
                    first_element = p.Scenarios.Values.SelectMany(s => s.Elements?.Elements ?? new System.Collections.Generic.List<ElementRecord>())
                        .Select(e => new { e.Id, e.Type, geometry = e.Geometry?.Type, depth = e.Parameters?.DepthM, e.Source }).FirstOrDefault(),
                    designer_params = p.Parameters.Count(kv => kv.Value.Source == "designer"),
                };
                p.Save(Arg("-out"), Application.version);
                File.WriteAllText(report, JsonConvert.SerializeObject(read, Formatting.Indented));
                Exit(0);
            }
            catch (Exception ex)
            {
                File.WriteAllText(report, JsonConvert.SerializeObject(new { ok = false, error = ex.ToString() }));
                Debug.LogError(ex);
                Exit(1);
            }
        }

        static void Exit(int code)
        {
#if UNITY_EDITOR
            UnityEditor.EditorApplication.Exit(code);
#endif
        }
    }
}
