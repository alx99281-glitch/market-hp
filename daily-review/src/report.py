"""日次レポート用データの取得（コンソール出力・HTML出力で共有する）。米国・日本共通。"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from config import ZSCORE_THRESHOLD, ZSCORE_WINDOW
from decompose import run_layer1, top_bottom_contributors
from market_context import MarketContext
from news_store import load_news_for_date
from pca import run_layer3
from zscore import run_layer2


def build_headline(index_ret: float, top_factor_name: str, top_factor_val: float) -> str:
    direction = "上昇" if index_ret > 0 else "下落" if index_ret < 0 else "横ばい"
    magnitude = "大幅" if abs(index_ret) >= 0.01 else "小幅"
    return (
        f"指数は{magnitude}{direction}（{index_ret:+.2%}）。"
        f"最も動いたのは{top_factor_name}ファクター（{top_factor_val:+.2%}）"
    )


def gather_report_data(ctx: MarketContext, target_date: pd.Timestamp | None = None) -> dict:
    """層1・層2・層3を実行し、レポート出力に必要な値をまとめて返す。"""
    l1 = run_layer1(ctx)
    l3 = run_layer3(ctx, l1.returns)
    l2 = run_layer2(ctx, l1, l3)

    idx_series = l1.index_ret.dropna()
    last_date = target_date or idx_series.index[-1]
    index_ret = l1.index_ret.loc[last_date]

    factor_today = l1.factor_ret.loc[last_date].dropna()
    if not factor_today.empty:
        top_factor_name = factor_today.abs().idxmax()
        top_factor_val = factor_today[top_factor_name]
    else:
        top_factor_name, top_factor_val = "N/A", 0.0

    talking_points = l2.talking_points(last_date)
    news_for_date = load_news_for_date(ctx.name, last_date)
    talking_points = talking_points.copy()
    talking_points["news"] = talking_points["metric"].apply(lambda m: news_for_date.get(m))

    return {
        "ctx": ctx,
        "date": last_date,
        "index_ret": index_ret,
        "headline": build_headline(index_ret, top_factor_name, top_factor_val),
        "talking_points": talking_points,
        "sector_contrib": l1.sector_contrib.loc[last_date].dropna().sort_values(ascending=False),
        "sector_etf_ret": l1.sector_etf_ret.loc[last_date].dropna().sort_values(ascending=False),
        "factor_ret": l1.factor_ret.loc[last_date],
        "factor_etf_ret": l1.factor_etf_ret.loc[last_date].dropna(),
        "top_bottom": top_bottom_contributors(l1.returns, last_date, ctx.universe_df, ctx.fundamentals_path),
        "pc_scores": l3.pc_scores.tail(60),
        "residual_ratio": l3.residual_ratio.tail(60),
        "pca_axes_meta": l3.axes_meta,
        "generated_at": datetime.now(timezone.utc),
        "zscore_window": ZSCORE_WINDOW,
        "zscore_threshold": ZSCORE_THRESHOLD,
    }


def print_daily_report(ctx: MarketContext, target_date: pd.Timestamp | None = None) -> None:
    d = gather_report_data(ctx, target_date)

    print("=" * 70)
    print(f" 日次市場サマリー（{ctx.label}） {d['date'].date()}")
    print("=" * 70)

    print("\n[結論]")
    print(" " + d["headline"])

    print(f"\n[本日の論点] |z| >= {d['zscore_threshold']}（ローリング{d['zscore_window']}日）")
    tp = d["talking_points"]
    if tp.empty:
        print("  該当なし")
    else:
        for _, row in tp.iterrows():
            print(f"  - {row['metric']:42s} 値={row['value']:+.4f}  z={row['zscore']:+.2f}")
            news = row.get("news")
            if news:
                print(f"      裏付けニュース: {news['summary']}")
                for src in news["sources"]:
                    print(f"        - {src['title']} ({src['url']})")
            else:
                print("      裏付けニュース: 要因不明")

    print("\n[補足: セクター寄与度ウォーターフォール（自前計算）]")
    for name, val in d["sector_contrib"].items():
        print(f"  {name:28s} {val:+.4%}")

    print("\n[補足: セクターETFベース簡易版（整合性チェック）]")
    for name, val in d["sector_etf_ret"].items():
        print(f"  {name:28s} {val:+.4%}")

    print("\n[補足: ファクター日次リターン]")
    print("  自前計算:")
    for name, val in d["factor_ret"].items():
        marker = " " if pd.isna(val) else f"{val:+.4%}"
        print(f"    {name:15s} {marker}")
    print("  ETFベース簡易版:")
    for name, val in d["factor_etf_ret"].items():
        print(f"    {name:15s} {val:+.4%}")

    print("\n[補足: 個別銘柄寄与 上位/下位10]")
    for _, row in d["top_bottom"].iterrows():
        print(f"  [{row['group']:6s}] {row['ticker']:6s} return={row['return']:+.3%}  contribution={row['contribution']:+.4%}")

    print("\n[補足: PCA射影（銘柄レベル、直近5日）]")
    meta = d["pca_axes_meta"]["stocks"]
    exp = ", ".join(f"PC{i+1}={v:.1%}" for i, v in enumerate(meta["explained_variance_ratio"]))
    print(f"  軸推定日: {meta['estimated_at']}  銘柄数: {meta['n_tickers']}  寄与率: {exp}")
    print(d["pc_scores"].tail(5).to_string())
    print("  残差比率(直近5日、PC1-5で説明できなかった当日分散の比率):")
    print("  " + d["residual_ratio"].tail(5).to_string().replace("\n", "\n  "))

    if ctx.name == "us":
        print("[補足: 日米連携指標] フェーズ6未実装")

    print("\n[フッター]")
    print(f"  データ出所: Yahoo Finance (yfinance) / セクターウェイト: {ctx.sector_weight_method}")
    print(f"  計算窓幅: zスコア={d['zscore_window']}日, セクター間相関=20日, Beta/Vol/Liquidity=60日, Momentum=252-21日")
    print(f"  レポート生成時刻: {d['generated_at'].isoformat()}")


if __name__ == "__main__":
    import sys

    import console_utf8  # noqa: F401
    from market_context import jp_context, us_context

    ctx = jp_context() if "--jp" in sys.argv else us_context()
    print_daily_report(ctx)
