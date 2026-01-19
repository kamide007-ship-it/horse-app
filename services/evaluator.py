from __future__ import annotations

import math
from typing import Any, Dict, Tuple

from services.image_features import image_body_feature
from services.video_features import video_motion_features


# ============================================================
# Equine Vet Synapse - Horse Ability Model (Locked)
#
# ...


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, x)))


def _sigmoid(x: float) -> float:
    # numerically stable enough for our range
    return 1.0 / (1.0 + math.exp(-x))


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        s = str(v).strip()
        if not s:
            return default
        return float(s)
    except Exception:
        return default


def _rank_from_ability(ability: float) -> str:
    a = float(ability)
    if a >= 82:
        return "A"
    if a >= 72:
        return "B"
    if a >= 62:
        return "C"
    return "D"


def _stars_from_ability(ability: float) -> str:
    a = float(ability)
    # 1-5 stars
    if a >= 85:
        n = 5
    elif a >= 78:
        n = 4
    elif a >= 70:
        n = 3
    elif a >= 62:
        n = 2
    else:
        n = 1
    return "★" * n + "☆" * (5 - n)


def _distance_bucket(distance_m: float) -> Tuple[str, float]:
    """Return (bucket_name, shortness_0_1).

    shortness: 1 => sprint, 0 => staying
    """
    d = float(distance_m or 0.0)
    if d <= 0:
        d = 1600.0

    # Map 1000m -> ~1.0, 2200m -> ~0.0
    d_km = d / 1000.0
    shortness = _clamp((2.2 - d_km) / 1.2, 0.0, 1.0)

    if d <= 1400:
        return "Sprint", shortness
    if d <= 2000:
        return "Mile", shortness
    return "Stayer", shortness


def _derive_traits(
    body_index: float,
    photo_index: float,
    motion_index: float,
    speed_index: float,
    pedigree_index: float,
    accel_index: float,
    stability_index: float,
    distance_m: float,
) -> Dict[str, float]:
    """Derive 7 traits (0-100) from intermediate indices."""

    bucket, shortness = _distance_bucket(distance_m)

    # Base traits (0-100)
    speed = _clamp(0.60 * speed_index + 0.15 * pedigree_index + 0.25 * motion_index, 35, 90)
    power = _clamp(0.55 * body_index + 0.25 * photo_index + 0.20 * pedigree_index, 35, 90)

    # Stamina: distance & physique / rhythm
    stamina = _clamp(
        0.40 * motion_index + 0.35 * body_index + 0.25 * pedigree_index + (1.0 - shortness) * 8.0,
        35,
        90,
    )

    durability = _clamp(0.45 * photo_index + 0.35 * body_index + 0.20 * stability_index, 35, 90)

    # Risk increases when stability is low and volatility is high
    risk = _clamp(100.0 - (0.65 * stability_index + 0.35 * durability), 10, 80)

    acceleration = _clamp(0.55 * accel_index + 0.30 * speed + 0.15 * motion_index, 35, 90)
    stability = _clamp(0.70 * stability_index + 0.20 * durability + 0.10 * (100.0 - risk), 35, 90)

    # slight distance-aware nudges (kept mild)
    if bucket == "Sprint":
        speed = _clamp(speed + 2.0, 35, 90)
        acceleration = _clamp(acceleration + 2.0, 35, 90)
    elif bucket == "Stayer":
        stamina = _clamp(stamina + 2.0, 35, 90)
        durability = _clamp(durability + 1.0, 35, 90)

    return {
        "Speed": float(round(speed)),
        "Power": float(round(power)),
        "Stamina": float(round(stamina)),
        "Durability": float(round(durability)),
        "Risk": float(round(risk)),
        "Acceleration": float(round(acceleration)),
        "Stability": float(round(stability)),
    }


def _ability_from_traits(traits: Dict[str, float], distance_m: float) -> Dict[str, float]:
    """Locked ability formula (0-100).

    - turfiness = sigmoid(k*(Speed-Power))
    - Speed* = 0.75*Speed + 0.25*Acceleration
    - Risk*  = 0.70*Risk  + 0.30*(100-Stability)
    - Ability = α(d,t)*Speed* + (1-α(d,t))*Stamina + λ*Durability - ρ*Risk*
    """
    speed = float(traits["Speed"])
    power = float(traits["Power"])
    stamina = float(traits["Stamina"])
    durability = float(traits["Durability"])
    risk = float(traits["Risk"])
    accel = float(traits["Acceleration"])
    stability = float(traits["Stability"])

    # turfiness in [0,1]
    k = 0.085
    turfiness = _sigmoid(k * (speed - power))

    # distance effect: sprint -> alpha high, staying -> low
    _, shortness = _distance_bucket(distance_m)
    alpha = 0.35 + 0.45 * shortness + 0.10 * (turfiness - 0.5) * 2.0
    alpha = float(_clamp(alpha, 0.30, 0.90))

    speed_star = 0.75 * speed + 0.25 * accel
    risk_star = 0.70 * risk + 0.30 * (100.0 - stability)

    lam = 0.10
    rho = 0.18

    ability = alpha * speed_star + (1.0 - alpha) * stamina + lam * durability - rho * risk_star
    ability = float(_clamp(ability, 1.0, 99.0))

    return {
        "Ability": float(round(ability, 2)),
        "alpha": float(round(alpha, 3)),
        "turfiness": float(round(turfiness, 3)),
        "speed_star": float(round(speed_star, 2)),
        "risk_star": float(round(risk_star, 2)),
    }


