from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict

from services.image_features import image_body_feature
from services.video_features import video_motion_features
from services.utils import clamp01, safe_float


def _age_months(dob_iso: str) -> float | None:
    try:
        dob = datetime.strptime(dob_iso, "%Y-%m-%d")
    except Exception:
        return None
    now = datetime.utcnow()
    return max(0.0, (now.year - dob.year) * 12 + (now.month - dob.month) + (now.day - dob.day)/30.0)


def _expected_weight_kg(age_months: float, sex: str) -> float:
    """Rough expected weight by age. Heuristic baseline used for BodyIndex.
    This does not replace a proper population model.
    """
    # Simple piecewise growth curve (yearling ~ 420-470, 2yo ~ 480-520, 3yo ~ 500-560)
    # Scale by sex slightly.
    base = 350.0 + 10.0 * min(age_months, 18)  # up to 18m
    if age_months > 18:
        base += 6.0 * min(age_months - 18, 12)
    if age_months > 30:
        base += 3.0 * min(age_months - 30, 18)
    sex = (sex or "").lower()
    if "牝" in sex or sex in ("filly", "mare", "f"):
        base -= 15.0
    return clamp01(base / 600.0) * 600.0


def evaluate_horse(payload: Dict[str, Any], side_photo_rel: str | None, video_rel: str | None) -> Dict[str, Any]:
    """Return scores + explanation in a UI-ready shape.

    Scores are 0-100. Japanese text is primary; English is small.
    """
    age_m = _age_months(payload.get("dob", ""))
    bw = safe_float(payload.get("body_weight"))

    # --- BodyIndex (0-100) ---
    body_index = 50.0
    body_notes = []
    if age_m is not None and bw is not None:
        exp = _expected_weight_kg(age_m, payload.get("sex", ""))
        diff = bw - exp
        # within +/-30kg is good; outside reduces
        body_index = 75.0 - (abs(diff) / 30.0) * 15.0
        body_index = max(35.0, min(90.0, body_index))
        if diff >= 0:
            body_notes.append(f"月齢比で馬体重が+{diff:.0f}kg（成長良好）")
        else:
            body_notes.append(f"月齢比で馬体重が{diff:.0f}kg（成長は平均〜やや控えめ）")
    else:
        body_notes.append("体重または生年月日が未入力のため、平均値で補完")

    # --- Photo feature (0-100) ---
    photo_index = 50.0
    photo_notes = []
    if side_photo_rel:
        feat = image_body_feature(side_photo_rel)
        photo_index = float(feat["score"])
        photo_notes.append(feat["note_ja"])
    else:
        photo_notes.append("側面写真が未入力のため、写真補正なし")

    # --- Video features: Motion & Speed ---
    motion_index = 50.0
    speed_index = 50.0
    video_notes = []
    if video_rel:
        vf = video_motion_features(video_rel)
        motion_index = float(vf["motion_score"])
        speed_index = float(vf["speed_score"])
        video_notes.append(vf["note_ja"])
    else:
        video_notes.append("動画が未入力のため、動画補正なし")

    # --- PedigreeIndex (0-100) heuristic ---
    sire = (payload.get("sire") or "").strip()
    damsire = (payload.get("damsire") or "").strip()
    pedigree_index = 55.0
    ped_notes = []

    def sire_base(name: str) -> float:
        if "オールザベスト" in name:
            return 65.0
        if "アジアエクスプレス" in name:
            return 62.0
        if "エスケンデレヤ" in name:
            return 60.0
        return 55.0

    pedigree_index = sire_base(sire)
    if "サウスヴィグラス" in damsire:
        pedigree_index += 3.0
        ped_notes.append("母父サウスヴィグラス補正（ダート先行力）")
    ped_notes.append("血統は市場/実績データの追加で自動更新される設計")
    pedigree_index = max(40.0, min(85.0, pedigree_index))

    # --- MarketIndex placeholder (0-100): set later by market service in UI ---
    market_index = 50.0

    # --- Compose domain traits (0-100) ---
    # Power: body + photo, Speed: speed + pedigree, Elasticity: motion + photo, Stability: motion + body, Efficiency: speed + motion
    power = 0.55 * body_index + 0.45 * photo_index
    speed = 0.60 * speed_index + 0.40 * pedigree_index
    elasticity = 0.55 * motion_index + 0.45 * photo_index
    stability = 0.55 * motion_index + 0.45 * body_index
    efficiency = 0.55 * speed_index + 0.45 * motion_index

    # --- TotalScore (fixed weights) ---
    total = 0.25 * (0.5 * body_index + 0.5 * photo_index) + 0.30 * motion_index + 0.20 * speed_index + 0.15 * pedigree_index + 0.10 * market_index

    # Round
    def r(x: float) -> int:
        return int(round(max(0.0, min(100.0, x))))

    total_i = r(total)

    def rank(score: int) -> str:
        if score >= 85:
            return "A+"
        if score >= 75:
            return "A"
        if score >= 65:
            return "B"
        if score >= 55:
            return "C"
        return "D"

    rk = rank(total_i)

    # --- Style (dirt/turf guess) ---
    # Heuristic: higher power+stability => dirt, higher speed+elasticity => turf
    dirtness = (power + stability) - (speed + elasticity)
    surface_ja = "ダート寄り" if dirtness > 2.0 else "芝寄り" if dirtness < -2.0 else "中間（両対応）"

    # --- Explanation (Japanese main, English sub) ---
    reason_ja = "／".join([body_notes[0], photo_notes[0], (video_notes[0] if video_notes else "")]).strip("／")
    reason_en = "Body/Photo/Video factors applied (missing inputs are filled with averages)."

    return {
        "total": total_i,
        "rank": rk,
        "surface": {"ja": surface_ja, "en": "Dirt/Turf tendency"},
        "traits": {
            "power": r(power),
            "speed": r(speed),
            "elasticity": r(elasticity),
            "stability": r(stability),
            "efficiency": r(efficiency),
        },
        "components": {
            "body": r(body_index),
            "photo": r(photo_index),
            "motion": r(motion_index),
            "speed": r(speed_index),
            "pedigree": r(pedigree_index),
            "market": r(market_index),
        },
        "reason": {"ja": reason_ja, "en": reason_en},
        "notes": {
            "body": body_notes,
            "photo": photo_notes,
            "video": video_notes,
            "pedigree": ped_notes,
        },
    }
