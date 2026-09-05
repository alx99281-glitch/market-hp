"""S&P500のセクター別ウェイト（cap-weighted、SPYの保有構成から取得）。

yfinanceのETF fund_data.sector_weightings はスナップショット値のみ提供され、
日次では大きく変動しないため、ユニバース更新（週次想定）と合わせて
更新すればよい。取得できない場合は前回キャッシュを使う。
"""

from __future__ import annotations

import json

import yfinance as yf

from config import DATA_DIR, SECTOR_WEIGHTS_JP

WEIGHTS_CACHE = DATA_DIR / "sector_weights.json"

# yfinance sector_weightings のキー -> GICSセクター名（Wikipedia表記）への対応
SECTOR_KEY_MAP = {
    "technology": "Information Technology",
    "financial_services": "Financials",
    "healthcare": "Health Care",
    "consumer_cyclical": "Consumer Discretionary",
    "consumer_defensive": "Consumer Staples",
    "energy": "Energy",
    "industrials": "Industrials",
    "basic_materials": "Materials",
    "utilities": "Utilities",
    "realestate": "Real Estate",
    "communication_services": "Communication Services",
}


def fetch_sector_weights(proxy_ticker: str = "SPY") -> dict[str, float]:
    """SPYの保有構成からGICSセクター別ウェイトを取得する。"""
    t = yf.Ticker(proxy_ticker)
    raw = t.funds_data.sector_weightings
    weights = {}
    for key, gics_name in SECTOR_KEY_MAP.items():
        if key in raw:
            weights[gics_name] = float(raw[key])
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    WEIGHTS_CACHE.write_text(json.dumps(weights, ensure_ascii=False, indent=2), encoding="utf-8")
    return weights


def load_sector_weights() -> dict[str, float]:
    if WEIGHTS_CACHE.exists():
        return json.loads(WEIGHTS_CACHE.read_text(encoding="utf-8"))
    return fetch_sector_weights()


def compute_jp_sector_weights() -> dict[str, float]:
    """日本版のセクターウェイト近似。

    TOPIX-17の公式時価総額ウェイトを無料で取得する手段がないため、
    日経225構成銘柄数のセクター別比率で代用する（時価総額ウェイトではない
    近似値である点に注意。将来的に正式なウェイトソースが見つかれば置き換える）。
    """
    from universe_jp import load_current_universe_jp

    uni = load_current_universe_jp()
    counts = uni["sector"].value_counts()
    weights = (counts / counts.sum()).to_dict()
    SECTOR_WEIGHTS_JP.write_text(json.dumps(weights, ensure_ascii=False, indent=2), encoding="utf-8")
    return weights


def load_sector_weights_jp() -> dict[str, float]:
    if SECTOR_WEIGHTS_JP.exists():
        return json.loads(SECTOR_WEIGHTS_JP.read_text(encoding="utf-8"))
    return compute_jp_sector_weights()


if __name__ == "__main__":
    w = fetch_sector_weights()
    for k, v in sorted(w.items(), key=lambda kv: -kv[1]):
        print(f"{k:30s} {v:6.2%}")
