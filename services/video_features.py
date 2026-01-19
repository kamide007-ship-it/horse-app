from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

# iPhone動画(HEVC)などで OpenCV が読めないケースがあるため
# imageio(同梱ffmpeg)でフォールバックします。
try:
    import imageio.v3 as iio  # type: ignore
except Exception:  # pragma: no cover
    iio = None  # type: ignore


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, x)))


def _pack(motion: float, speed: float, var: float, note_ja: str) -> dict:
    """Return a stable, backward-compatible payload.

    Existing keys (kept):
      - motion_score
      - speed_score

    New keys:
      - accel_score: 瞬発力の代理指標（変化量/分散を加点）
      - stability_score: 安定性の代理指標（分散が小さいほど高い）
      - volatility: ばらつき（0-100）
    """
    # var は動画の「変化量の分散」: 大きいほどメリハリがある一方、不安定さも増える
    # ここでは「瞬発力」と「安定性」を両立させるため、別指標として切り出す。
    volatility = _clamp((var / 30.0) * 100.0, 0.0, 100.0)
    accel = _clamp(40.0 + 0.55 * volatility, 35.0, 90.0)
    stability = _clamp(90.0 - 0.70 * volatility, 35.0, 90.0)

    return {
        "motion_score": int(round(_clamp(motion, 0.0, 100.0))),
        "speed_score": int(round(_clamp(speed, 0.0, 100.0))),
        "accel_score": int(round(accel)),
        "stability_score": int(round(stability)),
        "volatility": int(round(volatility)),
        "note_ja": note_ja,
    }


def _video_motion_features_imageio(path: str, samples: int = 24) -> dict:
    if iio is None:
        return _pack(50, 50, 0, "動画の読込に失敗したため平均値で補完")

    try:
        # index=None で全フレーム; heavyなので均等サンプリング
        frames = []
        for _, frame in enumerate(iio.imiter(path)):
            frames.append(frame)
            if len(frames) >= 240:  # hard cap
                break
        if len(frames) < 3:
            return _pack(50, 50, 0, "動画から有効フレームを取得できず平均値で補完")

        idxs = np.linspace(0, len(frames) - 1, min(samples, len(frames))).astype(int)
        prev = None
        diffs = []
        for i in idxs:
            f = frames[int(i)]
            gray = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) if f.ndim == 3 else f
            gray = cv2.resize(gray, (320, 180))
            if prev is not None:
                d = cv2.absdiff(gray, prev)
                diffs.append(float(d.mean()))
            prev = gray

        if not diffs:
            return _pack(50, 50, 0, "動画から有効フレームを取得できず平均値で補完")

        m = float(np.mean(diffs))
        v = float(np.var(diffs))

        # Normalize to 0-100 with soft caps
        motion = max(35.0, min(90.0, (m / 10.0) * 100.0))
        speed = max(35.0, min(90.0, (m / 10.0) * 85.0 + (v / 30.0) * 15.0))

        note = "動画（歩様/キャンター）から推進量・瞬発・安定性を算出（imageio）"
        return _pack(motion, speed, v, note)
    except Exception:
        return _pack(50, 50, 0, "動画の読込に失敗したため平均値で補完")


def video_motion_features(video_rel: str) -> dict:
    """Compute lightweight motion/speed/accel/stability scores from an uploaded video.

    Heuristic (deterministic):
    - Motion: average frame-to-frame pixel movement
    - Speed: motion adjusted by cadence proxy (variance)
    - Acceleration: variance-derived proxy
    - Stability: inverse variance-derived proxy
    """
    p = Path(__file__).resolve().parents[1] / video_rel
    if not p.exists():
        return _pack(50, 50, 0, "動画の読込に失敗したため平均値で補完")

    cap = cv2.VideoCapture(str(p))
    if not cap.isOpened():
        # OpenCV が開けない（HEVC等）場合は imageio でフォールバック
        return _video_motion_features_imageio(str(p))

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
        # OpenCVでフレーム取得できない/差分が取れない場合もフォールバック
        return _video_motion_features_imageio(str(p))

    m = float(np.mean(diffs))
    v = float(np.var(diffs))

    # Normalize to 0-100 with soft caps
    motion = max(35.0, min(90.0, (m / 10.0) * 100.0))
    speed = max(35.0, min(90.0, (m / 10.0) * 85.0 + (v / 30.0) * 15.0))

    note = "動画（歩様/キャンター）から推進量・瞬発・安定性を算出"
    return _pack(motion, speed, v, note)
