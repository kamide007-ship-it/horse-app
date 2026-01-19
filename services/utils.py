from __future__ import annotations

from typing import Any


def safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))
