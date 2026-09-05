"""層3: PCA（SPEC_1.md）。米国・日本共通（MarketContext経由）。

- 推定：過去250日（rolling）または全履歴のEWMA（半減期60日）共分散から
  主成分（ローディング）を推定し、ファイルに保存。再推定は週1回。
- 毎日：保存済みの軸にその日のリターンベクトルを射影し、PC1〜PC5座標と
  残差比率（PC1〜PC5で説明できなかった当日の断面分散の比率）を計算する。
- 単日データでPCAを再計算することはない（run_layer3は既存軸を使い回す）。
- セクターETFレベルでも同じ処理を行い、銘柄レベルPCAと並記する
  （軽量版・yfinance障害時のフォールバック）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from config import DATA_DIR
from market_context import MarketContext

N_COMPONENTS = 5
ROLLING_WINDOW = 250
EWMA_HALFLIFE = 60
RE_ESTIMATE_INTERVAL_DAYS = 7
MIN_HISTORY_DAYS = 260
PROJECTION_HISTORY_DAYS = 150  # zスコア化用の過去分布を作る日数（>= zscore window推奨だが軽量化のため150）


def _axes_path(ctx: MarketContext, level: str) -> Path:
    return DATA_DIR / f"pca_axes_{ctx.name}_{level}.json"


def _ewma_weights(n: int, halflife: float) -> np.ndarray:
    lam = np.exp(np.log(0.5) / halflife)
    w = lam ** np.arange(n - 1, -1, -1)  # 直近ほど大きい
    return w / w.sum()


def _covariance(mat: pd.DataFrame, method: str, window: int | None = None) -> np.ndarray:
    """mat: (T日 x K銘柄) リターン行列（NaNなし）。分散共分散行列(K x K)を返す。"""
    x = mat.values
    x = x - x.mean(axis=0, keepdims=True)
    if method == "ewma":
        w = _ewma_weights(len(mat), EWMA_HALFLIFE)
        return (x * w[:, None]).T @ x
    # rolling: 直近window日（既定ROLLING_WINDOW）の単純共分散
    x = x[-(window or ROLLING_WINDOW):]
    return (x.T @ x) / (len(x) - 1)


def estimate_axes(returns: pd.DataFrame, method: str = "ewma", window: int | None = None) -> dict:
    """完全データが揃う銘柄のみでPCAを推定し、辞書（保存用）を返す。

    window: methodが"rolling"のときの窓幅（層4の短期軸60日/長期軸250日比較用）。
    """
    valid_cols = returns.columns[returns.notna().mean() >= 0.95]
    mat = returns[valid_cols].dropna()
    min_required = window if (method == "rolling" and window) else MIN_HISTORY_DAYS
    if len(mat) < min_required or mat.shape[1] < N_COMPONENTS + 1:
        raise ValueError(f"PCA推定に必要なデータが不足しています（{len(mat)}日 x {mat.shape[1]}銘柄）")

    cov = _covariance(mat, method, window)
    eigvals, eigvecs = np.linalg.eigh(cov)  # 昇順
    order = np.argsort(eigvals)[::-1][:N_COMPONENTS]
    loadings = eigvecs[:, order]  # K x N_COMPONENTS
    explained = eigvals[order] / eigvals.sum()

    return {
        "estimated_at": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "tickers": list(mat.columns),
        "loadings": loadings.tolist(),
        "explained_variance_ratio": explained.tolist(),
    }


def save_axes(ctx: MarketContext, level: str, axes: dict) -> None:
    _axes_path(ctx, level).write_text(json.dumps(axes), encoding="utf-8")


def load_axes(ctx: MarketContext, level: str) -> dict | None:
    p = _axes_path(ctx, level)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def needs_reestimation(axes: dict | None) -> bool:
    if axes is None:
        return True
    estimated_at = datetime.fromisoformat(axes["estimated_at"])
    age_days = (datetime.now(timezone.utc) - estimated_at).days
    return age_days >= RE_ESTIMATE_INTERVAL_DAYS


def ensure_axes(ctx: MarketContext, level: str, returns: pd.DataFrame, method: str = "ewma") -> dict:
    axes = load_axes(ctx, level)
    if needs_reestimation(axes):
        axes = estimate_axes(returns, method=method)
        save_axes(ctx, level, axes)
    return axes


def project(returns: pd.DataFrame, axes: dict, history_days: int = PROJECTION_HISTORY_DAYS) -> tuple[pd.DataFrame, pd.Series]:
    """保存済み軸に、直近history_days分のリターンを射影する。

    戻り値: (PC1..PCnのDataFrame, 残差比率のSeries)。単日ではなく直近分を
    まとめて返すのは、zスコア化に使う過去分布を作るため（PCA自体の再計算はしない）。
    """
    tickers = axes["tickers"]
    loadings = np.array(axes["loadings"])  # K x N

    sub = returns[tickers].tail(history_days).fillna(0.0)
    pc_scores = sub.values @ loadings  # T x N
    pc_df = pd.DataFrame(pc_scores, index=sub.index, columns=[f"PC{i+1}" for i in range(loadings.shape[1])])

    reconstructed = pc_scores @ loadings.T  # T x K
    residual = sub.values - reconstructed
    actual_var = sub.values.var(axis=1)
    residual_var = residual.var(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        residual_ratio = np.where(actual_var > 0, residual_var / actual_var, np.nan)
    residual_series = pd.Series(residual_ratio, index=sub.index, name="residual_ratio")

    return pc_df, residual_series


class Layer3Result:
    def __init__(self, pc_scores, residual_ratio, pc_scores_sector, residual_ratio_sector, axes_meta):
        self.pc_scores = pc_scores
        self.residual_ratio = residual_ratio
        self.pc_scores_sector = pc_scores_sector
        self.residual_ratio_sector = residual_ratio_sector
        self.axes_meta = axes_meta


def run_layer3(ctx: MarketContext, returns: pd.DataFrame) -> Layer3Result:
    # 「銘柄レベル」はセクター/スタイルETFや指数を混ぜず、構成銘柄のみを対象にする
    member_cols = [t for t in ctx.universe_df["symbol"] if t in returns.columns]
    stock_returns = returns[member_cols]
    stock_axes = ensure_axes(ctx, "stocks", stock_returns)
    pc_scores, residual_ratio = project(stock_returns, stock_axes)

    # セクターレベルは自前集計ではなく実際のセクターETF価格から計算する
    # （個別銘柄データ取得が障害を起こした場合のフォールバックとして機能させるため、
    # 個別銘柄データ由来の集計値を使ってしまうと障害時に共倒れしてしまう）
    from decompose import sector_etf_returns

    etf_returns = sector_etf_returns(returns, ctx.sector_etfs)
    sector_axes = ensure_axes(ctx, "sectors", etf_returns)
    pc_scores_sector, residual_ratio_sector = project(etf_returns, sector_axes)

    return Layer3Result(
        pc_scores,
        residual_ratio,
        pc_scores_sector,
        residual_ratio_sector,
        {
            "stocks": {"estimated_at": stock_axes["estimated_at"], "method": stock_axes["method"],
                       "explained_variance_ratio": stock_axes["explained_variance_ratio"], "n_tickers": len(stock_axes["tickers"])},
            "sectors": {"estimated_at": sector_axes["estimated_at"], "method": sector_axes["method"],
                        "explained_variance_ratio": sector_axes["explained_variance_ratio"], "n_tickers": len(sector_axes["tickers"])},
        },
    )


if __name__ == "__main__":
    import sys

    import console_utf8  # noqa: F401
    from decompose import compute_returns
    from market_context import jp_context, us_context

    ctx = jp_context() if "--jp" in sys.argv else us_context()
    returns = compute_returns(ctx.price_store)

    result = run_layer3(ctx, returns)
    print(f"=== 層3 PCA（{ctx.label}） ===")
    print(f"銘柄レベル軸: 推定日={result.axes_meta['stocks']['estimated_at']}  "
          f"寄与率={[f'{v:.1%}' for v in result.axes_meta['stocks']['explained_variance_ratio']]}")
    print(result.pc_scores.tail(5))
    print("\n残差比率(直近5日):")
    print(result.residual_ratio.tail(5))
