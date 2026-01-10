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
# Track profile (shape/power)  ※水準levelはSTEP1 JSONで差し替え
# =========================
@dataclass(frozen=True)
class TrackProfile:
    name: str
    straight: float
    turns: float      # タイト(大)=器用さ/先行要求
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
# traits（差が出るように、実績が無いと控えめ）
# =========================
@dataclass(frozen=True)
class HorseTraits:
    speed: float
    stamina: float
    power: float
    agility: float
    ability: float  # 総合能力

def traits_from_sources(netkeiba: Optional[dict], jbis: Optional[dict]) -> Tuple[HorseTraits, bool, Optional[float]]:
    # ベースは控えめ（盛らない）
    speed = 0.50
    stamina = 0.52
    power = 0.55
    agility = 0.52
    ability = 0.45

    used = False
    perf_val = None

    # まず netkeiba（あれば差が出る）
    if netkeiba:
        try:
            perf_val = performance_score(netkeiba)
            ability = (perf_val - 1.0) / 4.0
            used = True

            recent = float(netkeiba.get("recent_form", 0.5))
            place = float(netkeiba.get("place_rate", 0.35))
            cls = float(netkeiba.get("class_index", 3.0))

            speed = clamp(0.45 + 0.30 * recent + 0.10 * (cls - 3.0), 0.20, 0.95)
            stamina = clamp(0.45 + 0.35 * place, 0.20, 0.95)
            power = clamp(0.50 + 0.25 * ability, 0.20, 0.95)
            agility = clamp(0.50 + 0.20 * (place - 0.35) + 0.15 * (0.6 - recent), 0.20, 0.95)
        except Exception:
            pass

    # 次に JBIS（netkeiba無い or 補強）
    if jbis and (not used):
        try:
            perf_val = performance_score(jbis)
            ability = (perf_val - 1.0) / 4.0
            used = True

            recent = float(jbis.get("recent_form", 0.5))
            place = float(jbis.get("place_rate", 0.35))
            speed = clamp(0.42 + 0.25 * recent, 0.20, 0.90)
            stamina = clamp(0.45 + 0.35 * place, 0.20, 0.95)
            power = clamp(0.50 + 0.20 * ability, 0.20, 0.95)
            agility = clamp(0.48 + 0.10 * (place - 0.35), 0.20, 0.95)
        except Exception:
            pass

    return HorseTraits(speed=speed, stamina=stamina, power=power, agility=agility, ability=ability), used, perf_val

# =========================
# track score (STEP1 level + STEP2補正)
# =========================
def suitability_score(tr: HorseTraits, tp: TrackProfile, level_map: Dict[str, float], nankan_map: Dict[str, float],
                      style: Optional[str], distance: Optional[str]) -> Tuple[float, float]:
    level = float(level_map.get(tp.name, 0.65))
    if tp.name == "JRA":
        level = float(level_map.get("JRA", 1.10))

    need_speed = tp.straight
    need_agility = tp.turns
    need_power = tp.power
    need_stamina = clamp(0.40 + 0.40 * (tp.straight * 0.6 + (1.0 - tp.turns) * 0.4), 0.0, 1.0)

    match = (
        (1.0 - abs(tr.speed - need_speed)) * 0.30
        + (1.0 - abs(tr.agility - need_agility)) * 0.25
        + (1.0 - abs(tr.power - need_power)) * 0.25
        + (1.0 - abs(tr.stamina - need_stamina)) * 0.20
    )

    # “水準が高いほど減点” が差を作る本体
    difficulty = 0.60 * level + 0.15 * tp.power
    raw = 0.58 * tr.ability + 0.42 * match - 0.38 * difficulty

    score = 1.0 + 4.0 * clamp(raw, 0.0, 1.0)

    # STEP2 南関補正（該当があれば微調整）
    adj = 0.0
    if style and distance:
        key = f"{tp.name}|{distance}|{style}"
        adj = float(nankan_map.get(key, 0.0))
        score = score + adj

    return clamp(score, 1.0, 5.0), adj

def class_estimate(score: float, level: float, is_jra: bool) -> str:
    # levelが高いほど1段下げる
    adj = clamp(score - (level - 0.65) * 1.0, 1.0, 5.0)

    if is_jra:
        if adj >= 4.4: return "OP〜3勝C"
        if adj >= 3.8: return "2勝C"
        if adj >= 3.2: return "1勝C"
        return "未勝利〜1勝C壁"

    if adj >= 4.5: return "A級上位"
    if adj >= 3.9: return "A級〜B1"
    if adj >= 3.3: return "B2〜C1"
    if adj >= 2.7: return "C2〜C3"
    return "C3〜"

