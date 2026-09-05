"""層2: 異常検知（SPEC_1.md）。米国・日本共通コード（MarketContextで切替）。

各系列（セクター寄与度・ファクターリターン・追加指標）を直近N日ローリング
標準偏差でzスコア化し、|z| >= しきい値を「本日の論点」として抽出する。

実装メモ: 3年分・数百系列でも pandas の rolling().mean()/.std() は
十分高速（1回のバッチ実行で1秒未満）なため、「当日追加・N日前削除の
差分更新」を素朴なオンライン平均・分散として別実装することはせず、
毎回ウィンドウ内で再計算する方式にしている（結果は完全に同一）。
"""

from __future__ import annotations

import pandas as pd

from config import SECTOR_CORR_WINDOW, ZSCORE_THRESHOLD, ZSCORE_WINDOW
from market_context import MarketContext


def rolling_zscore(series: pd.Series, window: int = ZSCORE_WINDOW) -> pd.Series:
    mean = series.rolling(window).mean()
    std = series.rolling(window).std()
    return (series - mean) / std


def cross_sectional_dispersion(returns: pd.DataFrame, universe: pd.DataFrame) -> pd.Series:
    """指数構成銘柄リターンの横断的標準偏差（日次）。"""
    members = [t for t in universe["symbol"] if t in returns.columns]
    return returns[members].std(axis=1, skipna=True).rename("cross_sectional_dispersion")


def sector_avg_correlation(sector_returns: pd.DataFrame, window: int = SECTOR_CORR_WINDOW) -> pd.Series:
    """セクター間平均相関（直近window日のローリング相関を全ペア平均）。"""
    n = sector_returns.shape[1]
    corr_sum = pd.Series(0.0, index=sector_returns.index)
    corr_count = 0
    cols = sector_returns.columns
    for i in range(n):
        for j in range(i + 1, n):
            c = sector_returns[cols[i]].rolling(window).corr(sector_returns[cols[j]])
            corr_sum = corr_sum.add(c, fill_value=0.0)
            corr_count += 1
    if corr_count == 0:
        return pd.Series(dtype=float, name="sector_avg_correlation")
    return (corr_sum / corr_count).rename("sector_avg_correlation")


def sector_internal_dispersion(returns: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    """セクター内の銘柄リターン標準偏差（セクター内の分裂を検知）。セクター別に系列を返す。"""
    sector_map = universe.set_index("symbol")["sector"]
    out = {}
    for sector in sector_map.unique():
        members = [t for t in sector_map[sector_map == sector].index if t in returns.columns]
        if len(members) < 3:
            continue
        out[sector] = returns[members].std(axis=1, skipna=True)
    return pd.DataFrame(out)


PRIORITY_METRICS = ("pca:residual_ratio", "pca_sector:residual_ratio")


class Layer2Result:
    def __init__(self, zscored: pd.DataFrame, raw: pd.DataFrame):
        self.zscored = zscored
        self.raw = raw

    def talking_points(self, date, threshold: float = ZSCORE_THRESHOLD, top_n: int = 5) -> pd.DataFrame:
        """|z| >= threshold の指標を返す。残差比率（PCA）が閾値を超えた場合は、
        「過去の構造で説明できない動き」として最重要論点とみなし最上段に置く
        （仕様書の指定どおり）。それ以外は|z|の大きい順。
        """
        if date not in self.zscored.index:
            return pd.DataFrame(columns=["metric", "value", "zscore"])
        z = self.zscored.loc[date].dropna()
        flagged = z[z.abs() >= threshold]

        priority = flagged[flagged.index.isin(PRIORITY_METRICS)].sort_values(key=lambda s: s.abs(), ascending=False)
        rest = flagged[~flagged.index.isin(PRIORITY_METRICS)].sort_values(key=lambda s: s.abs(), ascending=False)
        ordered = pd.concat([priority, rest])

        raw_vals = self.raw.loc[date, ordered.index]
        df = pd.DataFrame({"metric": ordered.index, "value": raw_vals.values, "zscore": ordered.values})
        return df.head(top_n)


def run_layer2(ctx: MarketContext, layer1_result, layer3_result=None) -> Layer2Result:
    from decompose import sector_return_series

    returns = layer1_result.returns
    universe = ctx.universe_df

    metrics = {}
    for col in layer1_result.sector_contrib.columns:
        metrics[f"sector:{col}"] = layer1_result.sector_contrib[col]
    for col in layer1_result.factor_ret.columns:
        metrics[f"factor:{col}"] = layer1_result.factor_ret[col]

    metrics["dispersion:cross_sectional"] = cross_sectional_dispersion(returns, universe)
    sec_ret_raw = sector_return_series(returns, universe)
    metrics["correlation:sector_avg"] = sector_avg_correlation(sec_ret_raw)

    sector_disp = sector_internal_dispersion(returns, universe)
    for col in sector_disp.columns:
        metrics[f"sector_internal_dispersion:{col}"] = sector_disp[col]

    if layer3_result is not None:
        for col in layer3_result.pc_scores.columns[:3]:  # PC1〜PC3
            metrics[f"pca:{col}"] = layer3_result.pc_scores[col]
        metrics["pca:residual_ratio"] = layer3_result.residual_ratio
        for col in layer3_result.pc_scores_sector.columns[:3]:
            metrics[f"pca_sector:{col}"] = layer3_result.pc_scores_sector[col]
        metrics["pca_sector:residual_ratio"] = layer3_result.residual_ratio_sector

    raw = pd.DataFrame(metrics)
    zscored = raw.apply(rolling_zscore)
    return Layer2Result(zscored, raw)


if __name__ == "__main__":
    import sys

    import console_utf8  # noqa: F401
    from decompose import run_layer1
    from market_context import jp_context, us_context

    from pca import run_layer3

    ctx = jp_context() if "--jp" in sys.argv else us_context()
    l1 = run_layer1(ctx)
    l3 = run_layer3(ctx, l1.returns)
    l2 = run_layer2(ctx, l1, l3)
    last_date = l1.index_ret.dropna().index[-1]

    print(f"=== 層2 異常検知（{ctx.label}）: 本日の論点 ({last_date.date()}, |z| >= {ZSCORE_THRESHOLD}) ===")
    tp = l2.talking_points(last_date)
    if tp.empty:
        print("本日、しきい値を超える論点はありませんでした。")
    else:
        for _, row in tp.iterrows():
            print(f"  {row['metric']:45s} value={row['value']:+.4f}  z={row['zscore']:+.2f}")
