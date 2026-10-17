// Batch-mode verification of the GPU water simulation against the engine:
//   Unity -batchmode -projectPath unity/SpongeParkApp -executeMethod SpongePark.EditorTools.BatchVerify.Run
//         -inputs <sim2d inputs JSON> -out <result JSON> -quit
// Runs WaterSim.compute on the engine's inputs exactly as the engine steps (maximum depth every step)
// and writes the water balance and final depths, which tests/test_unity_gpu.py compares with the engine.
using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SpongePark.EditorTools
{
    public static class BatchVerify
    {
        static string Arg(string name)
        {
            var a = Environment.GetCommandLineArgs();
            int i = Array.IndexOf(a, name);
            return i >= 0 && i + 1 < a.Length ? a[i + 1] : null;
        }

        public static void Run()
        {
            var inputs = Arg("-inputs");
            var output = Arg("-out");
            try
            {
                if (!GpuWaterSim.Supported) throw new Exception("compute shaders not supported on this device: " + SystemInfo.graphicsDeviceType);
                var inp = JToken.Parse(File.ReadAllText(inputs));
                using var sim = new GpuWaterSim();
                sim.Init(inp);
                var t0 = DateTime.Now;
                sim.RunToEnd();
                var bal = sim.Balance();
                var depth = sim.Depth();
                var bytes = new byte[depth.Length * 4];
                Buffer.BlockCopy(depth, 0, bytes, 0, bytes.Length);
                File.WriteAllText(output, JsonConvert.SerializeObject(new
                {
                    ok = true, device = SystemInfo.graphicsDeviceName, api = SystemInfo.graphicsDeviceType.ToString(),
                    seconds = (DateTime.Now - t0).TotalSeconds, balance = bal, depth = Convert.ToBase64String(bytes)
                }));
                Debug.Log("BatchVerify done: " + output);
                EditorExit(0);
            }
            catch (Exception ex)
            {
                File.WriteAllText(output ?? "batchverify_error.json", JsonConvert.SerializeObject(new { ok = false, error = ex.ToString() }));
                Debug.LogError(ex);
                EditorExit(1);
            }
        }

        static void EditorExit(int code)
        {
#if UNITY_EDITOR
            UnityEditor.EditorApplication.Exit(code);
#endif
        }
    }
}
