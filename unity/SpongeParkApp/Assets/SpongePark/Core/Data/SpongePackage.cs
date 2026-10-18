// Reading and writing the .sponge project package in C#, against the shared schema
// (schema/sponge.schema.json -> SpongeSchema.g.cs). The modelled JSON files are loaded into typed
// classes; every other file (rasters, GeoJSON, SWMM models, results) is carried through untouched.
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using Newtonsoft.Json;

namespace SpongePark.Data
{
    public class ScenarioData
    {
        public Scenario Info;
        public ElementsFile Elements;
    }

    public class SpongePackage : IDisposable
    {
        public string PackagePath { get; private set; }
        public string Root { get; private set; }
        public Manifest Manifest;
        public Dictionary<string, ParameterRecord> Parameters;
        public History History;
        public Locks Locks;
        public EditLog EditLog;
        public TerrainEdits TerrainEdits;
        public readonly Dictionary<string, ScenarioData> Scenarios = new Dictionary<string, ScenarioData>();
        public readonly Dictionary<string, Proposal> Proposals = new Dictionary<string, Proposal>();

        static readonly JsonSerializerSettings Settings = new JsonSerializerSettings
        {
            NullValueHandling = NullValueHandling.Ignore,
            Formatting = Formatting.Indented,
            FloatParseHandling = FloatParseHandling.Double,
            DateParseHandling = DateParseHandling.None,   // dates stay the strings they were written as
        };

        /// Opens a .sponge file (unzipped to a private folder) or a project folder.
        public static SpongePackage Open(string path)
        {
            var p = new SpongePackage();
            if (Directory.Exists(path)) { p.Root = path; p.PackagePath = null; }
            else
            {
                p.PackagePath = path;
                p.Root = Path.Combine(Path.GetTempPath(), "sponge_cs_" + Guid.NewGuid().ToString("N").Substring(0, 8));
                ZipFile.ExtractToDirectory(path, p.Root);
            }
            p.Manifest = p.Read<Manifest>("manifest.json");
            var major = (p.Manifest?.SchemaVersion ?? "0").Split('.')[0];
            if (major != SchemaInfo.Version.Split('.')[0])
                throw new InvalidDataException($"project schema {p.Manifest?.SchemaVersion} is not readable by this app (schema {SchemaInfo.Version}); open it once with the engine to upgrade it.");
            p.Parameters = p.Read<Dictionary<string, ParameterRecord>>("parameters.json");
            p.History = p.Read<History>("history.json");
            p.Locks = p.Read<Locks>("locks.json");
            p.EditLog = p.Read<EditLog>("edit_log.json");
            p.TerrainEdits = p.Read<TerrainEdits>("terrain/edits.json");
            var sc = Path.Combine(p.Root, "scenarios");
            if (Directory.Exists(sc))
                foreach (var d in Directory.GetDirectories(sc).OrderBy(x => x))
                {
                    var id = Path.GetFileName(d);
                    p.Scenarios[id] = new ScenarioData
                    {
                        Info = p.Read<Scenario>($"scenarios/{id}/scenario.json"),
                        Elements = p.Read<ElementsFile>($"scenarios/{id}/elements.json"),
                    };
                }
            var pr = Path.Combine(p.Root, "proposals");
            if (Directory.Exists(pr))
                foreach (var f in Directory.GetFiles(pr, "*.json").OrderBy(x => x))
                    p.Proposals[Path.GetFileNameWithoutExtension(f)] = p.Read<Proposal>($"proposals/{Path.GetFileName(f)}");
            return p;
        }

        T Read<T>(string rel) where T : class
        {
            var f = Path.Combine(Root, rel.Replace('/', Path.DirectorySeparatorChar));
            return File.Exists(f) ? JsonConvert.DeserializeObject<T>(File.ReadAllText(f), Settings) : null;
        }

        void Write<T>(string rel, T value) where T : class
        {
            if (value == null) return;
            var f = Path.Combine(Root, rel.Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(f));
            File.WriteAllText(f, JsonConvert.SerializeObject(value, Settings));
        }

        /// Writes the modelled files back and packs the project (to its own file, or to saveAs).
        public string Save(string saveAs = null, string appVersion = null)
        {
            if (Manifest != null)
            {
                Manifest.Modified = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ss+00:00");
                if (appVersion != null) Manifest.AppVersion = appVersion;
            }
            Write("manifest.json", Manifest);
            Write("parameters.json", Parameters);
            Write("history.json", History);
            Write("locks.json", Locks);
            Write("edit_log.json", EditLog);
            Write("terrain/edits.json", TerrainEdits);
            foreach (var kv in Scenarios)
            {
                Write($"scenarios/{kv.Key}/scenario.json", kv.Value.Info);
                Write($"scenarios/{kv.Key}/elements.json", kv.Value.Elements);
            }
            foreach (var kv in Proposals) Write($"proposals/{kv.Key}.json", kv.Value);
            var target = saveAs ?? PackagePath;
            if (target == null) return Root;   // a folder project is edited in place
            var tmp = target + ".tmp";
            if (File.Exists(tmp)) File.Delete(tmp);
            using (var zip = ZipFile.Open(tmp, ZipArchiveMode.Create))
                foreach (var f in Directory.GetFiles(Root, "*", SearchOption.AllDirectories).OrderBy(x => x, StringComparer.Ordinal))
                {
                    // entry names always use '/', whatever the platform
                    var rel = f.Substring(Root.Length).TrimStart(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar).Replace('\\', '/');
                    zip.CreateEntryFromFile(f, rel, CompressionLevel.Optimal);
                }
            if (File.Exists(target)) File.Delete(target);
            File.Move(tmp, target);
            return target;
        }

        public void Dispose()
        {
            if (PackagePath != null && Root != null && Directory.Exists(Root))
                try { Directory.Delete(Root, true); } catch (IOException) { }
        }
    }
}
