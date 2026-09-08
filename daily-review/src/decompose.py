"""層1: リターン分解（SPEC_1.md）。米国・日本共通コード（MarketContextで切替）。

1. 指数リターン
2. セクター寄与度（自前計算: セクター内均等加重リターン x ウェイト近似。
   ETFベースの簡易版も並記）
3. ファクター寄与度（価格ベース4ファクター: Momentum/Beta/Volatility/Liquidity を
   クインタイル・ロングショートで自前計算。Value/Growth/Quality/Size はファンダ
   メンタルズ・スナップショットが揃い次第追加。ETFベースの簡易版も並記）
4. 個別銘柄の寄与上位・下位（各10銘柄。時価総額ウェイトが取れれば使用、
   無ければ等加重）

すべて「日付ごとの時系列」として計算する（層2のローリングzスコアの入力になるため）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from data_layer import MarketDataStore
from fundamentals import load_fundamentals
from market_context import MarketContext

MOMENTUM_LOOKBACK = 252
MOMENTUM_SKIP = 21
VOL_WINDOW = 60
BETA_WINDOW = 60
LIQUIDITY_WINDOW = 60
QUINTILE = 0.2


BAD_TICK_RATIO = 3.0  # 前後1週間の中央値に対しこの倍率を超えて乖離（またはその逆数未満）したら異常値扱い
BAD_TICK_MAX_SPAN = 3  # 異常値が連続しうる最大日数（これを超えて続く場合は本物の変動とみなし補正しない）


def clean_bad_ticks(close: pd.DataFrame, window: int = 7, ratio: float = BAD_TICK_RATIO) -> pd.DataFrame:
    """データソース側の異常値（1〜数日だけの往復スパイク）を検出し、前後の価格で補間する。

    実例: 2026年のJPデータで、あるETFが2日間だけ約283円→0.55円→0.55円→288円という
    往復パターンを示した（出来高も同時に異常値）。分割・配当調整の問題ではなく
    フィード側の生データ異常だった。単純な隣接日リターンの符号反転チェックでは
    2日以上続くスパイクを見逃すため、前後`window`日の中央値との乖離倍率で判定する。
    """
    cleaned = close.copy()
    fixed = []
    for col in close.columns:
        s = close[col]
        med = s.rolling(window * 2 + 1, center=True, min_periods=window).median()
        with np.errstate(divide="ignore", invalid="ignore"):
            dev_ratio = s / med
        is_bad = ((dev_ratio > ratio) | (dev_ratio < 1 / ratio)) & med.notna()
        if not is_bad.any():
            continue
        # 連続する異常値ブロックごとに、直前・直後の正常値で線形補間する
        idx_positions = np.where(is_bad.values)[0]
        groups = np.split(idx_positions, np.where(np.diff(idx_positions) > 1)[0] + 1)
        for g in groups:
            if len(g) > BAD_TICK_MAX_SPAN:
                continue  # 長期間続く場合は本物の急落/急騰の可能性が高いので触らない
            start, end = g[0], g[-1]
            if start == 0 or end == len(s) - 1:
                continue  # 系列の端は前後どちらかの参照点が無いためスキップ
            prev_val, next_val = s.iloc[start - 1], s.iloc[end + 1]
            n = end - start + 2
            for k, pos in enumerate(range(start, end + 1), start=1):
                interp = prev_val + (next_val - prev_val) * k / n
                cleaned.iloc[pos, cleaned.columns.get_loc(col)] = interp
                fixed.append((col, close.index[pos].date()))
    if fixed:
        print(f"  [warn] 異常値(前後{window}日中央値の{ratio}倍を超える乖離)を{len(fixed)}件補正しました: {fixed[:10]}")
    return cleaned


def compute_returns(store: MarketDataStore) -> pd.DataFrame:
    close = clean_bad_ticks(store.wide_close())
    return close.pct_change()


def index_return_series(returns: pd.DataFrame, index_ticker: str) -> pd.Series:
    return returns[index_ticker].rename("index_return")


def sector_return_series(returns: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    """セクターごとの等加重平均リターン（自前計算）。"""
    sector_map = universe.set_index("symbol")["sector"]
    out = {}
    for sector in sector_map.unique():
        members = [t for t in sector_map[sector_map == sector].index if t in returns.columns]
        if not members:
            continue
        out[sector] = returns[members].mean(axis=1)
    return pd.DataFrame(out)


def sector_contribution(sector_returns: pd.DataFrame, weights: dict[str, float]) -> pd.DataFrame:
    """セクター寄与度 = セクターリターン x ウェイト近似（自前計算）。"""
    cols = {}
    for sector in sector_returns.columns:
        w = weights.get(sector, np.nan)
        cols[sector] = sector_returns[sector] * w
    return pd.DataFrame(cols)


def sector_etf_returns(returns: pd.DataFrame, sector_etfs: dict[str, str]) -> pd.DataFrame:
    """ETFベースの簡易版セクターリターン（整合性チェック用）。"""
    cols = {name: returns[etf] for etf, name in sector_etfs.items() if etf in returns.columns}
    return pd.DataFrame(cols)


def _quintile_long_short(metric: pd.DataFrame, returns: pd.DataFrame) -> pd.Series:
    """各日、metricの上位20%平均リターン - 下位20%平均リターン（等加重ロングショート）。"""
    common_dates = metric.index.intersection(returns.index)
    out = pd.Series(index=common_dates, dtype=float)
    for d in common_dates:
        m = metric.loc[d].dropna()
        if len(m) < 20:
            continue
        r = returns.loc[d]
        n_q = max(1, int(len(m) * QUINTILE))
        top = m.nlargest(n_q).index
        bottom = m.nsmallest(n_q).index
        top_ret = r.reindex(top).mean()
        bottom_ret = r.reindex(bottom).mean()
        out[d] = top_ret - bottom_ret
    return out


def price_based_factor_returns(returns: pd.DataFrame, index_ticker: str) -> dict[str, pd.Series]:
    """価格・出来高データのみから自前計算できる3ファクター（Momentum/Volatility/Beta）。"""
    close = (1 + returns).cumprod()

    cum_ret_252 = close.shift(MOMENTUM_SKIP) / close.shift(MOMENTUM_LOOKBACK + MOMENTUM_SKIP) - 1
    momentum_factor = _quintile_long_short(cum_ret_252, returns)

    realized_vol = returns.rolling(VOL_WINDOW).std()
    volatility_factor = _quintile_long_short(realized_vol, returns)

    mkt = returns[index_ticker]
    cov = returns.rolling(BETA_WINDOW).cov(mkt)
    var = mkt.rolling(BETA_WINDOW).var()
    beta = cov.div(var, axis=0)
    beta_factor = _quintile_long_short(beta, returns)

    return {"Momentum": momentum_factor, "Volatility": volatility_factor, "Beta": beta_factor}


def liquidity_factor_returns(store: MarketDataStore, returns: pd.DataFrame) -> pd.Series:
    df = store.load()
    df = df.copy()
    df["dollar_vol"] = df["close"] * df["volume"]
    dv = df.pivot_table(index="date", columns="ticker", values="dollar_vol")
    adv = dv.rolling(LIQUIDITY_WINDOW).mean()
    return _quintile_long_short(adv, returns)


def fundamental_factor_returns(returns: pd.DataFrame, fundamentals_path) -> dict[str, pd.Series]:
    """Value/Growth/Quality/Size（ファンダメンタルズ・スナップショット依存）。

    スナップショットは日次で変化しないため、直近値を全期間に適用した「現在の
    ファクター構成で過去を評価する」近似になる点に注意（週次更新を想定）。
    """
    fnd = load_fundamentals(fundamentals_path).set_index("ticker")
    if fnd.empty:
        return {}

    def _static_metric(col_values: pd.Series) -> pd.DataFrame:
        v = col_values.reindex(returns.columns)
        return pd.DataFrame(np.tile(v.values, (len(returns.index), 1)), index=returns.index, columns=returns.columns)

    out = {}
    if "priceToBook" in fnd.columns:
        out["Value"] = _quintile_long_short(_static_metric(-fnd["priceToBook"]), returns)
    if "revenueGrowth" in fnd.columns:
        out["Growth"] = _quintile_long_short(_static_metric(fnd["revenueGrowth"]), returns)
    if "returnOnEquity" in fnd.columns:
        out["Quality"] = _quintile_long_short(_static_metric(fnd["returnOnEquity"]), returns)
    if "marketCap" in fnd.columns:
        out["Size"] = _quintile_long_short(_static_metric(-fnd["marketCap"]), returns)
    return out


def factor_etf_returns(returns: pd.DataFrame, factor_etfs: dict[str, str]) -> pd.DataFrame:
    """ETFベースの簡易版ファクターリターン（整合性チェック用）。"""
    cols = {name: returns[etf] for etf, name in factor_etfs.items() if etf in returns.columns}
    return pd.DataFrame(cols)


def top_bottom_contributors(
    returns: pd.DataFrame, date, universe: pd.DataFrame, fundamentals_path, n: int = 10
) -> pd.DataFrame:
    """指定日の個別銘柄寄与上位・下位n銘柄（時価総額ウェイトが取れれば使用）。"""
    tickers = [t for t in universe["symbol"] if t in returns.columns]
    r = returns.loc[date, tickers].dropna()

    fnd = load_fundamentals(fundamentals_path).set_index("ticker")
    if not fnd.empty and "marketCap" in fnd.columns:
        w = fnd["marketCap"].reindex(r.index)
        w = w / w.sum()
        contribution = r * w
    else:
        contribution = r / len(r)

    contribution = contribution.dropna().sort_values(ascending=False)
    top = contribution.head(n)
    bottom = contribution.tail(n).sort_values()
    return pd.DataFrame(
        {
            "ticker": list(top.index) + list(bottom.index),
            "return": list(r.reindex(top.index)) + list(r.reindex(bottom.index)),
            "contribution": list(top.values) + list(bottom.values),
            "group": ["top"] * len(top) + ["bottom"] * len(bottom),
        }
    )


def breadth_metrics(returns: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    """相場の「厚み」＝指数が一部の銘柄だけで動いているか、幅広く動いているか。

    値上がり銘柄比率(advance_pct)が低いのに指数が大きく上昇している日は
    「一部の大型株だけが指数を押し上げている」相場、逆に比率が指数の動きと
    一致していれば「幅広い相場」と読める。PCAより直感的に伝えられる指標として
    層2の異常検知・日次レポートの両方で使う。
    """
    members = [t for t in universe["symbol"] if t in returns.columns]
    sub = returns[members]
    advancers = (sub > 0).sum(axis=1)
    decliners = (sub < 0).sum(axis=1)
    total = advancers + decliners
    advance_pct = (advancers / total.replace(0, np.nan)).rename("advance_pct")
    return pd.DataFrame({"advance_pct": advance_pct, "advancers": advancers, "decliners": decliners})


class Layer1Result:
    def __init__(self, returns, index_ret, sector_contrib, sector_etf_ret, factor_ret, factor_etf_ret, breadth):
        self.returns = returns
        self.index_ret = index_ret
        self.sector_contrib = sector_contrib
        self.sector_etf_ret = sector_etf_ret
        self.factor_ret = factor_ret
        self.factor_etf_ret = factor_etf_ret
        self.breadth = breadth


def run_layer1(ctx: MarketContext) -> Layer1Result:
    returns = compute_returns(ctx.price_store)

    idx_ret = index_return_series(returns, ctx.index_ticker)
    sec_ret = sector_return_series(returns, ctx.universe_df)
    sec_contrib = sector_contribution(sec_ret, ctx.sector_weights)
    sec_etf_ret = sector_etf_returns(returns, ctx.sector_etfs)

    factors = price_based_factor_returns(returns, ctx.index_ticker)
    factors["Liquidity"] = liquidity_factor_returns(ctx.price_store, returns)
    factors.update(fundamental_factor_returns(returns, ctx.fundamentals_path))
    factor_df = pd.DataFrame(factors)
    factor_etf_df = factor_etf_returns(returns, ctx.factor_etfs)

    breadth = breadth_metrics(returns, ctx.universe_df)

    return Layer1Result(returns, idx_ret, sec_contrib, sec_etf_ret, factor_df, factor_etf_df, breadth)


if __name__ == "__main__":
    import sys

    import console_utf8  # noqa: F401
    from market_context import jp_context, us_context

    ctx = jp_context() if "--jp" in sys.argv else us_context()
    result = run_layer1(ctx)
    last_date = result.index_ret.dropna().index[-1]
    print(f"=== 層1 リターン分解（{ctx.label}, {ctx.index_display}） ({last_date.date()}) ===")
    print(f"指数リターン: {result.index_ret.loc[last_date]:+.2%}")
    print("\n--- セクター寄与度（自前計算） ---")
    print(result.sector_contrib.loc[last_date].sort_values(ascending=False).apply(lambda x: f"{x:+.3%}"))
    print("\n--- ファクターリターン（自前計算） ---")
    print(result.factor_ret.loc[last_date].apply(lambda x: f"{x:+.3%}" if pd.notna(x) else "N/A"))
    print("\n--- 個別銘柄 寄与上位/下位10 ---")
    print(top_bottom_contributors(result.returns, last_date, ctx.universe_df, ctx.fundamentals_path))
