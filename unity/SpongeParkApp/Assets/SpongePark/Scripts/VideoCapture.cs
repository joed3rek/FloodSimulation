// Video export: renders frames at a fixed rate to PNGs (Time.captureFramerate), then encodes an MP4
// with ffmpeg if it is on the PATH. In the Editor, Unity Recorder (in the package manifest) can be used
// instead.
using System;
using System.Diagnostics;
using System.IO;
using UnityEngine;

namespace SpongePark
{
    public class VideoCapture : MonoBehaviour
    {
        public int Fps = 30;
        public bool Recording { get; private set; }
        public string Folder { get; private set; }
        public string Result = "";
        int frame;

        public void Begin(string folder)
        {
            Folder = folder;
            Directory.CreateDirectory(folder);
            foreach (var f in Directory.GetFiles(folder, "frame_*.png")) File.Delete(f);
            frame = 0;
            Time.captureFramerate = Fps;
            Recording = true;
            Result = "recording...";
        }

        public void End()
        {
            Recording = false;
            Time.captureFramerate = 0;
            var mp4 = Path.Combine(Folder, "simulation.mp4");
            try
            {
                var p = Process.Start(new ProcessStartInfo
                {
                    FileName = "ffmpeg",
                    Arguments = $"-y -framerate {Fps} -i \"{Path.Combine(Folder, "frame_%05d.png")}\" -pix_fmt yuv420p -vf \"scale=trunc(iw/2)*2:trunc(ih/2)*2\" \"{mp4}\"",
                    UseShellExecute = false, CreateNoWindow = true
                });
                p.WaitForExit();
                Result = p.ExitCode == 0 ? "video: " + mp4 : $"ffmpeg failed; {frame} PNG frames in {Folder}";
            }
            catch (Exception)
            {
                Result = $"ffmpeg not found; {frame} PNG frames in {Folder} (encode with any video tool)";
            }
        }

        void LateUpdate()
        {
            if (!Recording) return;
            ScreenCapture.CaptureScreenshot(Path.Combine(Folder, $"frame_{frame++:00000}.png"));
        }
    }
}