def _surface_text(turfiness: float, speed: float, power: float) -> Dict[str, str]:
    """Never hard-assert turf/dirt; show tendency."""
    t = float(turfiness)
    if t >= 0.68:
        ja = "芝寄り（軽い走り・スピード優位）"
        en = "Turf-leaning (light, speed-first)"
    elif t <= 0.42:
        ja = "ダート寄り（パワー優位・重い走り）"
        en = "Dirt-leaning (power-first)"
    else:
        ja = "中間（条件次第で両対応）"
        en = "Neutral (condition-dependent)"

    # add a short reason
    diff = speed - power
    if diff >= 12:
        r_ja = "Speed > Power が大きく、軽い走りの傾向"
        r_en = "Speed exceeds Power → lighter action"
    elif diff <= -12:
        r_ja = "Power > Speed が大きく、押しの強い走りの傾向"
        r_en = "Power exceeds Speed → stronger pushing action"
    else:
        r_ja = "Speed と Power が拮抗し、馬場適性は調教/条件で振れる"
        r_en = "Speed and Power are close → surface can swing with setup"

    return {"ja": ja, "en": en, "reason_ja": r_ja, "reason_en": r_en}


def _comment_blocks(traits: Dict[str, float], ability: float, turfiness: float) -> Dict[str, str]:
    """Case-by-case comments (Japanese main, English small)."""

    speed = traits["Speed"]
    power = traits["Power"]
    stamina = traits["Stamina"]
    durability = traits["Durability"]
    accel = traits["Acceleration"]
    stability = traits["Stability"]
    risk = traits["Risk"]

    # Main pattern selection
    # C = sprint speed, P = power dirt, S = stamina router, B = balanced
    if speed >= 78 and accel >= 75 and power < 72:
        kind = "C"
        ja = "スピードと瞬発力が強く、反応が速いタイプ。短〜マイルで前進気勢を活かすと良い。"
        en = "Speed/accel type; best used where quick response matters."
    elif power >= 78 and stability >= 70 and speed < 74:
        kind = "P"
        ja = "パワーで押し切る走りが武器。砂や重い馬場で性能が出やすい。"
        en = "Power type; tends to show on heavier surfaces."
    elif stamina >= 78 and durability >= 72:
        kind = "S"
        ja = "持続力と体の強さが目立つ。距離を延ばして良さが出る可能性。"
        en = "Stamina/durability type; can improve with distance."
    else:
        kind = "B"
        ja = "バランス型。条件（馬場/距離/展開）で上振れしやすく、調整次第で伸びしろ。"
        en = "Balanced; performance can swing with setup and conditioning."

    # Add risk/stability note
    if risk >= 65 or stability <= 55:
        ja += " ただし安定性に課題が出やすいので、調教負荷とケアの管理が重要。"
        en += " Watch stability/risk; manage load and care."
    elif stability >= 75 and risk <= 40:
        ja += " 安定性が高く、再現性のある走りが期待できる。"
        en += " High stability; repeatable performance likely."

    # Surface tendency
    st = _surface_text(turfiness, speed, power)
    ja += f"（適性傾向：{st['ja']}）"
    en += f" ({st['en']})"

    return {
        "pattern": kind,
        "ja": ja,
        "en": en,
        "surface_ja": st["ja"],
        "surface_en": st["en"],
        "surface_reason_ja": st["reason_ja"],
        "surface_reason_en": st["reason_en"],
    }


