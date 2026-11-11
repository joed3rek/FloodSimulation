// Still image export: the scene cameras render the framed part of the viewport into an off-screen texture at the
// chosen resolution (HD to 8K), supersampled and multisampled so lines and edges stay crisp when the picture is
// zoomed. A scale bar is drawn into the picture at that resolution. The result is an opaque PNG.
using System;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Experimental.Rendering;

namespace SpongePark
{
    public static class ImageExport
    {
        public struct Size
        {
            public string Name; public int W, H;
            public float Aspect => (float)W / H;
            public string Label => $"{Name}  {W} × {H}";
        }

        public static readonly Size[] Sizes =
        {
            new Size { Name = "HD", W = 1280, H = 720 },
            new Size { Name = "Full HD", W = 1920, H = 1080 },
            new Size { Name = "2K", W = 2048, H = 1080 },
            new Size { Name = "QHD", W = 2560, H = 1440 },
            new Size { Name = "4K", W = 3840, H = 2160 },
            new Size { Name = "8K", W = 7680, H = 4320 },
        };

        /// The part of the viewport (screen pixels, origin bottom left) that the picture shows: the largest rectangle
        /// of the picture's shape, centred in the viewport.
        public static Rect Frame(Rect viewport, float aspect)
        {
            float w = viewport.width, h = viewport.height;
            if (w / Mathf.Max(1, h) > aspect) w = h * aspect; else h = w / aspect;
            return new Rect(viewport.center.x - w / 2, viewport.center.y - h / 2, w, h);
        }

        /// Renders the cameras' view of `frame` (screen pixels) at size.W × size.H and returns the pixels (RGB, rows
        /// from the bottom). `metresPerFramePixel` > 0 adds a scale bar; `scaleNote` is written after its length.
        public static byte[] Render(IList<Camera> cams, Rect frame, Size size, Color background, float metresPerFramePixel, string scaleNote)
        {
            int W = size.W, H = size.H;
            // 2× supersampling where the card allows it, on top of multisampling: thin flow lines and arrow edges stay smooth
            int ss = W * 2 <= SystemInfo.maxTextureSize && H * 2 <= SystemInfo.maxTextureSize && W <= 3840 ? 2 : 1;
            int rw = W * ss, rh = H * ss;
            int msaa = rw * rh > 4096 * 2304 ? 4 : 8;
            var scene = new RenderTexture(rw, rh, 24, RenderTextureFormat.ARGB32) { antiAliasing = msaa, filterMode = FilterMode.Bilinear };
            var output = new RenderTexture(W, H, 0, RenderTextureFormat.ARGB32) { filterMode = FilterMode.Bilinear };
            var prev = RenderTexture.active;
            try
            {
                scene.Create();
                output.Create();
                RenderTexture.active = scene;
                GL.Clear(true, true, background);
                foreach (var c in cams)
                {
                    if (c == null || !c.enabled) continue;
                    var cr = c.pixelRect;
                    float x0 = Mathf.Max(cr.xMin, frame.xMin), x1 = Mathf.Min(cr.xMax, frame.xMax);
                    float y0 = Mathf.Max(cr.yMin, frame.yMin), y1 = Mathf.Min(cr.yMax, frame.yMax);
                    if (x1 <= x0 || y1 <= y0) continue;
                    // narrow the camera's own projection to the framed part of its viewport (works for plan and 3D)
                    var p = c.projectionMatrix;
                    float nx0 = 2 * (x0 - cr.x) / cr.width - 1, nx1 = 2 * (x1 - cr.x) / cr.width - 1;
                    float ny0 = 2 * (y0 - cr.y) / cr.height - 1, ny1 = 2 * (y1 - cr.y) / cr.height - 1;
                    float sx = 2 / (nx1 - nx0), sy = 2 / (ny1 - ny0);
                    var s = Matrix4x4.identity;
                    s.m00 = sx; s.m03 = -(nx0 + nx1) / 2 * sx;
                    s.m11 = sy; s.m13 = -(ny0 + ny1) / 2 * sy;
                    var oldRect = c.rect;
                    var oldTarget = c.targetTexture;
                    try
                    {
                        c.targetTexture = scene;
                        c.rect = new Rect((x0 - frame.x) / frame.width, (y0 - frame.y) / frame.height, (x1 - x0) / frame.width, (y1 - y0) / frame.height);
                        c.projectionMatrix = s * p;
                        c.Render();
                    }
                    finally
                    {
                        c.targetTexture = oldTarget;
                        c.rect = oldRect;
                        c.ResetProjectionMatrix();
                        c.ResetAspect();
                    }
                }
                // resolve the multisampling and average the supersamples (bilinear at half size = a 2×2 box filter)
                Graphics.Blit(scene, output);
                if (metresPerFramePixel > 0)
                    ScaleBar(output, metresPerFramePixel * frame.height / H, scaleNote);
                RenderTexture.active = output;
                var tex = new Texture2D(W, H, TextureFormat.RGB24, false);
                try
                {
                    tex.ReadPixels(new Rect(0, 0, W, H), 0, 0, false);
                    return tex.GetRawTextureData<byte>().ToArray();
                }
                finally { UnityEngine.Object.Destroy(tex); }
            }
            finally
            {
                RenderTexture.active = prev;
                scene.Release(); output.Release();
                UnityEngine.Object.Destroy(scene); UnityEngine.Object.Destroy(output);
            }
        }

