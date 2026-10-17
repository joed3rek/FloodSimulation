"""Encode PNG frame sequences (from the Unity app) to MP4 with the ffmpeg binary bundled by imageio-ffmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path


def encode(folder: Path, fps: int = 30, pattern: str = "frame_%05d.png", out_name: str = "simulation.mp4") -> Path:
    import imageio_ffmpeg

    folder = Path(folder)
    if not any(folder.glob("frame_*.png")):
        raise FileNotFoundError(f"no frame_*.png in {folder}")
    out = folder / out_name
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(folder / pattern),
           "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", str(out)]
    subprocess.run(cmd, check=True)
    return out
