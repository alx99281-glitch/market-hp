"""マクロ変数（USDJPY・米10年金利・原油）と、指数・PCAスコアとの相関。

「PCAが見つけた変動パターンは、結局のところマクロ要因で動いているのか」を
検証するための補助。PC1の説明力が高いからといって直ちに「マクロ主導」とは
言えない（セクターローテーションでも説明力は上がりうる）ため、実際に既知の
マクロ変数との相関を計算して裏付ける。米国・日本で共通のマクロ系列を使う
（USDJPY・米金利・原油はどちらの市場にも影響するため）。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import DATA_DIR
from data_layer import MarketDataStore

MACRO_STORE = DATA_DIR / "macro_prices.parquet"

MACRO_TICKERS = {"USDJPY": "JPY=X", "US10Y": "^TNX", "Oil": "CL=F"}

CORR_WINDOW = 60


def macro_store() -> MarketDataStore:
    return MarketDataStore(path=MACRO_STORE)


def fetch_macro_data() -> None:
    store = macro_store()
    store.initial_bulk_fetch(list(MACRO_TICKERS.values()), years=3)


def daily_update_macro() -> pd.DataFrame:
    store = macro_store()
    return store.daily_update(list(MACRO_TICKERS.values()))


def macro_returns() -> pd.DataFrame:
    """マクロ系列の日次変化率（USDJPY・原油は%変化、金利は水準差=bp相当）。"""
    close = macro_store().wide_close()
    close = close.rename(columns={v: k for k, v in MACRO_TICKERS.items()})
    out = pd.DataFrame(index=close.index)
    for name in ("USDJPY", "Oil"):
        if name in close.columns:
            out[name] = close[name].pct_change()
    if "US10Y" in close.columns:
        out["US10Y"] = close["US10Y"].diff()  # 金利は変化率でなく水準差（bp）
    return out


def correlation_with(
    series: pd.Series, macro: pd.DataFrame | None = None, window: int = CORR_WINDOW
) -> dict[str, float]:
    """指数リターンやPCスコアの系列と、各マクロ変数の直近window日相関。"""
    if macro is None:
        macro = macro_returns()
    aligned = macro.reindex(series.index)
    result = {}
    for col in aligned.columns:
        pair = pd.concat([series.tail(window), aligned[col].tail(window)], axis=1).dropna()
        if len(pair) >= 20:
            result[col] = float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
    return result


def today_macro_moves(date: pd.Timestamp) -> dict[str, float]:
    """指定日のマクロ変数の変化（USDJPY/Oil=前日比%、US10Y=前日比bp）。"""
    mret = macro_returns()
    if date not in mret.index:
        return {}
    row = mret.loc[date].dropna()
    return row.to_dict()


if __name__ == "__main__":
    import sys

    import console_utf8  # noqa: F401

    if "--update" in sys.argv:
        fetch_macro_data()
        n = daily_update_macro()
        print(f"マクロデータ更新: {len(n)}行追加")
    mret = macro_returns()
    print(mret.tail(5))
