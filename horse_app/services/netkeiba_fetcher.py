from __future__ import annotations

from typing import Optional, Dict, Any, List
import re
import requests
from bs4 import BeautifulSoup

def _extract_finishes_from_table(soup: BeautifulSoup) -> List[int]:
    # PC版/スマホ版の差を吸収
    candidates = [
        "table.db_h_race_results tr",
        "table.Nk_tb_common tr",
        "table tr",
    ]
    for sel in candidates:
        rows = soup.select(sel)
        finishes = []
        for row in rows[1:]:
            cols = row.find_all("td")
            if not cols:
                continue
            txt = cols[0].get_text(strip=True)
            if not txt:
                continue
            # 中止/除外など排除
            if not re.match(r"^\d+$", txt):
                continue
            finishes.append(int(txt))
        if finishes:
            return finishes
    return []

def fetch_netkeiba_metrics(result_url: str, timeout: int = 15) -> Optional[Dict[str, Any]]:
    if not result_url:
        return None

    r = requests.get(result_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    finishes = _extract_finishes_from_table(soup)
    if not finishes:
        return None

    n = len(finishes)
    win = sum(1 for f in finishes if f == 1)
    place = sum(1 for f in finishes if f <= 3)

    last = finishes[:5]
    avg_fin = sum(last) / len(last)
    recent_form = max(0.0, min(1.0, 1.0 - (avg_fin - 1.0) / 9.0))

    # クラス指数の推定（雑にでも差が出るようにする）
    text = soup.get_text(" ", strip=True).lower()
    class_index = 3.0
    if any(k in text for k in ["g1", "gⅰ", "g2", "gⅱ", "g3", "gⅲ", "重賞", "jpn", "op", "open"]):
        class_index = 4.6
    elif any(k in text for k in ["3勝", "1600", "準op"]):
        class_index = 4.1
    elif any(k in text for k in ["2勝", "1000"]):
        class_index = 3.7
    elif any(k in text for k in ["1勝", "500"]):
        class_index = 3.3
    elif any(k in text for k in ["未勝利", "新馬"]):
        class_index = 2.8

    return {
        "n_runs": n,
        "win_rate": win / n,
        "place_rate": place / n,
        "recent_form": recent_form,
        "class_index": class_index,
        "source": "netkeiba_url",
    }