def evaluate_horse(payload: dict, side_photo_rel: str | None, video_rel: str | None) -> dict:
    """Main entry.

    Inputs:
      - payload: form inputs
      - side_photo_rel / video_rel: relative paths
    """

    # -------------------------
    # Intermediate indices
    # -------------------------
    bw = _as_float(payload.get("body_weight"), 0.0)
    height = _as_float(payload.get("height"), 0.0)
    girth = _as_float(payload.get("girth"), 0.0)
    cannon = _as_float(payload.get("cannon"), 0.0)
    distance_m = _as_float(payload.get("distance_m"), 1600.0)

    # Body index from measurements (if missing -> neutral)
    body_index = 50.0
    body_note = "測尺が未入力のため平均補完"
    used_measure = 0
    if bw > 0:
        used_measure += 1
    if height > 0:
        used_measure += 1
    if girth > 0:
        used_measure += 1
    if cannon > 0:
        used_measure += 1

    if used_measure:
        # Normalize around typical 2yo/3yo ranges; keep mild
        bw_s = _clamp((bw - 380.0) / 2.0 + 50.0, 35, 90) if bw > 0 else 50.0
        ht_s = _clamp((height - 150.0) * 2.0 + 50.0, 35, 90) if height > 0 else 50.0
        gi_s = _clamp((girth - 170.0) * 1.5 + 50.0, 35, 90) if girth > 0 else 50.0
        ca_s = _clamp((cannon - 19.0) * 6.0 + 50.0, 35, 90) if cannon > 0 else 50.0
        body_index = float(round(0.45 * bw_s + 0.20 * ht_s + 0.20 * gi_s + 0.15 * ca_s, 2))
        body_note = "馬体重/測尺から骨格とパワー要素を補正"

    # Photo index
    photo_index = 50.0
    photo_note = "側面写真が未添付のため平均補完"
    if side_photo_rel:
        ph = image_body_feature(side_photo_rel)
        photo_index = float(ph.get("score", 50))
        photo_note = str(ph.get("note_ja", "側面写真から補正"))

    # Video indices
    motion_index = 50.0
    speed_index = 50.0
    accel_index = 50.0
    stability_index = 50.0
    video_note = "動画が未添付のため平均補完"
    if video_rel:
        vf = video_motion_features(video_rel)
        motion_index = float(vf.get("motion_score", 50))
        speed_index = float(vf.get("speed_score", 50))
        accel_index = float(vf.get("accel_score", 50))
        stability_index = float(vf.get("stability_score", 50))
        video_note = str(vf.get("note_ja", "動画から補正"))

    # Pedigree index (v1.0: light rule-based prior; deterministic)
    sire = (payload.get("sire") or "").strip()
    damsire = (payload.get("damsire") or "").strip()
    pedigree_index = 50.0
    ped_note = "血統は簡易事前分布（v1.0）"
    # Known speed lines (very light bias)
    speed_hints = {"Speightstown", "スパイツタウン", "エスケンデレヤ", "Eskendereya"}
    power_hints = {"サウスヴィグラス", "South Vigorous", "アジアエクスプレス", "Asia Express"}
    if sire in speed_hints:
        pedigree_index += 6.0
        ped_note = "父系からスピード寄りの事前補正"
    if damsire in power_hints:
        pedigree_index += 4.0
        ped_note = "母父からパワー寄りの事前補正"
    pedigree_index = _clamp(pedigree_index, 40, 75)

    # -------------------------
    # Traits & Ability
    # -------------------------
    traits = _derive_traits(
        body_index=body_index,
        photo_index=photo_index,
        motion_index=motion_index,
        speed_index=speed_index,
        pedigree_index=pedigree_index,
        accel_index=accel_index,
        stability_index=stability_index,
        distance_m=distance_m,
    )

    ability_pack = _ability_from_traits(traits, distance_m=distance_m)
    ability = float(ability_pack["Ability"])
    rank = _rank_from_ability(ability)
    stars = _stars_from_ability(ability)

    # Comment blocks
    comments = _comment_blocks(traits, ability, ability_pack["turfiness"])

    # Confidence: how many strong inputs present
    conf = 0.45
    if side_photo_rel:
        conf += 0.20
    if video_rel:
        conf += 0.20
    conf += min(0.15, 0.05 * used_measure)
    conf = float(_clamp(conf, 0.30, 0.95))

    # Display list (JA main)
    traits_display = [
        {"key": "Speed", "label_ja": "スピード", "label_en": "Speed", "value": int(traits["Speed"])},
        {"key": "Power", "label_ja": "パワー", "label_en": "Power", "value": int(traits["Power"])},
        {"key": "Stamina", "label_ja": "スタミナ", "label_en": "Stamina", "value": int(traits["Stamina"])},
        {"key": "Durability", "label_ja": "耐久", "label_en": "Durability", "value": int(traits["Durability"])},
        {"key": "Risk", "label_ja": "リスク", "label_en": "Risk", "value": int(traits["Risk"])},
        {"key": "Acceleration", "label_ja": "瞬発力", "label_en": "Acceleration", "value": int(traits["Acceleration"])},
        {"key": "Stability", "label_ja": "安定性", "label_en": "Stability", "value": int(traits["Stability"])},
    ]

    return {
        "algo_version": "EVS-Ability-v1.0-Locked",
        "total": int(round(ability)),
        "rank": rank,
        "stars": stars,
        "confidence": round(conf, 2),
        "ability": ability_pack,
        "surface": {"ja": comments["surface_ja"], "en": comments["surface_en"]},
        "reason": {"ja": comments["surface_reason_ja"], "en": comments["surface_reason_en"]},
        "comment": {"ja": comments["ja"], "en": comments["en"], "pattern": comments["pattern"]},
        "traits": traits,
        "traits_display": traits_display,
        "notes": {
            "body": [body_note],
            "photo": [photo_note],
            "video": [video_note],
            "pedigree": [ped_note],
        },
        "debug": {
            "distance_m": distance_m,
            "indices": {
                "body_index": round(body_index, 2),
                "photo_index": round(photo_index, 2),
                "motion_index": round(motion_index, 2),
                "speed_index": round(speed_index, 2),
                "accel_index": round(accel_index, 2),
                "stability_index": round(stability_index, 2),
                "pedigree_index": round(pedigree_index, 2),
            },
        },
    }
