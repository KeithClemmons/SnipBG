"""
SnipBG core processing pipeline.

A single Settings object drives everything. process_image() takes a source
PIL image plus Settings and returns the finished PIL image, applying (in order):
cutout -> despill -> enhance -> sticker | (shadow + background) -> center ->
resize -> watermark. Saving (format / compression / naming) is handled by save_output().

The InSPyReNet model is provided by the `transparent-background` package and is
loaded lazily and cached so it's only built once per process.
"""

from __future__ import annotations

import os
import io
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime

import numpy as np
from PIL import Image, ImageFilter, ImageDraw

try:
    from scipy import ndimage as _ndi
except Exception:  # pragma: no cover
    _ndi = None

# HEIC/HEIF (iPhone photos) needs the pillow-heif plugin; without it those files are skipped.
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_EXTS = (".heic", ".heif")
except Exception:  # pragma: no cover
    HEIF_EXTS = ()


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".avif") + HEIF_EXTS
GIF_EXTS = (".gif",)
VIDEO_EXTS = (".mp4", ".mov", ".avi", ".webm", ".mkv")


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
@dataclass
class Settings:
    # model
    quality: str = "base"          # base (InSPyReNet best) | fast
    gpu: bool = False

    # background
    background: str = "transparent"  # transparent|black|white|image|blur|custom
    bg_color: str = "#ffffff"        # used when background == custom
    bg_image: str = ""               # path, used when background == image
    blur_strength: int = 50          # 1..100

    # edges
    despill: int = 0                 # 0..100

    # enhance / resize
    enhance: bool = False
    enhance_scale: int = 2           # 2|3|4 output multiplier
    resize: str = ""                 # "WxH" or "" for off

    # sticker
    sticker: bool = False
    sticker_thickness: int = 16      # 8..32
    sticker_color: str = "white"     # white|black|gray

    # shadow
    shadow: int = 0                  # 0..100
    shadow_type: str = "classic"     # classic|gimp-style|soft

    # layout
    center: bool = False

    # output
    fmt: str = "png"                 # png|webp
    compression: str = "none"        # none|lossless|32bit|256colors|128colors
    name_pattern: str = "original"
    alpha_mask: bool = False
    watermark: str = ""              # path to PNG

    # video
    video_speed: int = 1             # 1..4
    video_format: str = "mov-prores"  # mov-prores|mp4

    def copy(self) -> "Settings":
        return Settings(**asdict(self))


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #
_remover_cache: dict = {}


def get_remover(quality: str = "base", gpu: bool = False):
    key = (quality, gpu)
    if key not in _remover_cache:
        from transparent_background import Remover
        # Always pick the device explicitly: left to itself, Remover grabs Apple's MPS
        # backend on Macs, which is untested with this model and absent on CI runners.
        device = "cpu"
        if gpu:
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda:0"
            except Exception:
                pass
        _remover_cache[key] = Remover(mode=quality, device=device)
    return _remover_cache[key]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def get_matte(img_rgb: Image.Image, settings: Settings) -> Image.Image:
    """Return an L-mode alpha matte (white = subject)."""
    remover = get_remover(settings.quality, settings.gpu)
    matte = remover.process(img_rgb, type="map")  # grayscale saliency map
    return matte.convert("L")


def cutout_from_matte(img_rgb: Image.Image, matte: Image.Image) -> Image.Image:
    out = img_rgb.convert("RGBA")
    out.putalpha(matte)
    return out


