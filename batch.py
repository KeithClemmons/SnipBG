"""Shared batch runner used by both the GUI and the CLI."""

import os

from PIL import Image

import core
import video as videomod


def default_output_dir():
    return os.path.join(os.path.expanduser("~"), "Downloads", "background-remover-output")


def run_batch(inputs, output_dir, settings, on_status=None, on_item=None):
    """inputs: list of (path, rel_subdir). Returns list of output paths.

    on_status(text) and on_item(done, total, out_path|None) are optional callbacks.
    Subfolder structure is preserved under output_dir.
    """
    items = core.discover_inputs([p for p, _ in inputs]) if inputs and isinstance(inputs[0], str) \
        else inputs
    os.makedirs(output_dir, exist_ok=True)
    results = []
    total = len(items)

    for i, (path, rel) in enumerate(items, 1):
        sub_out = os.path.join(output_dir, rel) if rel else output_dir
        os.makedirs(sub_out, exist_ok=True)
        kind = core.kind_of(path)
        name = core.build_name(path, settings, index=i)
        out_path = os.path.join(sub_out, name)
        if on_status:
            on_status(f"Processing {os.path.basename(path)} ({i}/{total})")
        try:
            if kind == "image":
                src = Image.open(path)
                rgba, matte = core.process_image(src, settings)
                core.save_output(rgba, out_path, settings, matte)
            elif kind == "gif":
                out_path = videomod.process_gif(path, out_path, settings)
            else:  # video
                out_path = videomod.process_video(path, out_path, settings)
            results.append(out_path)
            if on_item:
                on_item(i, total, out_path)
        except Exception as e:
            if on_status:
                on_status(f"Failed on {os.path.basename(path)}: {e}")
            if on_item:
                on_item(i, total, None)
    return results
