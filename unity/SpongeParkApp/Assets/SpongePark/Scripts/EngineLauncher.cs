// Starts the Python engine API (spongepark serve) as a child process on desktop builds, so a
// non-technical user only opens the app. Python and the engine must be installed (see unity/README.md).
using System;
using System.Diagnostics;
using System.IO;
using UnityEngine;

namespace SpongePark
{
    public class EngineLauncher : MonoBehaviour
    {
        public string PythonExe = "";   // empty: the engine checkout's .venv python if one is found, else "python"
        public string WorkingDir = "";  // empty: the engine checkout if one is found, else the current directory
        Process proc;
        string message = "";

        /// Why the engine is not up; starts with "could not" once the engine has failed.
        public string Message => proc != null && proc.HasExited
            ? $"could not start the engine: {proc.StartInfo.FileName} stopped (exit code {proc.ExitCode}); run spongepark serve in a terminal to see why"
            : message;

        public bool Launch()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            message = "the WebGL viewer cannot start the engine";
            return false;
#else
            var root = FindEngineRoot();
            var venvPy = root == null ? null : Path.Combine(root, ".venv", "Scripts", "python.exe");
            if (venvPy != null && !File.Exists(venvPy)) venvPy = Path.Combine(root, ".venv", "bin", "python");
            var exe = !string.IsNullOrEmpty(PythonExe) ? PythonExe : venvPy != null && File.Exists(venvPy) ? venvPy : "python";
            var dir = !string.IsNullOrEmpty(WorkingDir) ? WorkingDir : root ?? Environment.CurrentDirectory;
            try
            {
                // output is not redirected: uvicorn logs every request, and a pipe the app stops reading
                // blocks the engine mid-request (health checks then time out)
                proc = Process.Start(new ProcessStartInfo
                {
                    FileName = exe,
                    Arguments = "-m spongepark.cli.main serve",
                    WorkingDirectory = dir,
                    UseShellExecute = false, CreateNoWindow = true
                });
                message = "engine starting...";
                UnityEngine.Debug.Log($"engine: {exe} -m spongepark.cli.main serve (in {dir})");
                return true;
            }
            catch (Exception ex)
            {
                message = "could not start the engine: " + ex.Message;
                return false;
            }
#endif
        }

        /// The engine checkout (has pyproject.toml and the spongepark package), searched upwards from the
        /// app's data folder and the current directory; null if none.
        static string FindEngineRoot()
        {
            foreach (var start in new[] { Application.dataPath, Environment.CurrentDirectory })
            {
                for (var d = new DirectoryInfo(start); d != null; d = d.Parent)
                    if (File.Exists(Path.Combine(d.FullName, "pyproject.toml")) && Directory.Exists(Path.Combine(d.FullName, "spongepark")))
                        return d.FullName;
            }
            return null;
        }

        void OnApplicationQuit()
        {
            if (proc == null || proc.HasExited) return;
            // a venv's python.exe is a launcher that starts the real interpreter: end the whole tree
            try
            {
                if (Application.platform == RuntimePlatform.WindowsPlayer || Application.platform == RuntimePlatform.WindowsEditor)
                    Process.Start(new ProcessStartInfo("taskkill", $"/T /F /PID {proc.Id}") { UseShellExecute = false, CreateNoWindow = true })?.WaitForExit(3000);
                else proc.Kill();
            }
            catch (Exception) { }
        }
    }
}
