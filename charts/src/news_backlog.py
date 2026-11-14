"""日々の材料(data/news/YYYY-MM.json)がまだない取引日を、収集する順に並べて出す。

    python charts/src/news_backlog.py [件数] [--years 3]

対象は直近 --years 年の、日経平均か S&P500 のどちらかが取引した日。
順序: 直近7日 → 日米どちらかが2%以上動いた日(動きの大きい順) → 残りを新しい順。
各行に日付・日経平均とS&P500の騰落率・足りない市場(jp/us)を出す。
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
NEWS = DATA / "news"


def changes(name: str) -> dict[str, float]:
    rows = json.loads((DATA / f"{name}_ohlc.json").read_text(encoding="utf-8"))
    return {rows[i]["t"]: (rows[i]["c"] / rows[i - 1]["c"] - 1) * 100 for i in range(1, len(rows))}


def covered() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for p in NEWS.glob("*.json"):
        for d, v in json.loads(p.read_text(encoding="utf-8")).items():
            out[d] = {k for k in ("us", "jp") if (v.get(k) or {}).get("items") or (v.get(k) or {}).get("note")}
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = int(args[0]) if args else 15
    years = 3
    if "--years" in sys.argv:
        years = int(sys.argv[sys.argv.index("--years") + 1])
    jp, us = changes("n225"), changes("spx")
    last = max(max(jp), max(us))
    start = (date.fromisoformat(last) - timedelta(days=365 * years)).isoformat()
    have = covered()
    todo = []
    for d in sorted(set(jp) | set(us)):
        if d < start:
            continue
        need = [m for m, src in (("jp", jp), ("us", us)) if d in src and m not in have.get(d, set())]
        if need:
            todo.append((d, jp.get(d), us.get(d), need))
    recent_cut = (date.fromisoformat(last) - timedelta(days=7)).isoformat()
    recent = [t for t in todo if t[0] >= recent_cut]
    rest = [t for t in todo if t[0] < recent_cut]
    big = sorted((t for t in rest if max(abs(t[1] or 0), abs(t[2] or 0)) >= 2),
                 key=lambda t: -max(abs(t[1] or 0), abs(t[2] or 0)))
    others = sorted((t for t in rest if t not in big), key=lambda t: t[0], reverse=True)
    order = sorted(recent, key=lambda t: t[0], reverse=True) + big + others
    print(f"# 未収集 {len(todo)}日(直近{years}年)。上位{min(n, len(order))}日:")
    for d, cj, cu, need in order[:n]:
        fj = "休場" if cj is None else f"{cj:+.2f}%"
        fu = "休場" if cu is None else f"{cu:+.2f}%"
        print(f"{d}  日経 {fj:>8}  S&P {fu:>8}  不足: {','.join(need)}")


if __name__ == "__main__":
    main()
