"""ファンダメンタルズ・スナップショットの取得（Value/Growth/Quality/Sizeファクター用）。

yfinance の Ticker.info はリクエストごとに時間がかかるため、週次更新を想定した
バッチジョブとして分離する。取得項目は、日次では変化しない/しにくい特性値のみ
（株価そのものは日次データ側で別途持つ）。米国・日本で別ファイルに保存する。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from config import FUNDAMENTALS_STORE

FIELDS = [
    "marketCap",
    "priceToBook",
    "trailingPE",
    "returnOnEquity",
    "revenueGrowth",
    "earningsGrowth",
    "debtToEquity",
    "profitMargins",
]

SLEEP_SEC = 0.5


def fetch_fundamentals(
    tickers: list[str], store_path: Path = FUNDAMENTALS_STORE, sleep_sec: float = SLEEP_SEC
) -> pd.DataFrame:
    rows = []
    now = datetime.now(timezone.utc).isoformat()
    total = len(tickers)
    for i, t in enumerate(tickers, 1):
        row = {"ticker": t, "updated_at": now}
        try:
            info = yf.Ticker(t).get_info()
            for f in FIELDS:
                row[f] = info.get(f)
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] {t}: {e}")
            for f in FIELDS:
                row[f] = None
        rows.append(row)
        if i % 25 == 0 or i == total:
            print(f"  fundamentals {i}/{total}")
        time.sleep(sleep_sec)
    df = pd.DataFrame(rows)
    df.to_parquet(store_path, index=False)
    return df


def load_fundamentals(store_path: Path = FUNDAMENTALS_STORE) -> pd.DataFrame:
    if store_path.exists():
        return pd.read_parquet(store_path)
    return pd.DataFrame(columns=["ticker", "updated_at"] + FIELDS)


if __name__ == "__main__":
    import sys

    from config import FUNDAMENTALS_STORE_JP

    if "--jp" in sys.argv:
        from universe_jp import load_current_universe_jp

        tickers = load_current_universe_jp()["symbol"].tolist()
        store_path = FUNDAMENTALS_STORE_JP
    else:
        from universe import load_current_universe

        tickers = load_current_universe()["symbol"].tolist()
        store_path = FUNDAMENTALS_STORE

    if "--test" in sys.argv:
        tickers = tickers[:10]
    print(f"ファンダメンタルズ取得: {len(tickers)}銘柄 -> {store_path}")
    fetch_fundamentals(tickers, store_path=store_path)
    print("完了。")
