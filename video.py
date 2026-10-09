"""
SnipBG video and GIF processing.

Each frame goes through the same image pipeline as stills. Video is muxed with
ffmpeg: MOV (ProRes 4444, real 10-bit alpha) by default, or MP4 (H.264) with a
green-screen background for editors that can't read ProRes. GIFs are processed
frame-by-frame and written back out as an animated GIF (transparent).

ffmpeg must be on PATH for video. If it isn't, process_video raises and the
caller reports it. GIFs use only Pillow and always work.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageSequence

import core


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _frame_indices(total: int, speed: int):
    """Which frame indices to actually process given video-speed (1..4)."""
    speed = max(1, min(4, int(speed)))
    return set(range(0, total, speed))


# --------------------------------------------------------------------------- #
# GIF
# --------------------------------------------------------------------------- #
def process_gif(in_path: str, out_path: str, settings: "core.Settings", progress=None):
    src = Image.open(in_path)
    frames = []
    durations = []
    all_frames = list(ImageSequence.Iterator(src))
    keep = _frame_indices(len(all_frames), settings.video_speed)
    last = None
    for i, fr in enumerate(all_frames):
        dur = fr.info.get("duration", 80)
        if i in keep:
            rgb = fr.convert("RGB")
            out, _ = core.process_image(rgb, settings)
            last = out
        if last is None:
            continue
        frames.append(last.convert("RGBA"))
        durations.append(dur)
        if progress:
            progress(i + 1, len(all_frames))

    if not frames:
        raise RuntimeError("No frames processed")

    out_path = os.path.splitext(out_path)[0] + ".gif"
    frames[0].save(out_path, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, disposal=2, transparency=0)
    return out_path


# --------------------------------------------------------------------------- #
# Video
# --------------------------------------------------------------------------- #
def process_video(in_path: str, out_path: str, settings: "core.Settings", progress=None):
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg not found on PATH. Install ffmpeg to process video.")

    import cv2  # opencv comes with transparent-background

    cap = cv2.VideoCapture(in_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    keep = _frame_indices(total if total > 0 else 10 ** 9, settings.video_speed)

    transparent = settings.background == "transparent" and not settings.sticker
    greenscreen = (settings.video_format == "mp4") and transparent

    tmp = tempfile.mkdtemp(prefix="snipbg_")
    n = 0
    last_rgba = None
    try:
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx in keep:
                rgb = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                processed, _ = core.process_image(rgb, settings)
                last_rgba = processed.convert("RGBA")
            if last_rgba is not None:
                if greenscreen:
                    bg = Image.new("RGBA", last_rgba.size, (0, 177, 64, 255))
                    flat = Image.alpha_composite(bg, last_rgba).convert("RGB")
                    flat.save(os.path.join(tmp, f"f_{n:06d}.png"))
                elif transparent:
                    last_rgba.save(os.path.join(tmp, f"f_{n:06d}.png"))
                else:
                    last_rgba.convert("RGB").save(os.path.join(tmp, f"f_{n:06d}.png"))
                n += 1
            idx += 1
            if progress and total:
                progress(idx, total)
        cap.release()

        if n == 0:
            raise RuntimeError("No frames decoded")

        out_fps = fps / max(1, settings.video_speed)
        pattern = os.path.join(tmp, "f_%06d.png")

        if transparent and settings.video_format == "mov-prores":
            out_path = os.path.splitext(out_path)[0] + ".mov"
            cmd = ["ffmpeg", "-y", "-framerate", f"{out_fps}", "-i", pattern,
                   "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
                   out_path]
        else:
            out_path = os.path.splitext(out_path)[0] + ".mp4"
            cmd = ["ffmpeg", "-y", "-framerate", f"{out_fps}", "-i", pattern,
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", out_path]

        # try to bring original audio along
        cmd_audio = cmd[:-1] + ["-i", in_path, "-map", "0:v", "-map", "1:a?",
                                "-c:a", "aac", "-shortest", out_path]
        try:
            subprocess.run(cmd_audio, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            subprocess.run(cmd, check=True, capture_output=True)
        return out_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