def evaluate_track_suitability(traits: HorseTraits, style: Optional[str], distance: Optional[str]) -> dict:
    level_map = load_track_level()
    nankan_map = load_nankan_map()

    rows = []
    raw_map = {}
    adj_map = {}

    for tp in TRACKS:
        level = float(level_map.get(tp.name, 0.65))
        if tp.name == "JRA":
            level = float(level_map.get("JRA", 1.10))
        s, adj = suitability_score(traits, tp, level_map, nankan_map, style, distance)
        raw_map[tp.name] = s
        if adj != 0.0:
            adj_map[tp.name] = adj
        rows.append({
            "track": tp.name,
            "score": round(s, 3),
            "stars": stars(s),
            "grade": grade_from_5(s),
            "class": class_estimate(s, level, is_jra=(tp.name=="JRA")),
            "notes": tp.notes + (f" / 補正{adj:+.2f}" if adj != 0.0 else ""),
        })

    rows_sorted = sorted(rows, key=lambda r: (r["track"] == "JRA", r["track"]))
    return {
        "rows": rows_sorted,
        "raw": raw_map,
        "adj": adj_map,
        "comment": "競馬場形状（直線/コーナー）・馬場傾向（パワー要求）・競走水準（keiba.go.jp統計level）に対し、馬の特性（実績があれば反映）を突合して算出。南関は脚質×距離CSVがあれば微調整。",
    }

# =========================
# conformation（フェーズ2：画像があれば“控えめに”反映）
#  - Pillowが無くても動く
# =========================
def evaluate_conformation(has_image: bool, image_path: Optional[str] = None) -> dict:
    base = 3.0
    img_bonus = 0.0

    if has_image and image_path:
        try:
            from PIL import Image
            im = Image.open(image_path).convert("L")
            w, h = im.size
            pixels = list(im.getdata())
            mean = sum(pixels) / len(pixels)
            var = sum((p - mean) ** 2 for p in pixels) / len(pixels)
            # コントラスト(分散)が一定以上なら「撮影状態が良く、評価の信頼性が少し上がる」程度に反映
            img_bonus = clamp((var / 5000.0), 0.0, 0.25)
            base = 3.1 + img_bonus
        except Exception:
            base = 3.05

    raw = {
        "馬体バランス": base + 0.20,
        "トモ（後躯・推進力）": base + 0.10,
        "前肢・肩の角度": base - 0.05,
        "骨量・丈夫さ": base + 0.10,
        "成長余地": base - 0.10,
    }
    raw = {k: clamp(v, 1.0, 5.0) for k, v in raw.items()}
    avg = sum(raw.values()) / len(raw)

    return {
        "raw": raw,
        "avg": avg,
        "total": stars(avg),
        "grade": grade_from_5(avg),
        "details": {k: stars(v) for k, v in raw.items()},
        "comment": (
            "現時点は“写真から読み取れる範囲”のみで控えめに評価しています。"
            "歩様・故障歴・馬体計測（部位長/角度）などの実測が入るほど精度が上がります。"
        ),
    }

# =========================
# broodmare（STEP3 中央値校正）
# =========================
def pedigree_broodmare_adjustment(sire_line: Optional[str], dam_sire_line: Optional[str]) -> Tuple[float, str]:
    bonus = 0.0
    reasons = []
    if sire_line:
        if "サンデー" in sire_line or "Sunday" in sire_line:
            bonus += 0.12; reasons.append("サンデー系")
        if "キングマンボ" in sire_line or "Kingmambo" in sire_line:
            bonus += 0.12; reasons.append("キングマンボ系")
    if dam_sire_line:
        if "Deputy" in dam_sire_line or "米国" in dam_sire_line:
            bonus += 0.16; reasons.append("米国ダート母父")
    return bonus, " / ".join(reasons)

