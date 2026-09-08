"""日次レポート用データの取得（コンソール出力・HTML出力で共有する）。米国・日本共通。"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from config import ZSCORE_THRESHOLD, ZSCORE_WINDOW
from decompose import run_layer1, top_bottom_contributors
from free_news_lookup import fetch_all, match_keywords
from market_context import MarketContext
from news_store import load_news_for_date, save_news
from pca import load_axes, run_layer3
from zscore import run_layer2


def _sector_name_from_metric(metric: str) -> str | None:
    if metric.startswith("sector:"):
        return metric.split(":", 1)[1]
    if metric.startswith("sector_internal_dispersion:"):
        return metric.split(":", 1)[1]
    return None


def related_movers(metric: str, returns: pd.DataFrame, date: pd.Timestamp, universe: pd.DataFrame, n: int = 3) -> list[dict]:
    """論点の「肉付け」用: その論点に関係する銘柄の、当日の実際の値動きを添える。

    現状はsector: / sector_internal_dispersion: 系の論点についてのみ、
    該当セクター内で当日リターンの絶対値が大きい銘柄を返す（factor:系や
    PCA系は、どの銘柄が「その日クインタイルに属していたか」が可変で
    示しにくいため今回は対象外）。
    """
    sector = _sector_name_from_metric(metric)
    if sector is None:
        return []
    sector_map = universe.set_index("symbol")["sector"]
    members = [t for t in sector_map[sector_map == sector].index if t in returns.columns]
    if not members:
        return []
    day_ret = returns.loc[date, members].dropna()
    if day_ret.empty:
        return []
    top = day_ret.reindex(day_ret.abs().sort_values(ascending=False).index).head(n)
    return [{"ticker": t, "return": float(r)} for t, r in top.items()]


def _company_name(universe: pd.DataFrame, ticker: str) -> str | None:
    row = universe[universe["symbol"] == ticker]
    if row.empty:
        return None
    for col in ("security", "name"):
        if col in row.columns:
            return str(row.iloc[0][col])
    return None


FACTOR_KEYWORDS = {
    "jp": {
        "Value": ["バリュー株", "割安株"], "Growth": ["グロース株", "成長株"],
        "Momentum": ["モメンタム"], "Quality": ["高配当", "優良株"],
        "Size": ["小型株", "大型株"], "Beta": ["ハイベータ"],
        "Volatility": ["低ボラティリティ"], "Liquidity": ["流動性"],
    },
    "us": {
        "Value": ["value stocks"], "Growth": ["growth stocks"],
        "Momentum": ["momentum stocks"], "Quality": ["quality stocks"],
        "Size": ["small-cap", "large-cap"], "Beta": ["high beta"],
        "Volatility": ["volatility"], "Liquidity": ["liquidity"],
    },
}

# セクター/ファクター固有のキーワードで見つからなかった場合の最後の網。
# 「セクター名では引っかからないマクロ要因（原油急騰・中東情勢等）」を拾うため。
MACRO_KEYWORDS = {
    "jp": ["日銀", "FRB", "利上げ", "利下げ", "円安", "円高", "原油", "中東", "関税", "米国株安", "米国株高"],
    "us": ["Fed", "Federal Reserve", "interest rate", "inflation", "jobs report", "oil", "tariff", "yields"],
}


def _keywords_for_metric(metric: str, movers: list[dict], universe: pd.DataFrame, market: str) -> list[str]:
    sector = _sector_name_from_metric(metric)
    if sector is not None:
        kws = [sector]
        for mv in movers:
            name = _company_name(universe, mv["ticker"])
            if name:
                kws.append(name)
        return kws
    if metric.startswith("factor:"):
        return FACTOR_KEYWORDS[market].get(metric.split(":", 1)[1], [])
    return []


def free_rss_lookup(talking_points: pd.DataFrame, ctx: MarketContext, date: pd.Timestamp) -> pd.DataFrame:
    """ニュースキャッシュに無い論点について、無料RSSの見出しとキーワード一致で
    照合し、見つかれば結果をnews_storeにも保存する。

    Anthropic APIキーが無い場合のフォールバック（free_news_lookup.py参照）。
    意味理解のない単純な文字列一致のため、要約文にはその旨を明記する。
    PCA由来の論点（pca:/pca_sector:）はローディングに基づくより確度の高い
    定性的説明が既にあるため対象外。まずセクター名/ファクター名/関連銘柄名で
    絞り込み、見つからなければマクロキーワード（日銀・FRB・原油・中東等）で
    もう一段広く探す（セクター名では拾えないマクロ要因主導の日を拾うため）。
    """
    missing = talking_points["news"].isna() & ~talking_points["metric"].str.startswith(("pca:", "pca_sector:"))
    if not missing.any():
        return talking_points

    feed_items = fetch_all(ctx.name)
    if not feed_items:
        return talking_points

    for idx in talking_points[missing].index:
        row = talking_points.loc[idx]
        specific_kws = _keywords_for_metric(row["metric"], row["movers"], ctx.universe_df, ctx.name)
        matched = match_keywords(feed_items, specific_kws) if specific_kws else []
        is_macro = False
        if not matched:
            matched = match_keywords(feed_items, MACRO_KEYWORDS[ctx.name])
            is_macro = bool(matched)
        if not matched:
            continue

        titles = "」「".join(m["title"] for m in matched)
        scope_note = "マクロ全般の材料として" if is_macro else ""
        summary = f"（自動キーワード一致・要確認）{scope_note}関連する可能性のある見出し: 「{titles}」"
        sources = [{"title": f"{m['source']}: {m['title']}", "url": m["url"]} for m in matched]
        talking_points.at[idx, "news"] = {"summary": summary, "sources": sources}
        save_news(ctx.name, date, row["metric"], summary, sources)

    return talking_points


def build_headline(
    index_ret: float, top_factor_name: str, top_factor_val: float,
    advancers: int | None = None, decliners: int | None = None,
) -> str:
    direction = "上昇" if index_ret > 0 else "下落" if index_ret < 0 else "横ばい"
    magnitude = "大幅" if abs(index_ret) >= 0.01 else "小幅"
    breadth_note = ""
    if advancers is not None and decliners is not None:
        total = advancers + decliners
        if total > 0:
            adv_pct = advancers / total
            if index_ret > 0 and adv_pct < 0.4:
                breadth_note = f"。値上がり{advancers}/値下がり{decliners}銘柄と、一部の銘柄が指数を押し上げた幅の狭い上昇"
            elif index_ret < 0 and adv_pct > 0.6:
                breadth_note = f"。値上がり{advancers}/値下がり{decliners}銘柄と、指数の下落ほど広範には売られていない"
            else:
                breadth_note = f"。値上がり{advancers}/値下がり{decliners}銘柄"
    return (
        f"指数は{magnitude}{direction}（{index_ret:+.2%}）。"
        f"最も動いたのは{top_factor_name}ファクター（{top_factor_val:+.2%}）{breadth_note}"
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

    breadth_today = l1.breadth.loc[last_date]
    advancers, decliners = int(breadth_today["advancers"]), int(breadth_today["decliners"])

    talking_points = l2.talking_points(last_date)
    news_for_date = load_news_for_date(ctx.name, last_date)
    talking_points = talking_points.copy()
    talking_points["news"] = talking_points["metric"].apply(lambda m: news_for_date.get(m))
    talking_points["movers"] = talking_points["metric"].apply(
        lambda m: related_movers(m, l1.returns, last_date, ctx.universe_df)
    )
    talking_points = free_rss_lookup(talking_points, ctx, last_date)

    return {
        "ctx": ctx,
        "date": last_date,
        "index_ret": index_ret,
        "headline": build_headline(index_ret, top_factor_name, top_factor_val, advancers, decliners),
        "talking_points": talking_points,
        "breadth": {"advancers": advancers, "decliners": decliners, "advance_pct": advancers / max(advancers + decliners, 1)},
        "sector_contrib": l1.sector_contrib.loc[last_date].dropna().sort_values(ascending=False),
        "sector_etf_ret": l1.sector_etf_ret.loc[last_date].dropna().sort_values(ascending=False),
        "factor_ret": l1.factor_ret.loc[last_date],
        "factor_etf_ret": l1.factor_etf_ret.loc[last_date].dropna(),
        "top_bottom": top_bottom_contributors(l1.returns, last_date, ctx.universe_df, ctx.fundamentals_path),
        "pc_scores": l3.pc_scores.tail(60),
        "residual_ratio": l3.residual_ratio.tail(60),
        "pca_axes_meta": l3.axes_meta,
        "pca_stock_axes": load_axes(ctx, "stocks"),
        "pca_sector_axes": load_axes(ctx, "sectors"),
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

    print(f"\n[本日の論点: 何がマーケットを主導したか] |z| >= {d['zscore_threshold']}（ローリング{d['zscore_window']}日）")
    tp = d["talking_points"]
    if tp.empty:
        print("  目立った論点はありませんでした。")
    else:
        from html_report import _fmt_metric_value, _pca_metric_story, humanize_metric

        seen_summaries: dict[str, str] = {}
        for _, row in tp.iterrows():
            news = row.get("news")
            metric_name = str(row["metric"])
            label = humanize_metric(metric_name)
            value_str = _fmt_metric_value(metric_name, row["value"])
            if news and news["summary"] in seen_summaries:
                print(f"  - 「{seen_summaries[news['summary']]}」と同じ背景とみられます（上記参照）")
                print(f"      ({label}: {value_str} / z={row['zscore']:+.2f})")
            elif news:
                print(f"  - {news['summary']}")
                print(f"      ({label}: {value_str} / z={row['zscore']:+.2f})")
                for src in news["sources"]:
                    print(f"      出典: {src['title']} ({src['url']})")
                seen_summaries[news["summary"]] = label
            else:
                pca_story = _pca_metric_story(metric_name, row["value"], d["pca_stock_axes"], d["pca_sector_axes"], ctx.universe_df)
                if pca_story:
                    print(f"  - {pca_story}")
                else:
                    print(f"  - {label}が普段より大きく動きましたが、対応する材料は特定できませんでした（要因不明）。")
                print(f"      ({label}: {value_str} / z={row['zscore']:+.2f})")
            movers = row.get("movers") or []
            if movers:
                movers_str = ", ".join(f"{m['ticker']} {m['return']:+.2%}" for m in movers)
                print(f"      関連銘柄: {movers_str}")

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

    print("\n[主成分分析(PCA)から分かること]")
    from html_report import _pca_narrative

    meta = d["pca_axes_meta"]["stocks"]
    print("  " + _pca_narrative(d["pc_scores"], d["residual_ratio"], meta, d["pca_stock_axes"], ctx.universe_df))
    exp = ", ".join(f"PC{i+1}={v:.1%}" for i, v in enumerate(meta["explained_variance_ratio"]))
    print(f"  （軸推定日: {meta['estimated_at'][:10]}  銘柄数: {meta['n_tickers']}  各パターンの説明力: {exp}）")
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
