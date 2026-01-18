from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageEnhance


def make_3yo_prediction_image(side_photo_rel: str, coat: str) -> str | None:
    """Generate a "3yo body" image based on the original side photo.

    v1.0 policy:
    - MUST keep the same horse appearance (coat & markings)
    - apply only mild growth-like geometric transforms (length/height)

    Returns relative path under static/generated.
    """
    base_dir = Path(__file__).resolve().parents[1]
    src = base_dir / side_photo_rel
    if not src.exists():
        return None

    out_dir = base_dir / "static" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)

    im = Image.open(src).convert("RGB")

    # mild growth transform: stretch horizontally + a little vertically
    w, h = im.size
    new_w = int(w * 1.06)
    new_h = int(h * 1.02)
    grown = im.resize((new_w, new_h), resample=Image.BICUBIC)

    # center-crop back to original size to keep framing consistent
    left = max(0, (new_w - w) // 2)
    top = max(0, (new_h - h) // 2)
    grown = grown.crop((left, top, left + w, top + h))

    # slight contrast/clarity
    grown = ImageEnhance.Contrast(grown).enhance(1.03)
    grown = ImageEnhance.Sharpness(grown).enhance(1.05)

    # save
    out_name = f"pred_3yo_{src.stem}.png"
    dst = out_dir / out_name
    grown.save(dst, format="PNG")

    return str(dst.relative_to(base_dir))
