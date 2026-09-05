"""米国・日本のパイプラインを共通コードで動かすための市場コンテキスト。

decompose.py / zscore.py / report.py / html_report.py はすべてこの
MarketContext を受け取って動作し、市場固有の定数（ティッカー・ETF・
セクター区分など）を直接importしない。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from data_layer import MarketDataStore


@dataclass
class MarketContext:
    name: str
    label: str
    price_store: MarketDataStore
    fundamentals_path: Path
    universe_df: pd.DataFrame  # 必須列: symbol, sector
    sector_weights: dict[str, float]
    index_ticker: str
    sector_etfs: dict[str, str]  # ETFティッカー -> セクター名
    factor_etfs: dict[str, str]  # ETFティッカー -> ファクター表示名
    factor_etf_map: dict[str, str]  # 自前計算ファクター名 -> factor_etfsの表示名
    output_subdir: str
    index_display: str  # レポート表示用の指数名
    sector_weight_method: str  # セクターウェイトの算出方法（表示用の説明文）


def us_context() -> MarketContext:
    from config import (
        FUNDAMENTALS_STORE,
        PRICE_STORE,
        US_FACTOR_ETF_MAP,
        US_FACTOR_ETFS,
        US_INDEX_TICKER,
        US_SECTOR_ETFS,
    )
    from sector_weights import load_sector_weights
    from universe import load_current_universe

    uni = load_current_universe().rename(columns={"gics_sector": "sector"})
    return MarketContext(
        name="us",
        label="米国",
        price_store=MarketDataStore(path=PRICE_STORE),
        fundamentals_path=FUNDAMENTALS_STORE,
        universe_df=uni,
        sector_weights=load_sector_weights(),
        index_ticker=US_INDEX_TICKER,
        sector_etfs=US_SECTOR_ETFS,
        factor_etfs=US_FACTOR_ETFS,
        factor_etf_map=US_FACTOR_ETF_MAP,
        output_subdir="us",
        index_display="S&P500",
        sector_weight_method="SPY保有構成ベース（cap-weight近似）",
    )


def jp_context() -> MarketContext:
    from config import (
        FUNDAMENTALS_STORE_JP,
        JP_FACTOR_ETF_MAP,
        JP_INDEX_TICKER,
        JP_SECTOR_ETFS,
        JP_STYLE_ETFS,
        PRICE_STORE_JP,
    )
    from sector_weights import load_sector_weights_jp
    from universe_jp import load_current_universe_jp

    uni = load_current_universe_jp()
    return MarketContext(
        name="jp",
        label="日本",
        price_store=MarketDataStore(path=PRICE_STORE_JP),
        fundamentals_path=FUNDAMENTALS_STORE_JP,
        universe_df=uni,
        sector_weights=load_sector_weights_jp(),
        index_ticker=JP_INDEX_TICKER,
        sector_etfs=JP_SECTOR_ETFS,
        factor_etfs=JP_STYLE_ETFS,
        factor_etf_map=JP_FACTOR_ETF_MAP,
        output_subdir="jp",
        index_display="日経平均株価",
        sector_weight_method="日経225構成銘柄数比率（cap-weightではない近似）",
    )
