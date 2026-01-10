from __future__ import annotations

import json
import os
from typing import Dict, Optional, Tuple

import requests

from .utils import read_csv_dicts, pick, to_float, median, clamp

MARKET_JSON = os.path.join(os.path.dirname(__file__), "..", "data", "broodmare_market.json")

DEFAULT = {
    "center_man": 80.0,
    "n_samples": 0,
    "source": "default",
}

def load_market() -> dict:
    try:
        with open(MARKET_JSON, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and "center_man" in d:
            return d
    except Exception:
        pass
    return dict(DEFAULT)

def save_market(d: dict) -> None:
    os.makedirs(os.path.dirname(MARKET_JSON), exist_ok=True)
    with open(MARKET_JSON, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def _parse_prices_from_csv_bytes(raw: bytes) -> Tuple[Optional[float], int]:
    rows = read_csv_dicts(raw)
    if not rows:
        return None, 0

    prices = []
    for row in rows:
        p = pick(row, ["価格（万円）", "価格", "取引価格", "落札価格", "price_man", "price"])
        v = to_float(p)
        if v is None:
            continue
        # 価格が円の場合を簡易検知（大きすぎる）: 例 3000000 -> 300万円
        if v > 10000:
            v = v / 10000.0
        prices.append(float(v))

    m = median(prices)
    return m, len(prices)

def update_market_from_csv_url(csv_url: str, timeout: int = 20) -> dict:
    r = requests.get(csv_url, timeout=timeout)
    r.raise_for_status()
    m, n = _parse_prices_from_csv_bytes(r.content)

    if m is None:
        d = dict(DEFAULT)
        d["source"] = "url_parse_failed"
        save_market(d)
        return d

    d = {
        "center_man": float(clamp(m, 20.0, 500.0)),
        "n_samples": int(n),
        "source": "csv_url",
    }
    save_market(d)
    return d

def update_market_from_upload(raw: bytes) -> dict:
    m, n = _parse_prices_from_csv_bytes(raw)
    if m is None:
        d = dict(DEFAULT)
        d["source"] = "upload_parse_failed"
        save_market(d)
        return d
    d = {
        "center_man": float(clamp(m, 20.0, 500.0)),
        "n_samples": int(n),
        "source": "upload",
    }
    save_market(d)
    return d
