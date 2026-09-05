"""層4: 構造変化モニタ（SPEC_1.md）。週次バッチ、月次サマリー付き。米国・日本共通。

- PC1説明力（長期軸=250日ローリング）の推移とそのローリングzスコア
- 短期軸(60日) vs 長期軸(250日) のPC1・PC2ローディング相関（絶対値）。
  0.8を下回ったら「構造変化の疑い」フラグ
- PC1〜PC3のローディング上位・下位セクターの入れ替わり（先週比）
- 残差比率の週次平均の推移
- セクター間平均相関の推移（20日・60日）
- 月次: 上記を1ページに要約

週ごとのスナップショットは一度計算したら data/structure_history_{market}.parquet に
保存し、以後は未計算の週だけを追加計算する（差分更新、全期間の再計算はしない）。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config import DATA_DIR
from market_context import MarketContext
from pca import estimate_axes, project

SHORT_WINDOW = 60
LONG_WINDOW = 250
CORR_FLAG_THRESHOLD = 0.8
TOP_N_SECTORS = 3
STRUCTURE_ZSCORE_WINDOW = 26  # 週次系列なので26週(半年)をローリングzスコア窓にする
MIN_HISTORY_FOR_LONG = LONG_WINDOW + 10


def _history_path(ctx: MarketContext) -> Path:
    return DATA_DIR / f"structure_history_{ctx.name}.parquet"


def _week_ending_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """returnsの日付インデックスから「各週最後の営業日」の一覧を返す。"""
    s = pd.Series(index, index=index)
    return list(s.groupby(index.to_period("W")).max())


def _sector_loadings(loadings: np.ndarray, tickers: list[str], universe: pd.DataFrame, n_pc: int) -> pd.DataFrame:
    sector_map = universe.set_index("symbol")["sector"]
    df = pd.DataFrame(loadings[:, :n_pc], index=tickers, columns=[f"PC{i+1}" for i in range(n_pc)])
    df["sector"] = sector_map.reindex(df.index)
    return df.groupby("sector").mean()


def _top_bottom_str(sector_loadings: pd.DataFrame, pc: str, n: int = TOP_N_SECTORS) -> tuple[str, str]:
    s = sector_loadings[pc].sort_values(ascending=False)
    return ",".join(s.head(n).index), ",".join(s.tail(n).index)


def compute_week_snapshot(ctx: MarketContext, returns: pd.DataFrame, sector_returns: pd.DataFrame, date: pd.Timestamp) -> dict | None:
    """指定週末時点までのデータのみを使い、その週のスナップショットを計算する。"""
    hist = returns.loc[:date]
    if len(hist) < MIN_HISTORY_FOR_LONG:
        return None

    member_cols = [t for t in ctx.universe_df["symbol"] if t in hist.columns]
    stock_hist = hist[member_cols]

    try:
        short_axes = estimate_axes(stock_hist, method="rolling", window=SHORT_WINDOW)
        long_axes = estimate_axes(stock_hist, method="rolling", window=LONG_WINDOW)
    except ValueError:
        return None

    common = [t for t in long_axes["tickers"] if t in short_axes["tickers"]]
    short_load = pd.DataFrame(short_axes["loadings"], index=short_axes["tickers"]).loc[common].values
    long_load = pd.DataFrame(long_axes["loadings"], index=long_axes["tickers"]).loc[common].values
    pc1_corr = abs(np.corrcoef(short_load[:, 0], long_load[:, 0])[0, 1])
    pc2_corr = abs(np.corrcoef(short_load[:, 1], long_load[:, 1])[0, 1])

    week_days = hist.index[hist.index.to_period("W") == date.to_period("W")]
    _, resid = project(stock_hist, long_axes, history_days=max(len(week_days) + 2, 5))
    resid_week_avg = resid.reindex(week_days).dropna().mean()

    sec_hist = sector_returns.loc[:date].dropna(how="all")
    corr20 = sec_hist.tail(20 + 1).corr().where(~np.eye(len(sec_hist.columns), dtype=bool)).stack().mean() \
        if len(sec_hist) >= 20 else np.nan
    corr60 = sec_hist.tail(60 + 1).corr().where(~np.eye(len(sec_hist.columns), dtype=bool)).stack().mean() \
        if len(sec_hist) >= 60 else np.nan

    sec_load = _sector_loadings(np.array(long_axes["loadings"]), long_axes["tickers"], ctx.universe_df, n_pc=3)
    pc1_top, pc1_bottom = _top_bottom_str(sec_load, "PC1")
    pc2_top, pc2_bottom = _top_bottom_str(sec_load, "PC2")
    pc3_top, pc3_bottom = _top_bottom_str(sec_load, "PC3")

    return {
        "week_ending": date,
        "pc1_explained": long_axes["explained_variance_ratio"][0],
        "pc2_explained": long_axes["explained_variance_ratio"][1],
        "pc1_short_long_corr": pc1_corr,
        "pc2_short_long_corr": pc2_corr,
        "structure_change_flag": bool(pc1_corr < CORR_FLAG_THRESHOLD or pc2_corr < CORR_FLAG_THRESHOLD),
        "residual_ratio_week_avg": float(resid_week_avg) if pd.notna(resid_week_avg) else np.nan,
        "sector_corr_20d": float(corr20) if pd.notna(corr20) else np.nan,
        "sector_corr_60d": float(corr60) if pd.notna(corr60) else np.nan,
        "pc1_top_sectors": pc1_top, "pc1_bottom_sectors": pc1_bottom,
        "pc2_top_sectors": pc2_top, "pc2_bottom_sectors": pc2_bottom,
        "pc3_top_sectors": pc3_top, "pc3_bottom_sectors": pc3_bottom,
    }


def run_layer4(ctx: MarketContext, returns: pd.DataFrame, sector_returns: pd.DataFrame, max_weeks_backfill: int = 26) -> pd.DataFrame:
    """週次スナップショットを差分更新し、全履歴を返す。"""
    path = _history_path(ctx)
    history = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    done_weeks = set(pd.to_datetime(history["week_ending"])) if not history.empty else set()

    all_week_ends = _week_ending_dates(returns.index)
    candidates = all_week_ends[-max_weeks_backfill:] if not done_weeks else all_week_ends
    todo = [d for d in candidates if d not in done_weeks]

    new_rows = []
    for d in todo:
        snap = compute_week_snapshot(ctx, returns, sector_returns, d)
        if snap is not None:
            new_rows.append(snap)

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        history = pd.concat([history, new_df], ignore_index=True) if not history.empty else new_df
        history = history.sort_values("week_ending").drop_duplicates("week_ending", keep="last").reset_index(drop=True)
        history.to_parquet(path, index=False)
        print(f"  層4: {len(new_rows)}週分のスナップショットを新規計算しました。")

    return history


def rolling_zscore_weekly(series: pd.Series, window: int = STRUCTURE_ZSCORE_WINDOW) -> pd.Series:
    mean = series.rolling(window).mean()
    std = series.rolling(window).std()
    return (series - mean) / std


def latest_week_over_week_narrative(history: pd.DataFrame) -> list[str]:
    """先週比でPC1〜PC3の上位/下位セクールが入れ替わっていれば言語化する。"""
    if len(history) < 2:
        return []
    cur, prev = history.iloc[-1], history.iloc[-2]
    notes = []
    for pc, label in [("pc1_top_sectors", "PC1（第1主成分）"), ("pc2_top_sectors", "PC2（第2主成分）"), ("pc3_top_sectors", "PC3（第3主成分）")]:
        if cur[pc] != prev[pc]:
            notes.append(f"{label}の上位セクターが「{prev[pc]}」→「{cur[pc]}」に変化")
    if cur["structure_change_flag"] and not prev["structure_change_flag"]:
        notes.append(
            f"短期軸(60日)と長期軸(250日)のPC1ローディング相関が{cur['pc1_short_long_corr']:.2f}まで低下し、"
            f"構造変化の疑いフラグが立ちました（しきい値{CORR_FLAG_THRESHOLD}）"
        )
    return notes


def monthly_summary(history: pd.DataFrame) -> pd.DataFrame:
    """月次: 各指標の月内平均に要約する。"""
    if history.empty:
        return history
    h = history.copy()
    h["month"] = pd.to_datetime(h["week_ending"]).dt.to_period("M")
    numeric_cols = ["pc1_explained", "pc2_explained", "pc1_short_long_corr", "pc2_short_long_corr",
                    "residual_ratio_week_avg", "sector_corr_20d", "sector_corr_60d"]
    agg = h.groupby("month")[numeric_cols].mean()
    agg["structure_change_flag_any"] = h.groupby("month")["structure_change_flag"].any()
    return agg


if __name__ == "__main__":
    import sys

    import console_utf8  # noqa: F401
    from decompose import compute_returns, sector_return_series, sector_etf_returns
    from market_context import jp_context, us_context

    ctx = jp_context() if "--jp" in sys.argv else us_context()
    returns = compute_returns(ctx.price_store)
    sector_returns = sector_etf_returns(returns, ctx.sector_etfs)

    history = run_layer4(ctx, returns, sector_returns)
    print(f"=== 層4 構造変化モニタ（{ctx.label}） ===")
    print(history.tail(8).to_string())

    print("\n--- 先週比の変化 ---")
    for note in latest_week_over_week_narrative(history):
        print(f"  - {note}")

    print("\n--- 月次サマリー ---")
    print(monthly_summary(history).to_string())