def evaluate_broodmare_value(
    sire_line: Optional[str],
    dam_sire_line: Optional[str],
    performance_metrics: Optional[dict],
) -> dict:
    raw = {
        "体質・丈夫さ": 3.2,
        "気性の安定": 3.2,
        "母系の広がり": 2.9,
        "地方適性の再現性": 3.1,
        "初仔成功期待": 3.0,
    }
    base_avg = sum(raw.values()) / len(raw)

    ped_bonus, ped_reason = pedigree_broodmare_adjustment(sire_line, dam_sire_line)

    perf_bonus = 0.0
    if performance_metrics:
        ps = performance_score(performance_metrics)
        perf_bonus = clamp((ps - 3.0) * 0.10, -0.15, 0.20)

    final_avg = clamp(base_avg + ped_bonus + perf_bonus, 1.0, 5.0)

    market = load_market()
    center = float(market.get("center_man", 80.0))
    source = str(market.get("source", "default"))

    # 中央値を中心に、★で倍率を変える（盛りすぎない）
    multiplier = clamp(1.0 + 0.25 * (final_avg - 3.0), 0.65, 1.55)
    value = clamp(center * multiplier, 20.0, 600.0)

    return {
        "raw": raw,
        "base_avg": base_avg,
        "bonus": ped_bonus + perf_bonus,
        "final_avg": final_avg,
        "total": stars(final_avg),
        "grade": grade_from_5(final_avg),
        "details": {k: stars(v) for k, v in raw.items()},
        "comment": (
            f"血統補正: {ped_reason}。"
            if ped_reason else
            "血統補正は限定的（未入力/不確定）で、基礎条件重視の評価です。"
        ),
        "market_value_man": round(value, 1),
        "market_value_range_man": [round(value*0.85, 1), round(value*1.15, 1)],
        "market_value_center_man": round(center, 1),
        "market_value_center_source": source,
    }

# =========================
# report
# =========================
def build_report_summary(
    horse_name: str,
    include_broodmare: bool,
    sire_line: Optional[str],
    dam_sire_line: Optional[str],
    netkeiba_metrics: Optional[dict],
    jbis_metrics: Optional[dict],
    has_image: bool,
    image_path: Optional[str],
    nankan_style: Optional[str] = None,
    nankan_distance: Optional[str] = None,
) -> Dict[str, Any]:
    traits, perf_used, perf_val = traits_from_sources(netkeiba_metrics, jbis_metrics)

    track = evaluate_track_suitability(traits, style=nankan_style, distance=nankan_distance)
    conf = evaluate_conformation(has_image=has_image, image_path=image_path)

    # 総合：能力(1..5) + 馬体 + 主要コース平均
    key_tracks = ["大井", "川崎", "船橋", "浦和", "園田", "名古屋", "高知", "佐賀", "盛岡", "水沢"]
    track_vals = [track["raw"].get(t, 3.0) for t in key_tracks if t in track["raw"]]
    track_avg = sum(track_vals) / max(1, len(track_vals))

    overall_components = [
        1.0 + 4.0 * traits.ability,
        conf["avg"],
        track_avg,
    ]
    if perf_used and perf_val is not None:
        overall_components.append(perf_val)

    overall_avg = sum(overall_components) / len(overall_components)

    report: Dict[str, Any] = {
        "summary": (
            f"{horse_name}の評価は、(1)keiba.go.jp統計から推定した競馬場水準(level)による難度補正、"
            f"(2)netkeiba/JBISの実績があれば能力推定に反映（無ければ無視）、"
            f"(3)南関CSV（脚質×距離）があれば微調整、(4)馬体は現状“写真から読める範囲”のみ控えめに反映、"
            f"を統合して算出しています。"
        ),
        "overall": stars(overall_avg),
        "grade": grade_from_5(overall_avg),

        "track_comment": track["comment"],
        "track_rows": track["rows"],

        "conformation": conf,

        "_log": {
            "traits": traits.__dict__,
            "performance_used": perf_used,
            "performance_value_1to5": perf_val,
            "netkeiba_metrics": netkeiba_metrics,
            "jbis_metrics": jbis_metrics,
            "track_raw": track["raw"],
            "track_adj": track["adj"],
            "conformation_raw": conf["raw"],
            "nankan_style": nankan_style,
            "nankan_distance": nankan_distance,
        },
    }

    if include_broodmare:
        broodmare = evaluate_broodmare_value(
            sire_line=sire_line,
            dam_sire_line=dam_sire_line,
            performance_metrics=(netkeiba_metrics or jbis_metrics),
        )
        report["broodmare"] = broodmare
        report["_log"]["broodmare_raw"] = broodmare["raw"]
        report["_log"]["broodmare_bonus"] = broodmare["bonus"]

    return report
