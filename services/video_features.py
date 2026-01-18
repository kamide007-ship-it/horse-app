from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def video_motion_features(video_rel: str) -> dict:
    """Compute lightweight motion/speed scores from an uploaded video.

    Heuristic:
    - Motion: average frame-to-frame pixel movement
    - Speed: motion adjusted by cadence proxy (variance)

    v1.0 deterministic; returns scores 0-100.
    """
    p = Path(__file__).resolve().parents[1] / video_rel
    if not p.exists():
        return {"motion_score": 50, "speed_score": 50, "note_ja": "動画の読込に失敗したため平均値で補完"}

    cap = cv2.VideoCapture(str(p))
    if not cap.isOpened():
        return {"motion_score": 50, "speed_score": 50, "note_ja": "動画の読込に失敗したため平均値で補完"}

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    # sample up to 24 frames evenly
    samples = min(24, max(6, frame_count // 10 if frame_count else 12))
    idxs = np.linspace(0, max(1, frame_count - 1), samples).astype(int)

    prev = None
    diffs = []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (320, 180))
        if prev is not None:
            d = cv2.absdiff(gray, prev)
            diffs.append(float(d.mean()))
        prev = gray

    cap.release()

    if not diffs:
        return {"motion_score": 50, "speed_score": 50, "note_ja": "動画から有効フレームを取得できず平均値で補完"}

    m = float(np.mean(diffs))
    v = float(np.var(diffs))

    # Normalize to 0-100 with soft caps
    motion = max(35.0, min(90.0, (m / 10.0) * 100.0))
    speed = max(35.0, min(90.0, (m / 10.0) * 85.0 + (v / 30.0) * 15.0))

    note = "動画（歩様/キャンター）から推進量と安定性を算出し補正を適用"
    return {"motion_score": round(motion), "speed_score": round(speed), "note_ja": note}
