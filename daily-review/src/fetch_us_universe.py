"""米国ユニバース（S&P500構成銘柄 + セクターETF + ファクターETF + 指数）の初回一括取得。"""

import console_utf8  # noqa: F401
from data_layer import MarketDataStore
from universe import full_ticker_list, refresh_universe

if __name__ == "__main__":
    print("S&P500構成銘柄を最新化します...")
    refresh_universe()
    tickers = full_ticker_list()
    print(f"取得対象ティッカー数: {len(tickers)}")

    store = MarketDataStore()
    store.initial_bulk_fetch(tickers)
    print("完了。")
