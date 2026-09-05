"""S&P500構成銘柄ユニバースの管理。

Wikipedia の一覧ページを正とし、週次で再取得して前回との差分（採用・除外）を
data/universe_history.parquet に追記記録する。銘柄コードとGICSセクターの
対応も併せて保持する（層1のセクター寄与度計算で使用）。
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone

import pandas as pd
import requests

from config import UNIVERSE_CURRENT, UNIVERSE_STORE, US_SECTOR_ETFS, US_FACTOR_ETFS

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
HEADERS = {"User-Agent": "Mozilla/5.0 (daily-market-review research tool)"}


def fetch_sp500_constituents() -> pd.DataFrame:
    """Wikipediaから現在のS&P500構成銘柄とGICSセクターを取得する。

    戻り値の列: symbol, security, gics_sector, gics_sub_industry, date_added
    """
    r = requests.get(WIKI_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    tables = pd.read_html(io.StringIO(r.text))
    df = tables[0]
    df = df.rename(
        columns={
            "Symbol": "symbol",
            "Security": "security",
            "GICS Sector": "gics_sector",
            "GICS Sub-Industry": "gics_sub_industry",
            "Date added": "date_added",
        }
    )[["symbol", "security", "gics_sector", "gics_sub_industry", "date_added"]]
    # yfinanceのティッカー表記に合わせる（例: BRK.B -> BRK-B）
    df["symbol"] = df["symbol"].str.replace(".", "-", regex=False)
    return df.reset_index(drop=True)


def refresh_universe() -> pd.DataFrame:
    """現在の構成銘柄を取得し、前回スナップショットとの差分を記録した上で保存する。

    戻り値は最新の構成銘柄DataFrame。
    """
    new_df = fetch_sp500_constituents()
    now = datetime.now(timezone.utc).isoformat()

    old_symbols: set[str] = set()
    if UNIVERSE_CURRENT.exists():
        old = json.loads(UNIVERSE_CURRENT.read_text(encoding="utf-8"))
        old_symbols = set(old.get("symbols", []))

    new_symbols = set(new_df["symbol"])
    added = sorted(new_symbols - old_symbols)
    removed = sorted(old_symbols - new_symbols)

    if added or removed:
        events = []
        for sym in added:
            events.append({"date": now, "symbol": sym, "action": "added"})
        for sym in removed:
            events.append({"date": now, "symbol": sym, "action": "removed"})
        events_df = pd.DataFrame(events)

        if UNIVERSE_STORE.exists():
            history = pd.read_parquet(UNIVERSE_STORE)
            history = pd.concat([history, events_df], ignore_index=True)
        else:
            history = events_df
        history.to_parquet(UNIVERSE_STORE, index=False)

    UNIVERSE_CURRENT.write_text(
        json.dumps({"updated_at": now, "symbols": sorted(new_symbols)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    new_df.to_json(UNIVERSE_CURRENT.with_suffix(".detail.json"), orient="records", force_ascii=False, indent=2)

    return new_df


def load_current_universe() -> pd.DataFrame:
    """保存済みの最新構成銘柄詳細を読み込む。無ければ新規取得する。"""
    detail_path = UNIVERSE_CURRENT.with_suffix(".detail.json")
    if detail_path.exists():
        return pd.read_json(detail_path)
    return refresh_universe()


def full_ticker_list() -> list[str]:
    """個別銘柄 + セクターETF + ファクターETF の全ティッカーを返す。"""
    constituents = load_current_universe()["symbol"].tolist()
    etfs = list(US_SECTOR_ETFS.keys()) + list(US_FACTOR_ETFS.keys())
    index = ["^GSPC"]
    # 重複除去しつつ順序保持
    seen = set()
    result = []
    for t in constituents + etfs + index:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


if __name__ == "__main__":
    df = refresh_universe()
    print(f"S&P500構成銘柄: {len(df)}件")
    print(df["gics_sector"].value_counts())
