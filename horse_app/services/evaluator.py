from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Tuple

from .utils import clamp
from .keibago_fetcher import load_track_level
from .nankankeiba_loader import load_nankan_map
from .broodmare_market_loader import load_market

# =========================
# ★ / A-D
# =========================
def stars(score_1_to_5: float) -> str:
    n = int(round(clamp(score_1_to_5, 1.0, 5.0)))
    return "★" * n + "☆" * (5 - n)

def grade_from_5(score_1_to_5: float) -> str:
    s = clamp(score_1_to_5, 1.0, 5.0)
    if s >= 4.3: return "A"
    if s >= 3.6: return "B"
    if s >= 2.9: return "C"
    return "D"

# =========================
# netkeiba / jbis 実績 → 1..5
# =========================
def performance_score(metrics: Dict[str, Any]) -> float:
    win_rate = float(metrics.get("win_rate", 0.0))
    place_rate = float(metrics.get("place_rate", 0.0))
    class_index = float(metrics.get("class_index", 3.0))  # 1..5想定
    recent_form = float(metrics.get("recent_form", 0.5))  # 0..1

    s = (
        (win_rate * 5.0) * 0.35
        + (place_rate * 5.0) * 0.25
        + clamp(class_index, 1.0, 5.0) * 0.25
        + clamp(recent_form, 0.0, 1.0) * 5.0 * 0.15
    )
    return clamp(s, 1.0, 5.0)

# =========================
# Track profile
# =========================
@dataclass(frozen=True)
class TrackProfile:
    name: str
    straight: float
    turns: float
    power: float
    notes: str = ""

TRACKS: List[TrackProfile] = [
    TrackProfile("門別", 0.55, 0.65, 0.70, "小回り・パワー寄り"),
    TrackProfile("盛岡", 0.80, 0.45, 0.55, "直線長め・スピード持続"),
    TrackProfile("水沢", 0.55, 0.70, 0.75, "タイト・パワー要求"),
    TrackProfile("大井", 0.75, 0.55, 0.60, "水準高・持続力"),
    TrackProfile("川崎", 0.55, 0.80, 0.65, "タイト・先行/器用さ"),
    TrackProfile("船橋", 0.70, 0.60, 0.65, "バランス型"),
    TrackProfile("浦和", 0.45, 0.85, 0.70, "強タイト・先行/器用さ"),
    TrackProfile("金沢", 0.50, 0.75, 0.75, "タイト・パワー"),
    TrackProfile("笠松", 0.50, 0.80, 0.70, "タイト・先行力"),
    TrackProfile("名古屋", 0.55, 0.75, 0.70, "中〜高水準寄り"),
    TrackProfile("園田", 0.55, 0.75, 0.75, "パワー・タイト"),
    TrackProfile("姫路", 0.55, 0.70, 0.80, "パワー要求強"),
    TrackProfile("高知", 0.50, 0.85, 0.80, "最タイト級・パワー"),
    TrackProfile("佐賀", 0.55, 0.80, 0.75, "タイト・先行力"),
    TrackProfile("JRA", 0.85, 0.40, 0.55, "最高水準"),
]

# =========================
# Horse traits
# =========================
@dataclass(frozen=True)
class HorseTraits:
    speed: float
    stamina: float
    power: float
    agility: float
    ability: float

def traits_from_sources(
    netkeiba: Optional[dict],
    jbis: Optional[dict],
) -> Tuple[HorseTraits, bool, Optional[float]]:

    speed = stamina = agility = 0.52
    power = 0.55
    ability = 0.45

    used = False
    perf_val = None

    src = netkeiba or jbis
    if src:
        try:
            perf_val = performance_score(src)
            ability = (perf_val - 1.0) / 4.0
            used = True

            recent = float(src.get("recent_form", 0.5))
            place = float(src.get("place_rate", 0.35))
            cls = float(src.get("class_index", 3.0))

            speed = clamp(0.45 + 0.30 * recent + 0.10 * (cls - 3.0), 0.2, 0.95)
            stamina = clamp(0.45 + 0.35 * place, 0.2, 0.95)
            power = clamp(0.50 + 0.25 * ability, 0.2, 0.95)
            agility = clamp(0.50 + 0.20 * (place - 0.35), 0.2, 0.95)
        except Exception:
            pass

    return HorseTraits(speed, stamina, power, agility, ability), used, perf_val

