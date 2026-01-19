from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def image_body_feature(side_photo_rel: str) -> dict:
    """Compute a lightweight photo-based score from the uploaded side photo.

    NOTE: This is a heuristic (v1.0). It is deterministic and always returns a score.
    """
    p = Path(__file__).resolve().parents[1] / side_photo_rel
    if not p.exists():
        return {"score": 50, "note_ja": "側面写真の読込に失敗したため平均値で補完"}

    img = cv2.imread(str(p))
    if img is None:
        return {"score": 50, "note_ja": "側面写真の読込に失敗したため平均値で補完"}

    h, w = img.shape[:2]
    # sharpness
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sharp_score = min(100.0, max(0.0, (sharp / 200.0) * 100.0))

    # estimate foreground extent using edges (very rough)
    edges = cv2.Canny(gray, 60, 180)
    fg = float((edges > 0).sum()) / float(h * w)
    # good photos tend to have a medium amount of edge pixels; too low => blurry/underexposed, too high => noisy
    fg_score = 100.0 - min(60.0, abs(fg - 0.08) * 600.0)

    # aspect ratio preference: side photo typically wide
    ar = w / max(1.0, h)
    ar_score = 100.0 - min(50.0, abs(ar - 1.6) * 35.0)

    score = 0.45 * sharp_score + 0.35 * fg_score + 0.20 * ar_score
    score = float(max(35.0, min(90.0, score)))

    note = "側面写真の鮮明度と輪郭情報から馬体補正を適用"
    return {"score": round(score), "note_ja": note}
