"""「大きく動いたもの」の候補を機械的に洗い出す。

チャートを見て「お!」と思うような動きを、各系列の自分自身の過去と比べて探す。
- 1か月(21営業日)の変化が過去の分布の端にあるもの
- 1年以上ぶりの高値・安値を付けたもの(「いつ以来か」を出す)
- 1日の変化が過去の分布の端にあるもの
- 経済指標(FRED、Actionsで取得)の直近の変化が大きいもの、何年ぶりかの水準になったもの

使い方: python insights/src/scan_big_moves.py [出力先JSON] [--asof YYYY-MM-DD]
--asof を付けると、その日より後のデータ(取引途中の東京の値など)を切り落とす。号の基準日に合わせて使う。
既定の出力先は /tmp/market-data/big_moves_candidates.json。
これは候補の一覧で、号に載せるものは人が選び、解説を付けて editions の big_moves に入れる。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MD = Path("/tmp/market-data")
DR = ROOT / "daily-review" / "data"

# 水準の差(bp・ポイント)で見る系列。それ以外は騰落率で見る。
LEVEL = {"^TNX", "^FVX", "^IRX", "^TYX", "^VIX"}

LABELS = {
    "^GSPC": "S&P500", "^NDX": "ナスダック100", "^DJI": "NYダウ", "^RUT": "ラッセル2000", "^SOX": "SOX指数",
    "^VIX": "VIX", "^N225": "日経平均", "^HSI": "香港ハンセン", "^KS11": "韓国KOSPI", "^TWII": "台湾加権",
    "^STOXX50E": "ユーロストックス50", "^GDAXI": "独DAX", "^FTSE": "英FTSE100",
    "SPY": "SPY", "QQQ": "QQQ", "IWM": "IWM(小型株)", "RSP": "RSP(S&P均等加重)", "SMH": "SMH(半導体)",
    "SOXX": "SOXX(半導体)", "XLB": "米素材", "XLC": "米通信", "XLE": "米エネルギー", "XLF": "米金融",
    "XLI": "米資本財", "XLK": "米テック", "XLP": "米生活必需品", "XLRE": "米不動産", "XLU": "米公益",
    "XLV": "米ヘルスケア", "XLY": "米一般消費財", "EWJ": "EWJ(日本株・ドル建て)", "DXJ": "DXJ(日本株・ヘッジ付)",
    "EEM": "新興国株", "KRE": "米地銀", "IGV": "米ソフトウェア", "ARKK": "ARKK", "HYG": "米ハイイールド債",
    "LQD": "米投資適格社債", "TLT": "米超長期債", "IEF": "米中期債", "SHY": "米短期債", "GLD": "GLD(金)",
    "SLV": "SLV(銀)", "USO": "USO(原油)", "^IRX": "米3か月金利", "^FVX": "米5年金利", "^TNX": "米10年金利",
    "^TYX": "米30年金利", "DX-Y.NYB": "ドル指数", "JPY=X": "ドル円", "EURUSD=X": "ユーロドル",
    "CNY=X": "ドル人民元", "KRW=X": "ドルウォン", "TWD=X": "ドル台湾ドル", "CL=F": "WTI原油", "BZ=F": "ブレント原油",
    "NG=F": "天然ガス", "GC=F": "金先物", "HG=F": "銅先物", "ZN=F": "米10年債先物", "ES=F": "S&P500先物",
    "NQ=F": "ナスダック100先物", "NKD=F": "CME日経先物", "BTC-USD": "ビットコイン", "ETH-USD": "イーサリアム",
    "TSM": "TSMC(ADR)", "ASML": "ASML", "ARM": "Arm", "SNDK": "サンディスク", "CRWV": "CoreWeave", "NBIS": "Nebius",
    "005930.KS": "サムスン電子", "000660.KS": "SKハイニックス", "2330.TW": "TSMC(台湾)", "AMD": "AMD", "AAPL": "アップル",
    "MU": "マイクロン", "NVDA": "エヌビディア", "MSFT": "マイクロソフト", "AMZN": "アマゾン", "GOOGL": "アルファベット",
    "META": "メタ", "ORCL": "オラクル", "285A.T": "キオクシア", "6857.T": "アドバンテスト", "8035.T": "東京エレクトロン",
    "4062.T": "イビデン", "9984.T": "ソフトバンクG", "1570.T": "日経レバETF", "1357.T": "日経ダブルインバース",
    "2558.T": "MAXIS米国株(S&P500)", "1306.T": "TOPIX連動ETF", "1321.T": "日経225連動ETF",
}
# TOPIX-17業種ETF(NEXT FUNDS)
for _code, _name in zip(range(1617, 1634), [
        "食品", "エネルギー資源", "建設・資材", "素材・化学", "医薬品", "自動車・輸送機", "鉄鋼・非鉄", "機械",
        "電機・精密", "情報通信・サービス", "電力・ガス", "運輸・物流", "商社・卸売", "小売", "銀行", "金融(除く銀行)", "不動産"]):
    LABELS[f"{_code}.T"] = f"TOPIX-17 {_name}"

# FRED系列: 名前、単位、変化の見方(diff=水準差 / pct=前年比で見る指数)
FRED_META = {
    "DGS2": ("米2年金利", "%", "diff"),
    "T10Y2Y": ("米10年-2年スプレッド", "%pt", "diff"),
    "T10Y3M": ("米10年-3か月スプレッド", "%pt", "diff"),
    "DFII10": ("米10年実質金利", "%", "diff"),
    "T10YIE": ("米10年ブレークイーブン", "%", "diff"),
    "BAMLH0A0HYM2": ("米ハイイールド債スプレッド", "%pt", "diff"),
    "BAMLC0A0CM": ("米投資適格社債スプレッド", "%pt", "diff"),
    "MORTGAGE30US": ("米30年住宅ローン金利", "%", "diff"),
    "ICSA": ("米新規失業保険申請", "件", "diff"),
    "CCSA": ("米継続受給者数", "件", "diff"),
    "UNRATE": ("米失業率", "%", "diff"),
    "PAYEMS": ("米非農業部門雇用者数", "千人", "mom"),
    "CPIAUCSL": ("米CPI", "指数", "yoy"),
    "CPILFESL": ("米コアCPI", "指数", "yoy"),
    "PCEPILFE": ("米コアPCE", "指数", "yoy"),
    "INDPRO": ("米鉱工業生産", "指数", "yoy"),
    "RSAFS": ("米小売売上高", "百万ドル", "yoy"),
    "UMCSENT": ("ミシガン大消費者信頼感", "指数", "diff"),
    "JTSJOL": ("米求人件数", "千件", "diff"),
    "WALCL": ("FRB総資産", "百万ドル", "diff"),
    "RRPONTSYD": ("FRBリバースレポ残高", "十億ドル", "diff"),
    "WTREGEN": ("米財務省一般口座(TGA)", "百万ドル", "diff"),
    "IRLTLT01JPM156N": ("日本10年国債利回り(月次)", "%", "diff"),
    "STLFSI4": ("セントルイス連銀金融ストレス指数", "指数", "diff"),
}


ASOF: pd.Timestamp | None = None


def cut(s: pd.Series) -> pd.Series:
    return s[s.index <= ASOF] if ASOF is not None else s


def load_prices() -> dict[str, tuple[str, str, pd.Series]]:
    """{key: (label, group, series)}"""
    out = {}
    d = pd.read_parquet(MD / "daily.parquet")
    d["date"] = pd.to_datetime(d["date"]).dt.tz_localize(None).dt.normalize()
    for t, g in d.groupby("ticker"):
        s = cut(g.drop_duplicates("date").set_index("date")["close"].sort_index().dropna())
        out[t] = (LABELS.get(t, t), "市場", s)
    names_us = {x["symbol"]: x["security"] for x in json.loads((DR / "universe_current.detail.json").read_text())}
    names_jp = {x["symbol"]: x["name"] for x in json.loads((DR / "universe_current_jp.detail.json").read_text())}
    for f, group, names in (("prices.parquet", "S&P500採用", names_us), ("prices_jp.parquet", "日経225採用", names_jp)):
        p = pd.read_parquet(DR / f)
        p["date"] = pd.to_datetime(p["date"]).dt.tz_localize(None).dt.normalize()
        col = "adj_close" if "adj_close" in p.columns else "close"
        for t, g in p.groupby("ticker"):
            if t in out:
                continue
            s = cut(g.drop_duplicates("date").set_index("date")[col].sort_index().dropna())
            out[t] = (LABELS.get(t, names.get(t, t)), group, s)
    return out


def since_label(s: pd.Series, high: bool) -> tuple[str | None, int]:
    """直近値が何以来の高値(安値)か。(以来の日付, その間の観測数)。データ全期間で最高(最低)なら日付None。"""
    last = s.iloc[-1]
    prev = s.iloc[:-1]
    mask = prev >= last if high else prev <= last
    if not mask.any():
        return None, len(prev)
    d = prev[mask].index[-1]
    return str(d.date()), int((prev.index > d).sum())


def spark(s: pd.Series, n: int = 260, k: int = 130) -> list:
    x = s.tail(n)
    step = max(1, int(np.ceil(len(x) / k)))
    x = pd.concat([x.iloc[::step], x.iloc[[-1]]])
    x = x[~x.index.duplicated()]
    return [[str(i.date()), round(float(v), 4)] for i, v in x.items()]


def pct_rank(hist: pd.Series, v: float) -> float:
    h = hist.dropna()
    return float((h < v).mean() * 100) if len(h) else np.nan


def scan_prices(series: dict, asof_min: pd.Timestamp) -> list[dict]:
    rows = []
    for key, (label, group, s) in series.items():
        if len(s) < 300 or s.index[-1] < asof_min:
            continue
        lvl = key in LEVEL
        ch21 = (s - s.shift(21)) if lvl else (s / s.shift(21) - 1) * 100
        ch1 = (s - s.shift(1)) if lvl else (s / s.shift(1) - 1) * 100
        p21 = pct_rank(ch21.iloc[:-1], ch21.iloc[-1])
        p1 = pct_rank(ch1.iloc[:-1], ch1.iloc[-1])
        hi_since, hi_n = since_label(s, True)
        lo_since, lo_n = since_label(s, False)
        years = (s.index[-1] - s.index[0]).days / 365.25
        flags = []
        edge = 2.5 if group == "市場" else 1
        if p21 >= 100 - edge or p21 <= edge:
            flags.append(f"1か月の変化が過去の上下{edge:g}%")
        if p1 >= 99.5 or p1 <= 0.5:
            flags.append("1日の変化が過去の上下0.5%")
        if hi_n >= 250:
            flags.append("高値: " + (f"{hi_since}以来" if hi_since else f"取得データ({s.index[0].year}年〜)で最高"))
        if lo_n >= 250:
            flags.append("安値: " + (f"{lo_since}以来" if lo_since else f"取得データ({s.index[0].year}年〜)で最低"))
        if not flags:
            continue
        score = max(abs(p21 - 50), abs(p1 - 50) - 0.5) / 50 + min(max(hi_n, lo_n), 2500) / 2500
        rows.append(dict(
            key=key, label=label, group=group, unit="bp/pt" if lvl else "%", last=round(float(s.iloc[-1]), 4),
            last_date=str(s.index[-1].date()), chg_1d=round(float(ch1.iloc[-1] * (100 if key in LEVEL - {"^VIX"} else 1)), 2),
            chg_21d=round(float(ch21.iloc[-1] * (100 if key in LEVEL - {"^VIX"} else 1)), 2),
            pct_21d=round(p21, 1), pct_1d=round(p1, 1), high_since=hi_since if hi_n >= 250 else None,
            low_since=lo_since if lo_n >= 250 else None, history_years=round(years, 1), flags=flags,
            score=round(score, 3), series=spark(s),
        ))
    return sorted(rows, key=lambda r: -r["score"])


def scan_fred() -> list[dict]:
    f = MD / "fred.parquet"
    if not f.exists():
        return []
    d = pd.read_parquet(f)
    d["date"] = pd.to_datetime(d["date"])
    rows = []
    for sid, g in d.groupby("series"):
        s = cut(g.set_index("date")["value"].sort_index().dropna())
        if len(s) < 30:
            continue
        name, unit, how = FRED_META.get(sid, (sid, "", "diff"))
        freq = pd.infer_freq(s.index[-12:]) or ""
        per_year = 252 if len(s) / max((s.index[-1] - s.index[0]).days / 365.25, 1) > 200 else (52 if len(s) / max((s.index[-1] - s.index[0]).days / 365.25, 1) > 40 else 12)
        if how == "yoy":
            # 欠損月(例: 2025年10月のCPI)があっても月がずれないよう、日付で1年前と比べる
            prev = s.reindex(s.index - pd.DateOffset(years=1))
            v = pd.Series((s.values / prev.values - 1) * 100, index=s.index).dropna()
            base = v
            ch = v.diff()
        elif how == "mom":
            v = s.diff()
            base = v
            ch = v
        else:
            v = s
            base = s
            ch = s.diff(21 if per_year == 252 else (4 if per_year == 52 else 1))
        v = v.dropna()
        if len(v) < 24:
            continue
        hi_since, hi_n = since_label(v, True)
        lo_since, lo_n = since_label(v, False)
        p = pct_rank(ch.iloc[:-1], ch.iloc[-1])
        flags = []
        if p >= 98 or p <= 2:
            flags.append("直近の変化が過去の上下2%")
        thr = {252: 250, 52: 52, 12: 12}[per_year]
        if hi_n >= thr:
            flags.append("高水準: " + (f"{hi_since}以来" if hi_since else "取得データで最高"))
        if lo_n >= thr:
            flags.append("低水準: " + (f"{lo_since}以来" if lo_since else "取得データで最低"))
        rows.append(dict(
            key=sid, label=name, group="経済指標", unit=unit, how=how, last=round(float(v.iloc[-1]), 4),
            last_date=str(v.index[-1].date()), chg=round(float(ch.iloc[-1]), 4) if not np.isnan(ch.iloc[-1]) else None,
            pct_chg=round(p, 1), high_since=hi_since if hi_n >= thr else None, low_since=lo_since if lo_n >= thr else None,
            flags=flags, score=round(abs(p - 50) / 50 + min(max(hi_n, lo_n), thr * 10) / (thr * 10), 3),
            series=spark(v, n=per_year * 5 if per_year < 252 else 520, k=130),
        ))
    return sorted(rows, key=lambda r: -r["score"])


def main():
    global ASOF
    args = sys.argv[1:]
    if "--asof" in args:
        i = args.index("--asof")
        ASOF = pd.Timestamp(args[i + 1])
        del args[i:i + 2]
    out_path = Path(args[0]) if args else MD / "big_moves_candidates.json"
    series = load_prices()
    last_us = series["^GSPC"][2].index[-1]
    prices = scan_prices(series, last_us - pd.Timedelta(days=5))
    out = {
        "as_of": str(last_us.date()),
        "market": [r for r in prices if r["group"] == "市場"][:25],
        "sp500": [r for r in prices if r["group"] == "S&P500採用"][:15],
        "nikkei225": [r for r in prices if r["group"] == "日経225採用"][:15],
        "econ": scan_fred(),
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for k in ("market", "sp500", "nikkei225", "econ"):
        print(f"== {k} ({len(out[k])})")
        for r in out[k][:25]:
            extra = f"1d {r.get('chg_1d')} / 21d {r.get('chg_21d')} (pct21 {r.get('pct_21d')})" if k != "econ" else f"last {r['last']} chg {r['chg']} (pct {r['pct_chg']}) {r['last_date']}"
            print(f"  {r['label']:<24} {extra} | {'; '.join(r['flags'])}")


if __name__ == "__main__":
    main()
