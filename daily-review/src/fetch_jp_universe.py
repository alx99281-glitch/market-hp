"""日本ユニバース（日経225構成銘柄 + TOPIX-17セクターETF + グロース/バリューETF + 指数）の初回一括取得。"""

import console_utf8  # noqa: F401
from config import PRICE_STORE_JP
from data_layer import MarketDataStore
from universe_jp import full_ticker_list_jp, refresh_universe_jp

if __name__ == "__main__":
    print("日経225構成銘柄を最新化します...")
    refresh_universe_jp()
    tickers = full_ticker_list_jp()
    print(f"取得対象ティッカー数: {len(tickers)}")

    store = MarketDataStore(path=PRICE_STORE_JP)
    store.initial_bulk_fetch(tickers)
    print("完了。")
