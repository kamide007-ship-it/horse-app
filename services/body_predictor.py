from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageEnhance


def _tint_by_coat(img: Image.Image, coat: str) -> Image.Image:
    """毛色に合わせて簡易的に色味を寄せる（UI一貫性のための軽微補正）"""
    c = (coat or "").strip()
    if not c:
        return img

    # まずコントラスト/彩度を少しだけ整える
    out = ImageEnhance.Contrast(img).enhance(1.02)
    out = ImageEnhance.Color(out).enhance(1.02)

    # 主要毛色の"色温度"だけ寄せる（過度な変換はしない）
    if c in {"栗毛", "栃栗毛", "パロミノ"}:
        out = ImageEnhance.Color(out).enhance(1.10)
    elif c in {"鹿毛", "黒鹿毛", "青鹿毛", "青毛", "バックスキン"}:
        out = ImageEnhance.Color(out).enhance(1.04)
    elif c in {"芦毛", "白毛"}:
        out = ImageEnhance.Color(out).enhance(0.85)

    return out


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

    # slight contrast/clarity + coat consistency
    grown = _tint_by_coat(grown, coat)
    grown = ImageEnhance.Sharpness(grown).enhance(1.05)

    # save
    out_name = f"pred_3yo_{src.stem}.png"
    dst = out_dir / out_name
    grown.save(dst, format="PNG")

    return str(dst.relative_to(base_dir))
