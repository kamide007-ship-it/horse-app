from __future__ import annotations

import json
import os
from typing import Dict, Tuple, Optional

import requests

from .utils import read_csv_dicts, pick, to_float, clamp

NANKAN_JSON = os.path.join(os.path.dirname(__file__), "..", "data", "nankan_style_distance.json")

DEFAULT_NANKAN: Dict[str, float] = {}  # (track|distance|style) -> adj(-0.4..+0.4)

def load_nankan_map() -> Dict[str, float]:
    try:
        with open(NANKAN_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {k: float(v) for k, v in data.items()}
    except Exception:
        pass
    return dict(DEFAULT_NANKAN)

def save_nankan_map(m: Dict[str, float]) -> None:
    os.makedirs(os.path.dirname(NANKAN_JSON), exist_ok=True)
    with open(NANKAN_JSON, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

def update_nankan_map_from_csv_url(csv_url: str, timeout: int = 20) -> Dict[str, float]:
    """
    期待列（例）:
      - 競馬場: 大井/川崎/船橋/浦和
      - 距離: 1200 等
      - 脚質: 逃げ/先行/差し/追込
      - 勝率 or 複勝率 or 連対率
      - サンプル数（任意）
    出力: key=f"{track}|{distance}|{style}" -> 補正値（-0.4..+0.4）
    """
    r = requests.get(csv_url, timeout=timeout)
    r.raise_for_status()
    rows = read_csv_dicts(r.content)
    if not rows:
        save_nankan_map(DEFAULT_NANKAN)
        return dict(DEFAULT_NANKAN)

    out: Dict[str, float] = {}
    for row in rows:
        track = pick(row, ["競馬場", "場", "track"])
        dist = pick(row, ["距離", "distance"])
        style = pick(row, ["脚質", "style"])
        if not track or not dist or not style:
            continue

        # 勝率/複勝率/連対率のいずれか
        wr = to_float(pick(row, ["勝率", "win_rate"]))
        pr = to_float(pick(row, ["複勝率", "place_rate"]))
        qr = to_float(pick(row, ["連対率", "quinella_rate"]))

        # 0..100 の場合を 0..1 に
        def to01(x: Optional[float]) -> Optional[float]:
            if x is None: 
                return None
            return x/100.0 if x > 1.0 else x

        wr = to01(wr); pr = to01(pr); qr = to01(qr)
        rate = pr if pr is not None else (qr if qr is not None else wr)
        if rate is None:
            continue

        # 補正: 平均(0.35)より高ければ+、低ければ-
        # 最大でも±0.35★程度に抑える（過学習防止）
        adj = clamp((rate - 0.35) * 1.0, -0.35, 0.35)

        key = f"{track}|{dist}|{style}"
        out[key] = float(adj)

    save_nankan_map(out)
    return out
