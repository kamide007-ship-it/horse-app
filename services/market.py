from __future__ import annotations

import json
from pathlib import Path

from services.utils import safe_float

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "market_medians.json"

DEFAULTS = {
    "オールザベスト": 3300000,  # yen (初期アンカー：2-5M帯をカバー)
    "アジアエクスプレス": 2000000,
    "エスケンデレヤ": 1700000,
}


def _load_db() -> dict:
    if DATA_PATH.exists():
        try:
            return json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def estimate_market(payload: dict, market_inputs: dict) -> dict:
    """Return market price range and sources.

    v1.0: Uses sire median as a primary anchor, adjusted by dam value, sex, and blacktype proxies.
    """
    sire = (payload.get("sire") or "").strip()
    sex = (payload.get("sex") or "").strip()

    db = _load_db()
    sire_median = safe_float(market_inputs.get("sire_fee_median"))
    if sire_median is None:
        sire_median = float(db.get(sire, DEFAULTS.get(sire, 1500000)))

    dam_value = safe_float(market_inputs.get("dam_value")) or 0.0
    blacktype = safe_float(market_inputs.get("blacktype_count")) or 0.0
    near_gsw = safe_float(market_inputs.get("nearby_gsw")) or 0.0

    base = sire_median
    # mother value adds some premium
    base += min(3000000.0, dam_value * 0.25)
    base += blacktype * 250000.0
    base += near_gsw * 350000.0

    # sex adjustment (filly often a bit higher if broodmare value; colt slightly for racing)
    if "牝" in sex:
        base *= 1.06
    elif "牡" in sex:
        base *= 1.03

    # Wider range to avoid underestimation in early-stage market sampling.
    low = int(round(base * 0.65, -4))
    high = int(round(base * 1.50, -4))

    sources = {
        "ja": "推定根拠：種牡馬の市場取引中央値（入力 or 内部DB）＋母馬価値＋近親実績補正",
        "en": "Based on sire median market price + dam value + blacktype proxies.",
    }

    return {
        "yen_low": max(0, low),
        "yen_high": max(low, high),
        "anchor": int(round(sire_median, -4)),
        "source": sources,
    }
