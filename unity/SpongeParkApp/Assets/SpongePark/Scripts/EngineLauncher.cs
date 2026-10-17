// Starts the Python engine API (spongepark serve) as a child process on desktop builds, so a
// non-technical user only opens the app. Python and the engine must be installed (see unity/README.md).
using System;
using System.Diagnostics;
using UnityEngine;

namespace SpongePark
{
    public class EngineLauncher : MonoBehaviour
    {
        public string PythonExe = "python";   // or the full path to the engine's virtual environment python
        public string WorkingDir = "";
        Process proc;
        public string Message = "";

        public bool Launch()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            Message = "the WebGL viewer cannot start the engine";
            return false;
#else
            try
            {
                proc = Process.Start(new ProcessStartInfo
                {
                    FileName = PythonExe,
                    Arguments = "-m spongepark.cli.main serve",
                    WorkingDirectory = string.IsNullOrEmpty(WorkingDir) ? Environment.CurrentDirectory : WorkingDir,
                    UseShellExecute = false, CreateNoWindow = true
                });
                Message = "engine starting...";
                return true;
            }
            catch (Exception ex)
            {
                Message = "could not start the engine: " + ex.Message;
                return false;
            }
#endif
        }

        void OnApplicationQuit()
        {
            try { if (proc != null && !proc.HasExited) proc.Kill(); } catch (Exception) { }
        }
    }
}
