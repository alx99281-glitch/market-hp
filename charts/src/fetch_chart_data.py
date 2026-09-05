"""タブ1用: 日経平均・S&P500の10年分ローソク足データを取得しJSON化する。

チャート表示専用のシンプルなOHLCデータで、tab2(daily-review)の価格ストアとは
独立させる（用途が違う: こちらは表示専用・随時全期間再取得でよい）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yfinance as yf

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

TICKERS = {"spx": "^GSPC", "n225": "^N225"}


def fetch_and_save(name: str, ticker: str, period: str = "10y") -> None:
    df = yf.download(ticker, period=period, auto_adjust=False, progress=False)
    if df is None or df.empty:
        raise RuntimeError(f"{ticker}: データ取得に失敗しました")
    if isinstance(df.columns, __import__("pandas").MultiIndex):
        df.columns = df.columns.get_level_values(0)

    records = []
    for date, row in df.iterrows():
        records.append(
            {
                "t": date.strftime("%Y-%m-%d"),
                "o": round(float(row["Open"]), 2),
                "h": round(float(row["High"]), 2),
                "l": round(float(row["Low"]), 2),
                "c": round(float(row["Close"]), 2),
                "v": int(row["Volume"]) if row["Volume"] == row["Volume"] else 0,
            }
        )

    out_path = DATA_DIR / f"{name}_ohlc.json"
    out_path.write_text(json.dumps(records), encoding="utf-8")
    print(f"{name} ({ticker}): {len(records)}日分を保存しました -> {out_path}")


if __name__ == "__main__":
    for name, ticker in TICKERS.items():
        fetch_and_save(name, ticker)