# --------------------------------------------------------------------------- #
# Despill
# --------------------------------------------------------------------------- #
def apply_despill(rgba: Image.Image, strength: int) -> Image.Image:
    """Push edge foreground colors away from the dominant background color.

    Two stages, following LocalBG: (1) detect dominant bg color from low-alpha
    pixels, (2) subtract that color's projection from the foreground, tapered so
    the solid interior keeps its natural color.
    """
    if strength <= 0:
        return rgba
    arr = np.asarray(rgba).astype(np.float32)
    rgb = arr[..., :3]
    a = arr[..., 3] / 255.0

    # dominant bg color from semi-transparent edge pixels
    edge = (a > 0.02) & (a < 0.5)
    if edge.sum() < 20:
        return rgba
    bg = rgb[edge].mean(axis=0)
    bgn = bg / (np.linalg.norm(bg) + 1e-6)

    s = strength / 100.0
    # projection of each pixel onto bg direction
    proj = (rgb * bgn).sum(axis=-1, keepdims=True) * bgn
    # taper: strongest at edges (mid alpha), fades in solid interior
    taper = (1.0 - np.abs(a - 0.5) * 2.0)
    taper = np.clip(taper, 0, 1)[..., None]
    rgb2 = rgb - proj * s * taper * 0.6
    rgb2 = np.clip(rgb2, 0, 255)

    out = np.dstack([rgb2, arr[..., 3]]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


# --------------------------------------------------------------------------- #
# Enhance (Real-ESRGAN with graceful fallback)
# --------------------------------------------------------------------------- #
_esrgan = None


def _load_esrgan():
    global _esrgan
    if _esrgan is None:
        from realesrgan import RealESRGANer
        from basicsr.archs.rrdbnet_arch import RRDBNet
        here = os.path.dirname(os.path.abspath(__file__))
        weights = os.path.join(here, "models", "RealESRGAN_x4plus.pth")
        if not os.path.exists(weights):
            raise FileNotFoundError("Real-ESRGAN weights not found; run install_upscale.bat")
        model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23,
                        num_grow_ch=32, scale=4)
        _esrgan = RealESRGANer(scale=4, model_path=weights, model=model, half=False)
    return _esrgan


def apply_enhance(rgba: Image.Image, scale: int = 2) -> Image.Image:
    """Upscale the cutout by an integer factor (2x/3x/4x). Uses Real-ESRGAN if
    available, otherwise a Lanczos + unsharp fallback. The alpha channel is
    scaled to match so transparency stays aligned."""
    scale = int(scale)
    if scale <= 1:
        return rgba
    w, h = rgba.size
    tw, th = w * scale, h * scale
    rgb = rgba.convert("RGB")
    alpha = rgba.getchannel("A")
    try:
        up = _load_esrgan()
        out_np, _ = up.enhance(np.asarray(rgb), outscale=scale)
        big = Image.fromarray(out_np).resize((tw, th), Image.LANCZOS)
    except Exception:
        big = rgb.resize((tw, th), Image.LANCZOS).filter(
            ImageFilter.UnsharpMask(radius=2, percent=120, threshold=2))
    big_alpha = alpha.resize((tw, th), Image.LANCZOS)
    out = big.convert("RGBA")
    out.putalpha(big_alpha)
    return out


# --------------------------------------------------------------------------- #
# Center
# --------------------------------------------------------------------------- #
def apply_center(rgba: Image.Image) -> Image.Image:
    a = np.asarray(rgba.getchannel("A"))
    ys, xs = np.where(a > 8)
    if len(xs) == 0:
        return rgba
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    subj = rgba.crop((x0, y0, x1 + 1, y1 + 1))
    canvas = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    px = (rgba.width - subj.width) // 2
    py = (rgba.height - subj.height) // 2
    canvas.paste(subj, (px, py), subj)
    return canvas


# --------------------------------------------------------------------------- #
# Sticker
# --------------------------------------------------------------------------- #
_STICKER_COLORS = {"white": (255, 255, 255), "black": (0, 0, 0), "gray": (128, 128, 128)}


def apply_sticker(rgba: Image.Image, thickness: int, color: str) -> Image.Image:
    col = _STICKER_COLORS.get(color, (255, 255, 255))
    a = np.asarray(rgba.getchannel("A"))
    solid = a > 40
    # scale thickness with image size, base reference 1000px
    t = max(1, int(thickness * (max(rgba.size) / 1000.0)))
    if _ndi is not None:
        filled = _ndi.binary_fill_holes(solid)
        dil = _ndi.binary_dilation(filled, iterations=t)
    else:
        mask_img = Image.fromarray((solid * 255).astype(np.uint8))
        dil_img = mask_img.filter(ImageFilter.MaxFilter(t * 2 + 1))
        dil = np.asarray(dil_img) > 40
        filled = solid
    border = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    border_arr = np.zeros((*dil.shape, 4), np.uint8)
    border_arr[dil] = (*col, 255)
    border = Image.fromarray(border_arr, "RGBA")
    # fill internal holes of the subject with sticker color too
    fill_arr = np.zeros((*filled.shape, 4), np.uint8)
    fill_arr[filled] = (*col, 255)
    base = Image.fromarray(fill_arr, "RGBA")
    base = Image.alpha_composite(border, base)
    out = Image.alpha_composite(base, rgba)
    return out


