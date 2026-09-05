"""共通設定。仕様書(SPEC_1.md)の「未決事項」はここに初期値を集約し、後で調整する。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PRICE_STORE = DATA_DIR / "prices.parquet"
UNIVERSE_STORE = DATA_DIR / "universe_history.parquet"
UNIVERSE_CURRENT = DATA_DIR / "universe_current.json"
FUNDAMENTALS_STORE = DATA_DIR / "fundamentals.parquet"
REPORTS_DIR = ROOT / "reports"

# 日本版（米国版と対になるファイル群）
PRICE_STORE_JP = DATA_DIR / "prices_jp.parquet"
UNIVERSE_STORE_JP = DATA_DIR / "universe_history_jp.parquet"
UNIVERSE_CURRENT_JP = DATA_DIR / "universe_current_jp.json"
FUNDAMENTALS_STORE_JP = DATA_DIR / "fundamentals_jp.parquet"
SECTOR_WEIGHTS_JP = DATA_DIR / "sector_weights_jp.json"

INITIAL_HISTORY_YEARS = 3

# 層2: zスコアのローリング窓幅（初期値。60日か120日かは運用しながら決める）
ZSCORE_WINDOW = 120
ZSCORE_THRESHOLD = 1.5

# セクター間相関の窓幅
SECTOR_CORR_WINDOW = 20

# yfinance バッチ取得設定
YF_CHUNK_SIZE = 100          # 1回のyf.downloadに含める銘柄数
YF_SLEEP_SEC = 3             # チャンク間のスリープ
YF_MAX_RETRIES = 4
YF_BACKOFF_BASE_SEC = 5      # 指数バックオフの基準秒数（5, 10, 20, 40...）

# 米国 ETF ユニバース
US_SECTOR_ETFS = {
    "XLK": "Technology", "XLF": "Financials", "XLV": "Health Care",
    "XLY": "Consumer Discretionary", "XLP": "Consumer Staples",
    "XLE": "Energy", "XLI": "Industrials", "XLB": "Materials",
    "XLU": "Utilities", "XLRE": "Real Estate", "XLC": "Communication Services",
}

US_FACTOR_ETFS = {
    "MTUM": "Momentum", "VLUE": "Value", "QUAL": "Quality",
    "USMV": "Low Volatility", "IWM": "Size (Small Cap)", "SPY": "Market (Beta=1 proxy)",
}

US_INDEX_TICKER = "^GSPC"
US_INDEX_ETF_PROXY = "SPY"  # 個別銘柄リターンとの整合性チェック用

# 自前計算ファクター名 -> ETFベース簡易版の表示名 の対応（部分一致による誤対応を避けるため明示）
US_FACTOR_ETF_MAP = {
    "Momentum": "Momentum", "Value": "Value", "Quality": "Quality",
    "Volatility": "Low Volatility", "Size": "Size (Small Cap)",
}

# 日本 ETF ユニバース（TOPIX-17シリーズ + グロース/バリュー + 指数連動ETF）
JP_SECTOR_ETFS = {
    "1617.T": "食品", "1618.T": "エネルギー資源", "1619.T": "建設・資材",
    "1620.T": "素材・化学", "1621.T": "医薬品", "1622.T": "自動車・輸送機",
    "1623.T": "鉄鋼・非鉄", "1624.T": "機械", "1625.T": "電機・精密",
    "1626.T": "情報通信・サービスその他", "1627.T": "電力・ガス", "1628.T": "運輸・物流",
    "1629.T": "商社・卸売", "1630.T": "小売", "1631.T": "銀行",
    "1632.T": "金融（除く銀行）", "1633.T": "不動産",
}

JP_STYLE_ETFS = {"2516.T": "Growth", "2517.T": "Value"}

JP_INDEX_TICKER = "^N225"
JP_TOPIX_PROXY = "1306.T"  # ^TOPX がyfinanceで取得不可なためETFで代用（仕様書記載のフォールバック）
JP_NIKKEI_ETF_PROXY = "1321.T"

JP_FACTOR_ETF_MAP = {"Value": "Value", "Growth": "Growth"}
