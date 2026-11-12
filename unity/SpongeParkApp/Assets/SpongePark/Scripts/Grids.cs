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

    /// The water's velocity at every frame of a 2D flood run (engine /sim2d/{rp}/velocity): east and north m/s per
    /// cell centre, row 0 north. Brought to a time with At(t), then read anywhere with Sample (bilinear).
    public class VelocityFrames
    {
        public int Rows, Cols, Count;
        public float Cell, MaxSpeed, P95Speed;
        public Vector2 Origin;
        public float[] Times;
        ushort[] half;      // frame-major: per frame, east for every cell then north for every cell
        public float[] U, V, Speed;   // at the time last asked for
        float shownT = float.NaN;
        public int FrameIndex { get; private set; } = -1;   // the stored frame at or before that time

        public static VelocityFrames FromPayload(JToken t)
        {
            var f = new VelocityFrames
            {
                Rows = (int)t["rows"], Cols = (int)t["cols"], Cell = (float)t["cell_m"],
                Origin = new Vector2((float)t["origin"][0], (float)t["origin"][1]),
                Times = t["times_s"].ToObject<float[]>(),
                MaxSpeed = (float)t["max_speed_m_s"], P95Speed = (float)t["p95_speed_m_s"],
            };
            f.Count = f.Times.Length;
            var bytes = Convert.FromBase64String((string)t["velocity"]);
            f.half = new ushort[bytes.Length / 2];
            Buffer.BlockCopy(bytes, 0, f.half, 0, bytes.Length);
            int n = f.Rows * f.Cols;
            f.U = new float[n]; f.V = new float[n]; f.Speed = new float[n];
            return f;
        }

        /// The velocities at time t (s), linearly between stored frames.
        public void At(float t)
        {
            if (t == shownT) return;
            shownT = t;
            int n = Rows * Cols;
            int i = Array.BinarySearch(Times, t);
            if (i < 0) i = ~i - 1;
            i = Mathf.Clamp(i, 0, Count - 1);
            int j = Mathf.Min(i + 1, Count - 1);
            FrameIndex = i;
            float w = j == i ? 0f : Mathf.Clamp01((t - Times[i]) / (Times[j] - Times[i]));
            int a = i * 2 * n, b = j * 2 * n;
            for (int k = 0; k < n; k++)
            {
                U[k] = Mathf.Lerp(Mathf.HalfToFloat(half[a + k]), Mathf.HalfToFloat(half[b + k]), w);
                V[k] = Mathf.Lerp(Mathf.HalfToFloat(half[a + n + k]), Mathf.HalfToFloat(half[b + n + k]), w);
                Speed[k] = Mathf.Sqrt(U[k] * U[k] + V[k] * V[k]);
            }
        }

        /// The velocity at a survey point, between the four cell centres around it; false outside the grid.
        public bool Sample(float x, float y, out float u, out float v)
        {
            u = v = 0;
            float fc = (x - Origin.x) / Cell - 0.5f, fr = (Origin.y - y) / Cell - 0.5f;
            int c0 = Mathf.FloorToInt(fc), r0 = Mathf.FloorToInt(fr);
            if (r0 < -1 || c0 < -1 || r0 >= Rows || c0 >= Cols) return false;
            float tc = fc - c0, tr = fr - r0;
            for (int dr = 0; dr <= 1; dr++)
                for (int dc = 0; dc <= 1; dc++)
                {
                    int r = Mathf.Clamp(r0 + dr, 0, Rows - 1), c = Mathf.Clamp(c0 + dc, 0, Cols - 1);
                    float w = (dr == 1 ? tr : 1 - tr) * (dc == 1 ? tc : 1 - tc);
                    u += w * U[r * Cols + c];
                    v += w * V[r * Cols + c];
                }
            return true;
        }

        public Vector2 CellCentre(int k) => new Vector2(Origin.x + (k % Cols + 0.5f) * Cell, Origin.y - (k / Cols + 0.5f) * Cell);
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
