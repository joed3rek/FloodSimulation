// Batch builds:
//   Unity -batchmode -quit -projectPath unity/SpongeParkApp -executeMethod SpongePark.EditorTools.BuildApp.Windows
//   ... -executeMethod SpongePark.EditorTools.BuildApp.MacOS     (needs the macOS build module)
//   ... -executeMethod SpongePark.EditorTools.BuildApp.WebGL     (results viewer; needs the WebGL module)
// The app builds itself at runtime (Bootstrap), so the scene is empty.
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace SpongePark.EditorTools
{
    public static class BuildApp
    {
        const string Scene = "Assets/Scenes/Main.unity";

        static string[] EnsureScene()
        {
            if (!File.Exists(Scene))
            {
                Directory.CreateDirectory("Assets/Scenes");
                var s = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                EditorSceneManager.SaveScene(s, Scene);
            }
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(Scene, true) };
            LowPolyArt.List();   // the low-poly art the app places, when the packs are in the project
            PlayerSettings.productName = "Sponge Park";
            PlayerSettings.companyName = "Habitat Collective";
            return new[] { Scene };
        }

        static void Build(BuildTarget target, string path)
        {
            var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = EnsureScene(), locationPathName = path, target = target, options = BuildOptions.None
            });
            Debug.Log($"Build {target}: {report.summary.result}, {report.summary.totalErrors} errors, {report.summary.outputPath}");
            EditorApplication.Exit(report.summary.result == BuildResult.Succeeded ? 0 : 1);
        }

        public static void Windows() => Build(BuildTarget.StandaloneWindows64, "Builds/Windows/SpongePark.exe");
        public static void MacOS() => Build(BuildTarget.StandaloneOSX, "Builds/macOS/SpongePark.app");
        public static void WebGL() => Build(BuildTarget.WebGL, "Builds/WebGL");
    }
}