# --------------------------------------------------------------------------- #
# Shadow
# --------------------------------------------------------------------------- #
def apply_shadow(rgba: Image.Image, strength: int, style: str) -> Image.Image:
    if strength <= 0:
        return rgba
    s = strength / 100.0
    blur = max(1, int(40 * s * (max(rgba.size) / 1000.0)))
    off = int(30 * s * (max(rgba.size) / 1000.0))
    if style == "classic":
        ox, oy = 0, off
    elif style == "gimp-style":
        ox, oy = off, off
    else:  # soft glow
        ox, oy = 0, 0
    alpha = rgba.getchannel("A")
    shadow = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    blk = Image.new("RGBA", rgba.size, (0, 0, 0, int(160 * (0.4 + 0.6 * s))))
    shadow.paste(blk, (ox, oy), alpha)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    return Image.alpha_composite(shadow, rgba)


# --------------------------------------------------------------------------- #
# Background
# --------------------------------------------------------------------------- #
def apply_background(rgba: Image.Image, settings: Settings, source_rgb: Image.Image) -> Image.Image:
    bg = settings.background
    if bg == "transparent":
        return rgba
    w, h = rgba.size
    if bg == "black":
        base = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    elif bg == "white":
        base = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    elif bg == "custom":
        base = Image.new("RGBA", (w, h), (*_hex_to_rgb(settings.bg_color), 255))
    elif bg == "image" and settings.bg_image and os.path.exists(settings.bg_image):
        base = _fill_crop(Image.open(settings.bg_image).convert("RGBA"), w, h)
    elif bg == "blur":
        b = max(1, int(settings.blur_strength * 0.6))
        base = source_rgb.convert("RGBA").resize((w, h)).filter(ImageFilter.GaussianBlur(b))
    else:
        return rgba
    return Image.alpha_composite(base, rgba)


def _fill_crop(img: Image.Image, w: int, h: int) -> Image.Image:
    """Scale to fill then center-crop to exactly w x h (no stretch)."""
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = int(iw * scale + 0.5), int(ih * scale + 0.5)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def apply_resize(rgba: Image.Image, resize: str) -> Image.Image:
    if not resize or "x" not in resize.lower():
        return rgba
    try:
        w, h = (int(v) for v in resize.lower().split("x"))
    except ValueError:
        return rgba
    return _fill_crop(rgba, w, h)


# --------------------------------------------------------------------------- #
# Watermark
# --------------------------------------------------------------------------- #
def apply_watermark(rgba: Image.Image, path: str) -> Image.Image:
    if not path or not os.path.exists(path):
        return rgba
    wm = Image.open(path).convert("RGBA")
    target_w = int(rgba.width * 0.20)
    ratio = target_w / wm.width
    wm = wm.resize((target_w, int(wm.height * ratio)), Image.LANCZOS)
    pos = (rgba.width - wm.width - int(rgba.width * 0.02),
           rgba.height - wm.height - int(rgba.height * 0.02))
    out = rgba.copy()
    out.alpha_composite(wm, pos)
    return out


