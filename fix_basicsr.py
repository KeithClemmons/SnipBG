"""Patch basicsr's removed torchvision import so Real-ESRGAN imports on torch 2.x."""
import os, sys
try:
    import basicsr, glob
    base = os.path.dirname(basicsr.__file__)
    target = os.path.join(base, "data", "degradations.py")
    if os.path.exists(target):
        txt = open(target, encoding="utf-8").read()
        new = txt.replace(
            "from torchvision.transforms.functional_tensor import rgb_to_grayscale",
            "from torchvision.transforms.functional import rgb_to_grayscale")
        if new != txt:
            open(target, "w", encoding="utf-8").write(new)
            print("  patched", target)
        else:
            print("  no change needed")
except Exception as e:
    print("  patch skipped:", e)
