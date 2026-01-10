from __future__ import annotations

import json
import os
from typing import Dict, Optional

import requests

from .utils import clamp, read_csv_dicts, pick, to_float

TRACK_LEVEL_JSON = os.path.join(os.path.dirname(__file__), "..", "data", "track_level.json")

# フォールバック（取得失敗時でも“差”が出る最低限の水準）
FALLBACK_LEVEL: Dict[str, float] = {
    "大井": 1.00, "川崎": 0.92, "船橋": 0.92, "浦和": 0.88,
    "園田": 0.78, "名古屋": 0.74, "門別": 0.72, "盛岡": 0.70,
    "姫路": 0.68, "金沢": 0.62, "高知": 0.60, "佐賀": 0.60,
    "水沢": 0.60, "笠松": 0.58,
    "JRA": 1.10,  # 中央は別枠（難度上限）
}

def load_track_level() -> Dict[str, float]:
    try:
        with open(TRACK_LEVEL_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data:
            return {k: float(v) for k, v in data.items()}
    except Exception:
        pass
    return dict(FALLBACK_LEVEL)

def save_track_level(level_map: Dict[str, float]) -> None:
    os.makedirs(os.path.dirname(TRACK_LEVEL_JSON), exist_ok=True)
    with open(TRACK_LEVEL_JSON, "w", encoding="utf-8") as f:
        json.dump(level_map, f, ensure_ascii=False, indent=2)

def update_track_level_from_csv_url(csv_url: str, timeout: int = 20) -> Dict[str, float]:
    """
    keiba.go.jpの年度統計CSV（URL直指定）をDLし、
    avg_prize = 総賞金 / 出走頭数 で競馬場水準を作る。

    期待列（どれか一致すればOK）:
      - 競馬場 or 主催者
      - 総賞金
      - 出走頭数
    """
    r = requests.get(csv_url, timeout=timeout)
    r.raise_for_status()

    rows = read_csv_dicts(r.content)
    if not rows:
        # 解析失敗ならフォールバック
        save_track_level(FALLBACK_LEVEL)
        return dict(FALLBACK_LEVEL)

    track_avg = {}
    for row in rows:
        track = pick(row, ["競馬場", "主催者", "競馬場名"])
        total_prize = to_float(pick(row, ["総賞金", "賞金総額", "総賞金額"]))
        starts = to_float(pick(row, ["出走頭数", "出走回数", "出走数"]))
        if not track or total_prize is None or starts is None or starts <= 0:
            continue
        avg = total_prize / starts
        track_avg[track] = avg

    if not track_avg:
        save_track_level(FALLBACK_LEVEL)
        return dict(FALLBACK_LEVEL)

    # 正規化: 中央/地方混在でも破綻しないように robust に 0.55..0.95 へ
    vals = list(track_avg.values())
    vmin, vmax = min(vals), max(vals)
    def norm(v: float) -> float:
        if vmax <= vmin:
            return 0.70
        z = (v - vmin) / (vmax - vmin)  # 0..1
        return 0.55 + 0.40 * z          # 0.55..0.95

    level_map = {k: float(norm(v)) for k, v in track_avg.items()}
    # JRAだけは難度上限を維持
    level_map["JRA"] = 1.10
    save_track_level(level_map)
    return level_map