# =========================
# suitability score
# =========================
def suitability_score(
    tr: HorseTraits,
    tp: TrackProfile,
    level_map: Dict[str, float],
    nankan_map: Dict[str, float],
    style: Optional[str],
    distance: Optional[str],
) -> Tuple[float, float]:

    level = float(level_map.get(tp.name, 0.65))
    if tp.name == "JRA":
        level = float(level_map.get("JRA", 1.10))

    need_stamina = clamp(0.4 + 0.4 * tp.straight, 0.0, 1.0)

    match = (
        (1 - abs(tr.speed - tp.straight)) * 0.30 +
        (1 - abs(tr.agility - tp.turns)) * 0.25 +
        (1 - abs(tr.power - tp.power)) * 0.25 +
        (1 - abs(tr.stamina - need_stamina)) * 0.20
    )

    difficulty = 0.60 * level + 0.15 * tp.power
    raw = 0.58 * tr.ability + 0.42 * match - 0.38 * difficulty

    score = 1.0 + 4.0 * clamp(raw, 0.0, 1.0)

    adj = 0.0
    if style and distance:
        key = f"{tp.name}|{distance}|{style}"
        adj = float(nankan_map.get(key, 0.0))
        score += adj

    return clamp(score, 1.0, 5.0), adj

# =========================
# class estimate（確定仕様）
# =========================
def class_estimate(score: float, level: float, is_jra: bool) -> str:
    adj = clamp(score - (level - 0.65), 1.0, 5.0)

    if is_jra:
        if adj >= 4.4: return "OP〜3勝C"
        if adj >= 3.8: return "2勝C"
        if adj >= 3.2: return "1勝C"
        return "未勝利〜1勝C壁"

    if adj >= 4.5: return "A1（重賞級）"
    if adj >= 4.1: return "A1（OP級）"
    if adj >= 3.7: return "A2（上位）"
    if adj >= 3.3: return "A2（下位）"
    if adj >= 3.0: return "B1（上位）"
    if adj >= 2.7: return "B1（下位）"
    if adj >= 2.4: return "B2（上位）"
    if adj >= 2.1: return "B2（下位）"
    if adj >= 1.8: return "C1（上位）"
    if adj >= 1.6: return "C1（下位）"
    return "C2（下位）"

# =========================
# evaluate track suitability（★水準補正込み）
# =========================
def evaluate_track_suitability(
    traits: HorseTraits,
    style: Optional[str],
    distance: Optional[str],
) -> dict:

    level_map = load_track_level()
    nankan_map = load_nankan_map()

    STAR_LEVEL_ADJUST = {
        "JRA": -0.6,
        "大井": -0.3, "川崎": -0.3, "船橋": -0.3, "浦和": -0.3,
        "園田": 0.0, "名古屋": 0.0, "姫路": 0.0,
        "佐賀": +0.3, "高知": +0.3, "金沢": +0.3, "笠松": +0.3,
    }

    rows, raw_map, adj_map = [], {}, {}

    for tp in TRACKS:
        level = float(level_map.get(tp.name, 0.65))
        if tp.name == "JRA":
            level = float(level_map.get("JRA", 1.10))

        s, adj = suitability_score(traits, tp, level_map, nankan_map, style, distance)

        star_score = clamp(s + STAR_LEVEL_ADJUST.get(tp.name, 0.0), 1.0, 5.0)

        raw_map[tp.name] = s
        if adj != 0.0:
            adj_map[tp.name] = adj

        rows.append({
            "track": tp.name,
            "score": round(s, 3),
            "stars": stars(star_score),
            "grade": grade_from_5(star_score),
            "class": class_estimate(s, level, is_jra=(tp.name == "JRA")),
            "notes": tp.notes + (f" / 補正{adj:+.2f}" if adj != 0.0 else ""),
        })

    return {
        "rows": sorted(rows, key=lambda r: (r["track"] == "JRA", r["track"])),
        "raw": raw_map,
        "adj": adj_map,
        "comment": (
            "競馬場形状・馬場傾向・競走水準（keiba.go.jp）と"
            "馬の特性を突合して算出。南関は脚質×距離CSVがあれば微調整。"
        ),
    }

# =========================
# broodmare / report 以下は既存のまま
# =========================
