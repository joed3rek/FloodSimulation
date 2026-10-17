// Runs WaterSim.compute on the inputs served by the engine (/sim2d/{rp}/inputs), so the GPU and the
// engine simulate exactly the same case. Real-time mode reads the maximum depth once per frame to set
// the time step; verification mode reads it every step, as the engine does, and compares volumes.
using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SpongePark
{
    public class GpuWaterSim : IDisposable
    {
        public int Rows, Cols;
        public float Cell, Time, Duration;
        public Vector2 Origin;
        public bool Ready => cs != null;

        ComputeShader cs;
        readonly Dictionary<string, ComputeBuffer> buf = new Dictionary<string, ComputeBuffer>();
        float[] rain;
        float rainDt, alpha, dtMax, cumRain, cellArea;
        int nEl, nCells, groups;
        float[] groupMax, depth;
        float datum;
        double rainTotal;
        readonly Dictionary<string, int> k = new Dictionary<string, int>();

        public static bool Supported => SystemInfo.supportsComputeShaders;

        public void Init(JToken inp)
        {
            cs = Resources.Load<ComputeShader>("WaterSim");
            if (cs == null) throw new Exception("WaterSim.compute not found in Resources");
            foreach (var name in new[] { "FluxX", "FluxY", "CellScale", "ScaleX", "ScaleY", "Update", "ElementShare",
                                         "Sources", "ElementUpdate", "MaxDepth" })
                k[name] = cs.FindKernel(name);
            Rows = (int)inp["rows"]; Cols = (int)inp["cols"]; Cell = (float)inp["cell_m"];
            Origin = new Vector2((float)inp["origin"][0], (float)inp["origin"][1]);
            nCells = Rows * Cols; cellArea = Cell * Cell;
            rain = inp["rain_mm_hr"].ToObject<float[]>();
            rainDt = (float)inp["rain_dt_s"]; Duration = (float)inp["duration_s"];
            alpha = (float)inp["alpha"]; dtMax = (float)inp["dt_max"];
            var z = Decode.F32((string)inp["z"]);
            var mask = Decode.U8((string)inp["mask"]).Select(b => (int)b).ToArray();
            datum = float.MaxValue;
            for (int i = 0; i < nCells; i++) if (mask[i] != 0) datum = Mathf.Min(datum, z[i]);
            for (int i = 0; i < nCells; i++) z[i] = mask[i] != 0 ? z[i] - datum : 0f;   // float32 precision
            var n = Decode.F32((string)inp["n"]);
            for (int i = 0; i < nCells; i++) n[i] *= n[i];

            Make("Z", z); Make("Mask", mask); Make("N2", n);
            Make("H", new float[nCells]); Make("QX", new float[Rows * (Cols + 1)]); Make("QY", new float[(Rows + 1) * Cols]);
            Make("Scale", new float[nCells]); Make("CellOut", new float[nCells]); Make("CellInf", new float[nCells]);
            Make("HMax", new float[nCells]); Make("Take", new float[nCells]);

            var inf = inp["infiltration"];
            var kind = (string)inf["kind"];
            int infilKind = kind == "curve_number" ? 1 : kind == "horton" ? 2 : 0;
            float[] Arr(string key) => inf[key] != null ? Decode.F32((string)inf[key]) : new float[nCells];
            Make("InfBase", Arr("base_mm_hr")); Make("InfS", Arr("S_mm"));
            Make("InfF0", Arr("f0_mm_hr")); Make("InfFmin", Arr("fmin_mm_hr")); Make("InfK", Arr("k_1_hr"));

            var els = inp["elements"];
            int[] label = els != null && els.Type != JTokenType.Null ? Decode.I32((string)els["label"]) : Enumerable.Repeat(-1, nCells).ToArray();
            nEl = els != null && els.Type != JTokenType.Null ? els["ids"].Count() : 0;
            var cap = nEl > 0 ? els["capacity_m3"].ToObject<float[]>() : new float[1];
            var rate = nEl > 0 ? els["rate_m_s"].ToObject<float[]>() : new float[1];
            var area = nEl > 0 ? els["area_m2"].ToObject<float[]>() : new float[1];
            var cells = new float[Math.Max(nEl, 1)];
            var lists = new List<int>[Math.Max(nEl, 1)];
            for (int e = 0; e < lists.Length; e++) lists[e] = new List<int>();
            for (int i = 0; i < nCells; i++)
                if (label[i] >= 0 && mask[i] != 0) { cells[label[i]] += 1; lists[label[i]].Add(i); }
            var start = new int[lists.Length + 1];
            var idx = new List<int>();
            for (int e = 0; e < lists.Length; e++) { start[e] = idx.Count; idx.AddRange(lists[e]); }
            start[lists.Length] = idx.Count;
            if (idx.Count == 0) idx.Add(0);
            Make("El", label); Make("Cap", cap); Make("ElRate", rate); Make("ElArea", area); Make("ElCells", cells);
            Make("ElStart", start); Make("ElIdx", idx.ToArray());
            int ne = Math.Max(nEl, 1);
            Make("Share", new float[ne]); Make("Store", new float[ne]); Make("ElInf", new float[ne]);
            groups = Mathf.CeilToInt(nCells / 256f);
            groupMax = new float[groups];
            Make("GroupMax", groupMax);
            depth = new float[nCells];

            cs.SetInt("NR", Rows); cs.SetInt("NC", Cols); cs.SetInt("NEl", nEl); cs.SetInt("InfilKind", infilKind);
            cs.SetFloat("Dx", Cell); cs.SetFloat("Drop", (float)inp["edge_drop_fraction"] * Cell); cs.SetFloat("CellArea", cellArea);
            foreach (var kv in k)
                foreach (var b in buf)
                    if (Uses(kv.Key, b.Key)) cs.SetBuffer(kv.Value, b.Key, b.Value);
            Time = 0; cumRain = 0; rainTotal = 0;
            maskCount = mask.Count(m => m != 0);
        }

        int maskCount;

        static bool Uses(string kernel, string buffer)
        {
            // every kernel may bind every buffer it declares; binding unused ones is harmless but Unity
            // warns, so bind by name per kernel
            var map = new Dictionary<string, string[]>
            {
                ["FluxX"] = new[] { "Z", "Mask", "N2", "H", "QX" },
                ["FluxY"] = new[] { "Z", "Mask", "N2", "H", "QY" },
                ["CellScale"] = new[] { "Mask", "H", "QX", "QY", "Scale" },
                ["ScaleX"] = new[] { "Mask", "QX", "Scale" },
                ["ScaleY"] = new[] { "Mask", "QY", "Scale" },
                ["Update"] = new[] { "Mask", "H", "QX", "QY", "CellOut" },
                ["ElementShare"] = new[] { "Share", "Store", "Cap", "ElCells" },
                ["Sources"] = new[] { "Mask", "H", "El", "Share", "Take", "CellInf", "HMax", "InfBase", "InfS", "InfF0", "InfFmin", "InfK" },
                ["ElementUpdate"] = new[] { "Take", "Store", "ElInf", "ElRate", "ElArea", "ElStart", "ElIdx" },
                ["MaxDepth"] = new[] { "Mask", "H", "GroupMax" },
            };
            return map[kernel].Contains(buffer);
        }

        void Make<T>(string name, T[] data) where T : struct
        {
            var b = new ComputeBuffer(Math.Max(data.Length, 1), System.Runtime.InteropServices.Marshal.SizeOf<T>());
            if (data.Length > 0) b.SetData(data);
            buf[name] = b;
        }

        public float MaxDepthNow()
        {
            cs.Dispatch(k["MaxDepth"], groups, 1, 1);
            buf["GroupMax"].GetData(groupMax);
            return groupMax.Max();
        }

        /// One step with the given maximum depth (m). Returns dt (s).
        public float Step(float hmax)
        {
            float dt = hmax < 1e-3f ? dtMax : Mathf.Min(dtMax, alpha * Cell / Mathf.Sqrt(9.81f * hmax));
            int i = Mathf.FloorToInt(Time / rainDt);
            dt = Mathf.Min(dt, (i + 1) * rainDt - Time, Duration - Time);
            if (dt <= 0) return 0;
            float rate = i < rain.Length ? rain[i] : 0f;
            cs.SetFloat("Dt", dt);
            cs.SetFloat("RainM", rate / 3600000f * dt);
            cs.SetFloat("RainRate", rate);
            cs.SetFloat("CumRain", cumRain);
            cs.SetFloat("TimeS", Time);
            cumRain += rate * dt / 3600f;
            rainTotal += rate / 3600000.0 * dt * cellArea * maskCount;
            int gx = Mathf.CeilToInt((Cols + 1) / 8f), gy = Mathf.CeilToInt((Rows + 1) / 8f);
            cs.Dispatch(k["FluxX"], gx, gy, 1);
            cs.Dispatch(k["FluxY"], gx, gy, 1);
            cs.Dispatch(k["CellScale"], gx, gy, 1);
            cs.Dispatch(k["ScaleX"], gx, gy, 1);
            cs.Dispatch(k["ScaleY"], gx, gy, 1);
            cs.Dispatch(k["Update"], gx, gy, 1);
            int ge = Mathf.CeilToInt(Mathf.Max(nEl, 1) / 64f);
            cs.Dispatch(k["ElementShare"], ge, 1, 1);
            cs.Dispatch(k["Sources"], gx, gy, 1);
            cs.Dispatch(k["ElementUpdate"], ge, 1, 1);
            Time += dt;
            return dt;
        }

        /// Real time: advance by simTime seconds, reading the maximum depth once (with a safety margin).
        public void Advance(float simTime)
        {
            float target = Mathf.Min(Duration, Time + simTime);
            float hmax = MaxDepthNow() * 1.5f + 0.01f;
            int guard = 0;
            while (Time < target - 1e-3f && guard++ < 20000) Step(hmax);
        }

        /// Verification: step exactly as the engine does (maximum depth read every step).
        public void RunToEnd()
        {
            int guard = 0;
            while (Time < Duration - 1e-3f && guard++ < 2_000_000) Step(MaxDepthNow());
        }

        public float[] Depth()
        {
            buf["H"].GetData(depth);
            return depth;
        }

        public Dictionary<string, double> Balance()
        {
            double Sum(string name, int n) { var a = new float[n]; buf[name].GetData(a); return a.Sum(v => (double)v); }
            var h = Depth();
            return new Dictionary<string, double>
            {
                ["rainfall_m3"] = rainTotal,
                ["outflow_m3"] = Sum("CellOut", nCells),
                ["infiltration_ground_m3"] = Sum("CellInf", nCells),
                ["infiltration_elements_m3"] = nEl > 0 ? Sum("ElInf", nEl) : 0,
                ["element_storage_remaining_m3"] = nEl > 0 ? Sum("Store", nEl) : 0,
                ["surface_remaining_m3"] = h.Sum(v => (double)v) * cellArea,
            };
        }

        public void Dispose()
        {
            foreach (var b in buf.Values) b.Release();
            buf.Clear();
        }
    }
}