# --------------------------------------------------------------------------- #
# Full image pipeline
# --------------------------------------------------------------------------- #
def process_image(source_rgb: Image.Image, settings: Settings,
                  matte: Image.Image | None = None):
    """Return (result_image, alpha_matte). result honors all settings."""
    source_rgb = source_rgb.convert("RGB")
    if matte is None:
        matte = get_matte(source_rgb, settings)

    rgba = cutout_from_matte(source_rgb, matte)

    if settings.despill > 0:
        rgba = apply_despill(rgba, settings.despill)
    if settings.enhance:
        rgba = apply_enhance(rgba, settings.enhance_scale)

    if settings.sticker:
        rgba = apply_sticker(rgba, settings.sticker_thickness, settings.sticker_color)
    else:
        if settings.shadow > 0:
            rgba = apply_shadow(rgba, settings.shadow, settings.shadow_type)
        rgba = apply_background(rgba, settings, source_rgb)

    if settings.center:
        rgba = apply_center(rgba)
    if settings.resize:
        rgba = apply_resize(rgba, settings.resize)
    if settings.watermark:
        rgba = apply_watermark(rgba, settings.watermark)

    return rgba, matte


# --------------------------------------------------------------------------- #
# Saving: format / compression / naming / alpha mask
# --------------------------------------------------------------------------- #
def build_name(src_name: str, settings: Settings, index: int = 1) -> str:
    stem = os.path.splitext(os.path.basename(src_name))[0]
    ext = ".webp" if settings.fmt == "webp" else ".png"
    p = settings.name_pattern
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_") + f"{int(time.time()*1000)%1000:03d}"
    table = {
        "original": stem,
        "original-bg-removed": f"{stem} - bg-removed",
        "original-no-bg": f"{stem} - no-bg",
        "original-transparent": f"{stem} - transparent",
        "bg-removed-original": f"bg-removed - {stem}",
        "no-bg-original": f"no-bg - {stem}",
        "timestamp": ts,
        "timestamp-original": f"{ts} - {stem}",
        "numbered": f"{index:03d}",
        "numbered-original": f"{index:03d} - {stem}",
    }
    return table.get(p, stem) + ext


def save_output(rgba: Image.Image, out_path: str, settings: Settings,
                matte: Image.Image | None = None):
    fmt = settings.fmt
    comp = settings.compression
    img = rgba

    if fmt == "webp":
        params = {"lossless": comp in ("none", "lossless"), "quality": 90,
                  "method": 6}
        img.save(out_path, "WEBP", **params)
    else:  # PNG
        if comp == "256colors":
            img = img.convert("RGBA").quantize(colors=256, method=Image.FASTOCTREE)
            img.save(out_path, "PNG", optimize=True)
        elif comp == "128colors":
            img = img.convert("RGBA").quantize(colors=128, method=Image.FASTOCTREE)
            img.save(out_path, "PNG", optimize=True)
        elif comp == "lossless":
            # strip metadata, max optimize
            clean = Image.new("RGBA", img.size)
            clean.putdata(list(img.getdata()))
            clean.save(out_path, "PNG", optimize=True, compress_level=9)
        elif comp == "32bit":
            img.save(out_path, "PNG", optimize=True, compress_level=9)
        else:  # none
            img.save(out_path, "PNG")

    if settings.alpha_mask and matte is not None:
        mask_path = os.path.splitext(out_path)[0] + "_mask.png"
        matte.convert("L").save(mask_path, "PNG")


# --------------------------------------------------------------------------- #
# File discovery
# --------------------------------------------------------------------------- #
def discover_inputs(paths):
    """Expand files/folders into a list of (path, rel_subdir) preserving folder
    structure for batch output."""
    out = []
    for p in paths:
        if os.path.isdir(p):
            root = p
            for dirpath, _dirs, files in os.walk(p):
                rel = os.path.relpath(dirpath, root)
                rel = "" if rel == "." else rel
                for f in sorted(files):
                    if f.lower().endswith(IMAGE_EXTS + GIF_EXTS + VIDEO_EXTS):
                        out.append((os.path.join(dirpath, f), rel))
        elif os.path.isfile(p):
            if p.lower().endswith(IMAGE_EXTS + GIF_EXTS + VIDEO_EXTS):
                out.append((p, ""))
    return out


def kind_of(path: str) -> str:
    low = path.lower()
    if low.endswith(VIDEO_EXTS):
        return "video"
    if low.endswith(GIF_EXTS):
        return "gif"
    return "image"
