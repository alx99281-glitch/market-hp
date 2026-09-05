"""層5: ニュース照合の結果を保存するローカルキャッシュ。

キーは (市場, 日付, 論点metric名)。層2〜4で抽出された論点ごとに、見つかった
裏付けニュースの要約と出典URLを保存する。見つからなかった論点は保存しない
（レポート側で「要因不明」と表示する）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_DIR

NEWS_STORE = DATA_DIR / "news_cache.json"


def _load_all() -> dict:
    if NEWS_STORE.exists():
        return json.loads(NEWS_STORE.read_text(encoding="utf-8"))
    return {}


def _save_all(data: dict) -> None:
    NEWS_STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _key(market: str, date, metric: str) -> str:
    date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)
    return f"{market}:{date_str}:{metric}"


def save_news(market: str, date, metric: str, summary: str, sources: list[dict]) -> None:
    """sources: [{"title": ..., "url": ...}, ...]"""
    data = _load_all()
    data[_key(market, date, metric)] = {
        "summary": summary,
        "sources": sources,
        "searched_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_all(data)


def load_news(market: str, date, metric: str) -> dict | None:
    data = _load_all()
    return data.get(_key(market, date, metric))


def load_news_for_date(market: str, date) -> dict[str, dict]:
    data = _load_all()
    date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)
    prefix = f"{market}:{date_str}:"
    return {k[len(prefix):]: v for k, v in data.items() if k.startswith(prefix)}
