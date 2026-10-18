// Decoding of the engine's grid payloads (base64 little-endian arrays, row 0 = north).
using System;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SpongePark
{
    public class HeightGrid
    {
        public int Rows, Cols;
        public float Cell, ZMin, ZMax;
        public Vector2 Origin;      // x_min, y_max in survey metres
        public float[] Z;           // NaN = no data
        public byte[] Surveyed;     // 1 = surveyed ground, 0 = widened for display (null: all surveyed)

        public static HeightGrid FromPayload(JToken t)
        {
            var g = new HeightGrid
            {
                Rows = (int)t["rows"], Cols = (int)t["cols"], Cell = (float)t["cell_m"],
                ZMin = (float)t["z_min"], ZMax = (float)t["z_max"],
                Origin = new Vector2((float)t["origin"][0], (float)t["origin"][1])
            };
            g.Z = Decode.F32((string)t["z"]);
            if (t["surveyed"] != null && t["surveyed"].Type == JTokenType.String) g.Surveyed = System.Convert.FromBase64String((string)t["surveyed"]);
            return g;
        }

        public bool Valid(int r, int c) => !float.IsNaN(Z[r * Cols + c]);
    }

    public class DepthFrames
    {
        public int Rows, Cols, Count;
        public float Cell;
        public Vector2 Origin;
        public float[] Times;
        public ushort[] Half;   // frame-major float16

        public static DepthFrames FromPayload(JToken t)
        {
            var f = new DepthFrames
            {
                Rows = (int)t["rows"], Cols = (int)t["cols"], Cell = (float)t["cell_m"],
                Origin = new Vector2((float)t["origin"][0], (float)t["origin"][1]),
                Times = t["times_s"].ToObject<float[]>()
            };
            f.Count = f.Times.Length;
            var bytes = Convert.FromBase64String((string)t["frames"]);
            f.Half = new ushort[bytes.Length / 2];
            Buffer.BlockCopy(bytes, 0, f.Half, 0, bytes.Length);
            return f;
        }

        /// Depths at time t (s), linearly interpolated between stored frames.
        public void Sample(float t, float[] into)
        {
            int n = Rows * Cols;
            int i = Array.BinarySearch(Times, t);
            if (i < 0) i = ~i - 1;
            i = Mathf.Clamp(i, 0, Count - 1);
            int j = Mathf.Min(i + 1, Count - 1);
            float w = j == i ? 0f : Mathf.Clamp01((t - Times[i]) / (Times[j] - Times[i]));
            int a = i * n, b = j * n;
            for (int k = 0; k < n; k++)
                into[k] = Mathf.Lerp(Mathf.HalfToFloat(Half[a + k]), Mathf.HalfToFloat(Half[b + k]), w);
        }
    }

    public static class Decode
    {
        public static float[] F32(string b64)
        {
            var bytes = Convert.FromBase64String(b64);
            var a = new float[bytes.Length / 4];
            Buffer.BlockCopy(bytes, 0, a, 0, bytes.Length);
            return a;
        }

        public static int[] I32(string b64)
        {
            var bytes = Convert.FromBase64String(b64);
            var a = new int[bytes.Length / 4];
            Buffer.BlockCopy(bytes, 0, a, 0, bytes.Length);
            return a;
        }

        public static byte[] U8(string b64) => Convert.FromBase64String(b64);
    }
}
