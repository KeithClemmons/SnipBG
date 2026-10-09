"""
SnipBG command line interface — mirrors the LocalBG CLI.

Examples:
    python cli.py photo.jpg -o ./output
    python cli.py ./photos -o ./output --background white --compression lossless
    python cli.py portrait.jpg -o ./output --background blur --blur-strength 70
    python cli.py logo.png -o ./output --sticker --sticker-color black
    python cli.py video.mp4 -o ./output --video-speed 2 --video-format mov-prores
"""

import argparse
import sys

import core
import batch


def build_parser():
    p = argparse.ArgumentParser(prog="snipbg", description="Local background remover (InSPyReNet).")
    p.add_argument("input", nargs="+", help="Input files or folders")
    p.add_argument("-o", "--output", required=True, help="Output directory")
    p.add_argument("--background", default="transparent",
                   choices=["transparent", "black", "white", "blur", "image", "custom"])
    p.add_argument("--bg-color", default="#ffffff", help="Hex color for custom background")
    p.add_argument("--bg-image", default="", help="Path to background image")
    p.add_argument("--blur-strength", type=int, default=50)
    p.add_argument("--gpu", action="store_true")
    p.add_argument("--compression", default="none",
                   choices=["none", "lossless", "32bit", "256colors", "128colors"])
    p.add_argument("--resize", default="", help="WIDTHxHEIGHT, e.g. 1920x1080")
    p.add_argument("--video-speed", type=int, default=1, choices=[1, 2, 3, 4])
    p.add_argument("--enhance", action="store_true")
    p.add_argument("--enhance-scale", type=int, default=2, choices=[2, 3, 4])
    p.add_argument("--sticker", action="store_true")
    p.add_argument("--sticker-thickness", type=int, default=16)
    p.add_argument("--sticker-color", default="white", choices=["white", "black", "gray"])
    p.add_argument("--shadow", type=int, default=0)
    p.add_argument("--shadow-type", default="classic", choices=["classic", "gimp-style", "soft"])
    p.add_argument("--despill", type=int, default=0)
    p.add_argument("--video-format", default="mov-prores", choices=["mov-prores", "mp4"])
    p.add_argument("--center", action="store_true")
    p.add_argument("--alpha-mask", action="store_true")
    p.add_argument("--format", default="png", choices=["png", "webp"])
    p.add_argument("--name-pattern", default="original")
    p.add_argument("--watermark", default="")
    p.add_argument("--fast", action="store_true", help="Use the fast (lower quality) model")
    return p


def args_to_settings(a) -> core.Settings:
    return core.Settings(
        quality="fast" if a.fast else "base",
        gpu=a.gpu,
        background=a.background,
        bg_color=a.bg_color,
        bg_image=a.bg_image,
        blur_strength=a.blur_strength,
        despill=a.despill,
        enhance=a.enhance,
        enhance_scale=a.enhance_scale,
        resize=a.resize,
        sticker=a.sticker,
        sticker_thickness=a.sticker_thickness,
        sticker_color=a.sticker_color,
        shadow=a.shadow,
        shadow_type=a.shadow_type,
        center=a.center,
        fmt=a.format,
        compression=a.compression,
        name_pattern=a.name_pattern,
        alpha_mask=a.alpha_mask,
        watermark=a.watermark,
        video_speed=a.video_speed,
        video_format=a.video_format,
    )


def main(argv=None):
    a = build_parser().parse_args(argv)
    settings = args_to_settings(a)
    items = core.discover_inputs(a.input)
    if not items:
        print("No supported input files found.", file=sys.stderr)
        return 1
    print(f"Processing {len(items)} file(s) -> {a.output}")

    def status(msg):
        print("  " + msg)

    results = batch.run_batch(items, a.output, settings, on_status=status)
    print(f"Done. {len(results)} file(s) written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
