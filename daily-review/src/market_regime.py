"""市場のレジーム（地合い）判定。層3(PCA)を補完する、ルールベースで直感的な指標。

PCAは「値動きを統計的パターンに分解する」手法で、結果を読むには主成分・
ローディングという抽象を経由する必要がある。レジーム判定はその対極として、
トレンド・ボラティリティ・相関という3つのなじみやすい軸だけで「今の相場が
どんな性質か」を一言でラベル付けする（ユーザーが提案した「その他の良い
分析方法」の一つ）。PCAのように軸を週次で保存・使い回す必要はなく、実行の
たびに直近データから計算し直す（計算コストが軽いため）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

VOL_WINDOW = 20
VOL_LOOKBACK = 252
VOL_MIN_HISTORY = 60
TREND_SHORT_MA = 50
TREND_LONG_MA = 200
CORR_WINDOW = 20
CORR_HIGH_THRESHOLD = 0.5
CORR_LOW_THRESHOLD = 0.25


def volatility_regime(index_returns: pd.Series) -> dict:
    """直近VOL_WINDOW日の実現ボラティリティ(年率換算)が、過去VOL_LOOKBACK日の
    中でどのくらいの水準か（パーセンタイル）を見て、低/平常/高ボラに分類する。
    """
    r = index_returns.dropna()
    realized = r.rolling(VOL_WINDOW).std() * np.sqrt(252)
    hist = realized.tail(VOL_LOOKBACK).dropna()
    if len(hist) < VOL_MIN_HISTORY:
        return {"tag": "判定不可", "desc": "データ不足のためボラティリティは判定できません。", "current": np.nan, "percentile": np.nan}

    current = float(hist.iloc[-1])
    percentile = float((hist < current).mean())
    if percentile >= 0.67:
        tag = "高ボラ"
        desc = (
            f"直近{VOL_WINDOW}日の実現ボラティリティは年率{current:.1%}で、過去1年の分布の"
            f"上位{100 - percentile * 100:.0f}%に位置する高水準です。値動きが普段より荒く、"
            f"同じニュースでも振れ幅が大きくなりやすい局面です。"
        )
    elif percentile <= 0.33:
        tag = "低ボラ"
        desc = (
            f"直近{VOL_WINDOW}日の実現ボラティリティは年率{current:.1%}で、過去1年の分布の"
            f"下位{percentile * 100:.0f}%に位置する落ち着いた水準です。相場が静かで、"
            f"方向感のある材料が出にくい局面です。"
        )
    else:
        tag = "平常ボラ"
        desc = f"直近{VOL_WINDOW}日の実現ボラティリティは年率{current:.1%}で、過去1年の平常的な範囲内です。"
    return {"tag": tag, "desc": desc, "current": current, "percentile": percentile}


def trend_regime(index_close: pd.Series) -> dict:
    """指数の終値が短期(50日)・長期(200日)移動平均に対しどちらの位置にあるかで、
    上昇/下降/もみ合いの3分類にする（ゴールデンクロス/デッドクロスと同じ考え方）。
    """
    c = index_close.dropna()
    if len(c) < TREND_LONG_MA + 5:
        return {"tag": "判定不可", "desc": "データ不足のためトレンドは判定できません。", "ma_short": np.nan, "ma_long": np.nan}

    ma_short = float(c.rolling(TREND_SHORT_MA).mean().iloc[-1])
    ma_long = float(c.rolling(TREND_LONG_MA).mean().iloc[-1])
    price = float(c.iloc[-1])
    if price > ma_short > ma_long:
        tag = "上昇トレンド"
        desc = f"終値が{TREND_SHORT_MA}日線・{TREND_LONG_MA}日線をともに上回る形で並んでおり、上昇トレンドが続いています。"
    elif price < ma_short < ma_long:
        tag = "下降トレンド"
        desc = f"終値が{TREND_SHORT_MA}日線・{TREND_LONG_MA}日線をともに下回る形で並んでおり、下降トレンドが続いています。"
    else:
        tag = "もみ合い"
        desc = (
            f"終値・{TREND_SHORT_MA}日線・{TREND_LONG_MA}日線の位置関係がねじれており、"
            f"明確な方向感のないもみ合い局面です。"
        )
    return {"tag": tag, "desc": desc, "price": price, "ma_short": ma_short, "ma_long": ma_long}


def correlation_regime(sector_returns: pd.DataFrame) -> dict:
    """セクター間の直近平均相関。高いほど「一斉に同じ方向へ動く」相場、
    低いほど「銘柄・セクターごとの色が出る」相場と読める（層4の構造ページで
    使っている考え方を、日次のレジーム判定にも簡略版として適用）。
    """
    sec = sector_returns.tail(CORR_WINDOW).dropna(axis=1, how="any")
    if sec.shape[1] < 3 or len(sec) < CORR_WINDOW:
        return {"tag": "判定不可", "desc": "データ不足のためセクター間相関は判定できません。", "avg_corr": np.nan}

    corr = sec.corr()
    mask = ~np.eye(len(corr), dtype=bool)
    avg_corr = float(corr.where(mask).stack().mean())
    if avg_corr >= CORR_HIGH_THRESHOLD:
        tag = "高相関"
        desc = (
            f"直近{CORR_WINDOW}日のセクター間平均相関は{avg_corr:.2f}と高く、個別材料よりも"
            f"マクロ要因で銘柄が一斉に同じ方向へ動きやすい相場です。"
        )
    elif avg_corr <= CORR_LOW_THRESHOLD:
        tag = "低相関"
        desc = (
            f"直近{CORR_WINDOW}日のセクター間平均相関は{avg_corr:.2f}と低く、銘柄・セクターごとの"
            f"個別材料で明暗が分かれやすい相場です。"
        )
    else:
        tag = "平常相関"
        desc = f"直近{CORR_WINDOW}日のセクター間平均相関は{avg_corr:.2f}と平常的な水準です。"
    return {"tag": tag, "desc": desc, "avg_corr": avg_corr}


def classify_regime(index_close: pd.Series, index_returns: pd.Series, sector_returns: pd.DataFrame) -> dict:
    """3つの軸をまとめて、レジームの短いラベル文と各軸の説明文を返す。"""
    trend = trend_regime(index_close)
    vol = volatility_regime(index_returns)
    corr = correlation_regime(sector_returns)
    headline = f"{trend['tag']}・{vol['tag']}・{corr['tag']}"
    return {"headline": headline, "trend": trend, "volatility": vol, "correlation": corr}


if __name__ == "__main__":
    import sys

    import console_utf8  # noqa: F401
    from decompose import cleaned_close, compute_returns, sector_etf_returns
    from market_context import jp_context, us_context

    ctx = jp_context() if "--jp" in sys.argv else us_context()
    close = cleaned_close(ctx.price_store)
    returns = compute_returns(ctx.price_store)
    sector_ret = sector_etf_returns(returns, ctx.sector_etfs)

    regime = classify_regime(close[ctx.index_ticker], returns[ctx.index_ticker], sector_ret)
    print(f"=== レジーム判定（{ctx.label}） ===")
    print(f"総合: {regime['headline']}")
    for key in ("trend", "volatility", "correlation"):
        print(f"  - {regime[key]['desc']}")
