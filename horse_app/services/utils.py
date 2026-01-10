from __future__ import annotations

import csv
import io
from typing import Any, Dict, Iterable, Optional, Tuple

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def detect_decode(raw: bytes) -> Optional[str]:
    for enc in ("utf-8-sig", "cp932", "shift_jis", "utf-8"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return None

def read_csv_dicts(raw: bytes) -> list[dict]:
    text = detect_decode(raw)
    if text is None:
        return []
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for r in reader:
        if isinstance(r, dict):
            rows.append({(k or "").strip(): (v or "").strip() for k, v in r.items()})
    return rows

def pick(row: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return str(row[k]).strip()
    return None

def to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    try:
        return float(s.replace(",", ""))
    except Exception:
        return None

def median(vals: list[float]) -> Optional[float]:
    vals2 = [v for v in vals if v is not None]
    if not vals2:
        return None
    vals2.sort()
    n = len(vals2)
    mid = n // 2
    if n % 2 == 1:
        return float(vals2[mid])
    return float((vals2[mid-1] + vals2[mid]) / 2.0)
