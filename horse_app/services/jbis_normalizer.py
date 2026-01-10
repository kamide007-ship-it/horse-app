from __future__ import annotations

from typing import Optional, Dict, Any
import requests

from .utils import read_csv_dicts, pick, to_float, clamp

def fetch_jbis_csv_bytes(csv_url: str, timeout: int = 15) -> Optional[bytes]:
    if not csv_url:
        return None
    r = requests.get(csv_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        return None
    return r.content

def normalize_jbis_csv(raw: bytes) -> Optional[Dict[str, Any]]:
    """
    pandasを使わず、JBISの出力差を吸収して “評価用の最小指標” に正規化します。
    可能なら:
      - starts, wins, place(<=3), avg_prize(万円), recent_form(0..1)
    """
    rows = read_csv_dicts(raw)
    if not rows:
        return None

    finishes = []
    prizes = []
    for row in rows:
        fin = pick(row, ["着順", "順位", "着", "result", "finish"])
        if fin:
            try:
                f = int(str(fin).strip())
                finishes.append(f)
            except Exception:
                pass

        prize = pick(row, ["賞金", "獲得賞金", "本賞金", "prize"])
        p = to_float(prize)
        if p is not None:
            # 円っぽい場合を簡易補正
            if p > 10000:
                p = p / 10000.0
            prizes.append(float(p))

    if not finishes:
        return None

    n = len(finishes)
    wins = sum(1 for f in finishes if f == 1)
    places = sum(1 for f in finishes if f <= 3)

    last = finishes[:5]
    avg_fin = sum(last) / len(last)
    recent_form = clamp(1.0 - (avg_fin - 1.0) / 9.0, 0.0, 1.0)

    avg_prize = (sum(prizes) / len(prizes)) if prizes else None

    return {
        "starts": n,
        "wins": wins,
        "places": places,
        "win_rate": wins / n,
        "place_rate": places / n,
        "recent_form": recent_form,
        "avg_prize": avg_prize,
        "source": "jbis_csv",
    }
