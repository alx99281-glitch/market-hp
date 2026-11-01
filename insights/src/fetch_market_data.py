"""クラウド定期実行が使う市場データを取得する。

クラウド環境から Yahoo Finance に接続できないため、GitHub Actions でここを実行し、
結果を market-data ブランチに置く。引数は出力先ディレクトリ。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = ROOT / "data" / "universe.json"
INFO_FIELDS = (
    "shortName", "marketCap", "trailingPE", "forwardPE", "priceToBook", "operatingMargins",
    "revenueGrowth", "earningsGrowth", "shortPercentOfFloat", "beta", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
)


def to_long(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    frames = []
    for t in tickers:
        if t not in raw.columns.get_level_values(0):
            continue
        d = raw[t].dropna(subset=["Close"])
        if d.empty:
            continue
        d = d.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].copy()
        d.index = pd.to_datetime(d.index, utc=True).rename("date")
        d = d.reset_index()
        d.insert(1, "ticker", t)
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


def download(tickers: list[str], **kwargs) -> pd.DataFrame:
    raw = yf.download(tickers, auto_adjust=True, group_by="ticker", threads=True, progress=False, **kwargs)
    return to_long(raw, tickers)


def fundamentals(tickers: list[str]) -> dict:
    out = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).get_info()
            out[t] = {k: info.get(k) for k in INFO_FIELDS}
        except Exception as e:
            print(f"[warn] {t}: {e}", file=sys.stderr)
    return out


def main():
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))

    daily = download(universe["daily"], start="2000-01-01")
    daily["date"] = daily["date"].dt.tz_localize(None)
    daily.to_parquet(out_dir / "daily.parquet", compression="zstd", index=False)

    intraday = download(universe["intraday"], period="729d", interval="60m")
    intraday.to_parquet(out_dir / "intraday_60m.parquet", compression="zstd", index=False)

    funds = fundamentals(universe["fundamentals"])
    (out_dir / "fundamentals.json").write_text(json.dumps(funds, ensure_ascii=False, indent=1), encoding="utf-8")

    last = daily.groupby("ticker")["date"].max().dt.strftime("%Y-%m-%d")
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "last_date": {t: last.get(t) for t in ("^GSPC", "^N225")},
        "daily_tickers": len(last),
        "missing_daily": sorted(set(universe["daily"]) - set(last.index)),
        "intraday_tickers": int(intraday["ticker"].nunique()),
        "fundamentals_tickers": len(funds),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=1))
    if manifest["last_date"]["^GSPC"] is None or manifest["last_date"]["^N225"] is None:
        sys.exit("主要指数を取得できませんでした")


if __name__ == "__main__":
    main()