        /// PNG encoding off the main thread (an 8K picture takes a few seconds), then written to `path`.
        public static Task Save(byte[] rgb, int w, int h, string path) => Task.Run(() =>
        {
            var png = ImageConversion.EncodeArrayToPNG(rgb, GraphicsFormat.R8G8B8_UNorm, (uint)w, (uint)h);
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            File.WriteAllBytes(path, png);
        });

        // ------------------------------------------------------------ scale bar

        static Material solid;
        static Font font;

        /// Bottom left: a round length of ground in alternating black and white parts, labelled, on a light card.
        /// Every size is in proportion to the picture's height, so it reads the same at HD and at 8K.
        static void ScaleBar(RenderTexture rt, float metresPerPixel, string note)
        {
            int W = rt.width, H = rt.height;
            float u = H / 1080f;
            float want = 260 * u * metresPerPixel, nice = 0;
            foreach (var v in new[] { 1f, 2f, 5f, 10f, 20f, 25f, 50f, 100f, 200f, 250f, 500f, 1000f, 2000f, 5000f }) if (v <= want) nice = v;
            if (nice <= 0) return;
            float len = nice / metresPerPixel;
            if (solid == null)
            {
                solid = new Material(Shader.Find("Hidden/Internal-Colored")) { hideFlags = HideFlags.HideAndDontSave };
                solid.SetInt("_SrcBlend", (int)UnityEngine.Rendering.BlendMode.SrcAlpha);
                solid.SetInt("_DstBlend", (int)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
                solid.SetInt("_Cull", (int)UnityEngine.Rendering.CullMode.Off);
                solid.SetInt("_ZWrite", 0);
                solid.SetInt("_ZTest", (int)UnityEngine.Rendering.CompareFunction.Always);
            }
            if (font == null) font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            int fs = Mathf.Max(10, Mathf.RoundToInt(22 * u));
            string length = nice >= 1000 ? $"{nice / 1000:0.#} km" : $"{nice:0} m";
            string label = length + (string.IsNullOrEmpty(note) ? "" : " " + note);
            font.RequestCharactersInTexture("0" + label, fs, FontStyle.Normal);   // before any glyph is read: the atlas may be rebuilt

            float m = 28 * u, pad = 14 * u, barH = 10 * u, gap = 8 * u;
            float labelX = len - TextWidth(length, fs) / 2;   // the length centred under the bar's end, any note after it
            float half0 = TextWidth("0", fs) / 2;
            float cardW = Mathf.Max(len, labelX + TextWidth(label, fs)) + 2 * pad + half0;
            float cardH = pad + barH + gap + fs + pad;
            float x = m + pad + half0, y = m + pad + fs + gap;   // bar's bottom-left (pixels, origin bottom left)

            RenderTexture.active = rt;
            GL.PushMatrix();
            GL.LoadPixelMatrix(0, W, 0, H);
            solid.SetPass(0);
            GL.Begin(GL.QUADS);
            Quad(m, m, cardW, cardH, new Color(1, 1, 1, 0.88f));
            Quad(x - u, y - u, len + 2 * u, barH + 2 * u, new Color(0.1f, 0.1f, 0.1f, 1));
            for (int i = 0; i < 4; i++)
                Quad(x + i * len / 4, y, len / 4, barH, i % 2 == 0 ? new Color(0.1f, 0.1f, 0.1f, 1) : Color.white);
            GL.End();
            var ink = new Color(0.1f, 0.1f, 0.1f, 1);
            Text("0", x - half0, m + pad, fs, ink);
            Text(label, x + labelX, m + pad, fs, ink);
            GL.PopMatrix();
        }

        static void Quad(float x, float y, float w, float h, Color c)
        {
            GL.Color(c);
            GL.Vertex3(x, y, 0); GL.Vertex3(x, y + h, 0); GL.Vertex3(x + w, y + h, 0); GL.Vertex3(x + w, y, 0);
        }

        static float TextWidth(string s, int fs)
        {
            float w = 0;
            foreach (var ch in s) if (font.GetCharacterInfo(ch, out var ci, fs, FontStyle.Normal)) w += ci.advance;
            return w;
        }

        /// Text with its baseline at `baseY`, from the font's glyph atlas (sharp at any picture size).
        static void Text(string s, float x, float baseY, int fs, Color c)
        {
            font.material.SetPass(0);
            GL.Begin(GL.QUADS);
            GL.Color(c);
            foreach (var ch in s)
            {
                if (!font.GetCharacterInfo(ch, out var ci, fs, FontStyle.Normal)) continue;
                GL.TexCoord(ci.uvBottomLeft); GL.Vertex3(x + ci.minX, baseY + ci.minY, 0);
                GL.TexCoord(ci.uvTopLeft); GL.Vertex3(x + ci.minX, baseY + ci.maxY, 0);
                GL.TexCoord(ci.uvTopRight); GL.Vertex3(x + ci.maxX, baseY + ci.maxY, 0);
                GL.TexCoord(ci.uvBottomRight); GL.Vertex3(x + ci.maxX, baseY + ci.minY, 0);
                x += ci.advance;
            }
            GL.End();
        }
    }
}
