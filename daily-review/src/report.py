"""日次レポート用データの取得（コンソール出力・HTML出力で共有する）。米国・日本共通。"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from config import ZSCORE_THRESHOLD, ZSCORE_WINDOW
from decompose import cleaned_close, run_layer1, sector_etf_returns, top_bottom_contributors
from free_news_lookup import fetch_all, match_keywords
from market_context import MarketContext
from market_regime import classify_regime
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
    return [{"ticker": t, "return": float(r), "name": _company_name(universe, t)} for t, r in top.items()]


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


def lookup_news_for_metric(
    metric: str,
    movers: list[dict],
    ctx: MarketContext,
    date: pd.Timestamp,
    feed_items: list[dict] | None = None,
    news_for_date: dict | None = None,
    allow_macro_fallback: bool = True,
) -> dict | None:
    """1つの論点(metric)について、ニュースキャッシュまたは無料RSSキーワード一致で
    関連ニュースを探す（見つかればnews_storeにも保存）。

    free_rss_lookup()のループ内処理を独立させたもの。z-score異常検知を通った
    論点だけでなく、セクター寄与度の上位/下位（explain_top_sectors）のように
    閾値を超えていない対象にも同じロジックでニュースを探せるようにするため。

    allow_macro_fallback=False にすると、セクター名・関連銘柄名で見つからない
    場合に「要因不明」のままにする（マクロキーワードで見つけない）。1日1件だけ
    表示する本日の論点(talking_points)ではマクロ全般の材料として妥当でも、
    上位/下位セクター全件（方向がバラバラな複数セクター）に同じマクロ見出しを
    機械的に貼り付けると、上昇セクターと下落セクター両方に同じ「原因」が
    表示される矛盾した見え方になるため、セクター別の背景説明では使わない。
    """
    cache = news_for_date if news_for_date is not None else load_news_for_date(ctx.name, date)
    cached = cache.get(metric)
    if cached:
        return cached

    if feed_items is None:
        feed_items = fetch_all(ctx.name)
    if not feed_items:
        return None

    specific_kws = _keywords_for_metric(metric, movers, ctx.universe_df, ctx.name)
    matched = match_keywords(feed_items, specific_kws) if specific_kws else []
    is_macro = False
    if not matched and allow_macro_fallback:
        matched = match_keywords(feed_items, MACRO_KEYWORDS[ctx.name])
        is_macro = bool(matched)
    if not matched:
        return None

    titles = "」「".join(m["title"] for m in matched)
    scope_note = "マクロ全般の材料として" if is_macro else ""
    summary = f"（自動キーワード一致・要確認）{scope_note}関連する可能性のある見出し: 「{titles}」"
    sources = [{"title": f"{m['source']}: {m['title']}", "url": m["url"]} for m in matched]
    save_news(ctx.name, date, metric, summary, sources)
    return {"summary": summary, "sources": sources}


def free_rss_lookup(
    talking_points: pd.DataFrame, ctx: MarketContext, date: pd.Timestamp, feed_items: list[dict] | None = None
) -> pd.DataFrame:
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

    if feed_items is None:
        feed_items = fetch_all(ctx.name)
    if not feed_items:
        return talking_points

    for idx in talking_points[missing].index:
        row = talking_points.loc[idx]
        news = lookup_news_for_metric(row["metric"], row["movers"], ctx, date, feed_items, news_for_date={})
        if news:
            talking_points.at[idx, "news"] = news

    return talking_points


def explain_top_sectors(
    sector_contrib: pd.Series,
    zscored: pd.DataFrame,
    returns: pd.DataFrame,
    date: pd.Timestamp,
    ctx: MarketContext,
    news_for_date: dict,
    feed_items: list[dict] | None = None,
    n: int = 5,
) -> list[dict]:
    """本日のセクター寄与度、上位n・下位n件について「なぜ動いたか」を
    定量（関連銘柄の値動き・z-score）と定性（ニュース）の両面で説明する。

    z-score異常検知の「本日の論点」は、そのセクター自身の過去の振れ幅に対して
    "普段より"動いたかどうかで抽出するため、今日いちばん大きく動いたセクターが
    必ずしも論点として拾われるとは限らない（元々値動きの大きいセクターだと
    z-scoreが低いまま大きく動くことがある）。そのため論点抽出とは別に、
    単純に「本日の寄与度が大きい順」で網羅的に説明を付ける。
    """
    top = sector_contrib.head(n)
    bottom = sector_contrib.tail(n).sort_values()
    out = []
    for name, val in pd.concat([top, bottom]).items():
        metric = f"sector:{name}"
        movers = related_movers(metric, returns, date, ctx.universe_df)
        z = zscored.loc[date, metric] if date in zscored.index and metric in zscored.columns else float("nan")
        news = lookup_news_for_metric(metric, movers, ctx, date, feed_items, news_for_date, allow_macro_fallback=False)
        out.append({
            "name": name,
            "contribution": float(val),
            "zscore": float(z) if pd.notna(z) else None,
            "movers": movers,
            "news": news,
        })
    return out


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


def macro_fact_lines(ctx: MarketContext, date: pd.Timestamp) -> list[str]:
    """本日のマクロ変数（USDJPY・米10年金利・原油）の実際の動きのうち、
    「主因」候補として言及に値するもの（一定以上動いた変数）だけを返す。
    動きが小さい日にまで機械的に並べると、かえって何が主因か分かりにくくなるため。
    """
    from macro import today_macro_moves

    moves = today_macro_moves(date)
    lines = []
    v = moves.get("USDJPY")
    if v is not None and pd.notna(v) and abs(v) >= 0.004:
        lines.append(f"USDJPY: {v:+.2%}")
    v = moves.get("US10Y")
    if v is not None and pd.notna(v) and abs(v) >= 0.03:
        lines.append(f"米10年金利: {v * 100:+.0f}bp")
    v = moves.get("Oil")
    if v is not None and pd.notna(v) and abs(v) >= 0.012:
        lines.append(f"原油(WTI): {v:+.2%}")
    return lines


def sector_fact_lines(sector_contrib: pd.Series, n: int = 2) -> tuple[list[str], list[str]]:
    top = sector_contrib.head(n)
    bottom = sector_contrib.tail(n).sort_values()
    up = [f"{name} {val:+.3%}" for name, val in top.items()]
    down = [f"{name} {val:+.3%}" for name, val in bottom.items()]
    return up, down


def stock_fact_lines(top_bottom: pd.DataFrame, n: int = 2) -> tuple[list[str], list[str]]:
    up_rows = top_bottom[top_bottom["group"] == "top"].head(n)
    down_rows = top_bottom[top_bottom["group"] == "bottom"].head(n)

    def _fmt(row):
        name = row.get("name")
        label = f"{name}({row['ticker']})" if name else row["ticker"]
        return f"{label} {row['return']:+.2%}"

    up = [_fmt(r) for _, r in up_rows.iterrows()]
    down = [_fmt(r) for _, r in down_rows.iterrows()]
    return up, down


def build_lead_narrative(d: dict, ctx: MarketContext) -> dict:
    """結論→主因→セクター→個別銘柄→解釈(確度付き)、という一つのまとまった
    見立てを既存の計算結果から組み立てる。

    「主因」「セクター」「個別銘柄」は事実（自前の定量データ）のみで構成し、
    ニュースの引用は無料RSSキーワード一致で見つかった場合にのみ本文中に含める
    （精度が限定的なため、見つからない日の方が多い前提。README参照）。
    「解釈」だけは複数の定量シグナル（PCAの残差比率・マクロ相関・ファクター相関・
    ニュース裏付け件数）をどれだけ確認できたかに応じて確度(高/中/低)を付ける。
    """
    from html_report import _pca_facts

    facts = _pca_facts(
        d["pc_scores"], d["residual_ratio"], d["pca_axes_meta"]["stocks"],
        d["pca_stock_axes"], ctx.universe_df, d["factor_ret_history"],
    )

    primary_factors = [f"{ctx.index_display}: {d['index_ret']:+.2%}"]
    factor_today = d["factor_ret"].dropna()
    if not factor_today.empty:
        top_f = factor_today.abs().idxmax()
        primary_factors.append(f"{top_f}ファクター: {factor_today[top_f]:+.2%}")
    primary_factors.extend(macro_fact_lines(ctx, d["date"]))
    if facts["stronger_sectors"] and facts["weaker_sectors"]:
        primary_factors.append(
            f"値動きの主パターン(PC{facts['dominant_pc_num']}, 説明力{facts['dominant_exp']:.0%}): "
            f"「{'・'.join(facts['stronger_sectors'])}」高 / 「{'・'.join(facts['weaker_sectors'])}」安"
        )

    sector_up, sector_down = sector_fact_lines(d["sector_contrib"])
    stock_up, stock_down = stock_fact_lines(d["top_bottom"])

    signals = 0
    resid = facts["today_resid"]
    if resid is not None and resid <= 0.5:
        signals += 1
        resid_note = f"値動きの約{1 - resid:.0%}は過去の主要パターンで説明でき"
    elif resid is not None:
        resid_note = f"値動きの約{resid:.0%}は個別要因によるもので"
    else:
        resid_note = "PCAの説明力データが不足しており"

    macro_strong = {k: v for k, v in facts["macro_corr"].items() if pd.notna(v) and abs(v) >= 0.4}
    macro_names = {"USDJPY": "USDJPY", "US10Y": "米10年金利", "Oil": "原油"}
    if macro_strong:
        signals += 1
        best_k = max(macro_strong, key=lambda k: abs(macro_strong[k]))
        macro_note = f"、{macro_names.get(best_k, best_k)}との相関({macro_strong[best_k]:+.2f})も見られマクロ要因と整合的"
    else:
        macro_note = "、主要マクロ変数との相関は弱く"

    factor_strong = {k: v for k, v in facts["factor_corr"].items() if pd.notna(v) and abs(v) >= 0.4}
    factor_note = ""
    if factor_strong:
        signals += 1
        best_k = max(factor_strong, key=lambda k: abs(factor_strong[k]))
        factor_note = f"、{best_k}ファクター的な動き（相関{factor_strong[best_k]:+.2f}）"

    news_hits = sum(1 for item in d["sector_explanations"] if item["news"])
    if news_hits >= 2:
        signals += 1

    confidence = "高" if signals >= 3 else "中" if signals >= 1 else "低"
    interpretation = (
        f"{d['regime']['headline']}の相場の中、{resid_note}{macro_note}{factor_note}という一日でした。"
        f"（PCA・マクロ相関・ファクター相関・ニュース裏付けのうち{signals}/4のシグナルが確認できています）"
    )

    return {
        "conclusion": d["headline"],
        "primary_factors": primary_factors,
        "sector_up": sector_up,
        "sector_down": sector_down,
        "stock_up": stock_up,
        "stock_down": stock_down,
        "interpretation": interpretation,
        "confidence": confidence,
    }


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
    feed_items = fetch_all(ctx.name)
    talking_points = free_rss_lookup(talking_points, ctx, last_date, feed_items)

    close = cleaned_close(ctx.price_store)
    regime_sector_ret = sector_etf_returns(l1.returns, ctx.sector_etfs)
    regime = classify_regime(close[ctx.index_ticker], l1.returns[ctx.index_ticker], regime_sector_ret)

    sector_contrib_today = l1.sector_contrib.loc[last_date].dropna().sort_values(ascending=False)
    sector_explanations = explain_top_sectors(
        sector_contrib_today, l2.zscored, l1.returns, last_date, ctx, news_for_date, feed_items
    )

    top_bottom = top_bottom_contributors(l1.returns, last_date, ctx.universe_df, ctx.fundamentals_path)
    top_bottom["name"] = top_bottom["ticker"].apply(lambda t: _company_name(ctx.universe_df, t))

    d = {
        "ctx": ctx,
        "date": last_date,
        "index_ret": index_ret,
        "headline": build_headline(index_ret, top_factor_name, top_factor_val, advancers, decliners),
        "regime": regime,
        "talking_points": talking_points,
        "breadth": {"advancers": advancers, "decliners": decliners, "advance_pct": advancers / max(advancers + decliners, 1)},
        "sector_contrib": sector_contrib_today,
        "sector_explanations": sector_explanations,
        "sector_etf_ret": l1.sector_etf_ret.loc[last_date].dropna().sort_values(ascending=False),
        "factor_ret": l1.factor_ret.loc[last_date],
        "factor_ret_history": l1.factor_ret.tail(120),
        "factor_etf_ret": l1.factor_etf_ret.loc[last_date].dropna(),
        "top_bottom": top_bottom,
        "pc_scores": l3.pc_scores.tail(60),
        "residual_ratio": l3.residual_ratio.tail(60),
        "pca_axes_meta": l3.axes_meta,
        "pca_stock_axes": load_axes(ctx, "stocks"),
        "pca_sector_axes": load_axes(ctx, "sectors"),
        "generated_at": datetime.now(timezone.utc),
        "zscore_window": ZSCORE_WINDOW,
        "zscore_threshold": ZSCORE_THRESHOLD,
    }
    d["narrative"] = build_lead_narrative(d, ctx)
    return d


def print_daily_report(ctx: MarketContext, target_date: pd.Timestamp | None = None) -> None:
    d = gather_report_data(ctx, target_date)

    print("=" * 70)
    print(f" 日次市場サマリー（{ctx.label}） {d['date'].date()}")
    print("=" * 70)

    print("\n[結論]")
    print(" " + d["headline"])

    n = d["narrative"]
    print("\n[主因（定量的事実）]")
    for f in n["primary_factors"]:
        print(f"  - {f}")
    print("\n[セクター（寄与度上位/下位）]")
    print(f"  上昇: {', '.join(n['sector_up'])}")
    print(f"  下落: {', '.join(n['sector_down'])}")
    print("\n[個別銘柄（寄与上位/下位）]")
    print(f"  上昇: {', '.join(n['stock_up'])}")
    print(f"  下落: {', '.join(n['stock_down'])}")
    print(f"\n[解釈（確度: {n['confidence']}）]")
    print("  " + n["interpretation"])

    print(f"\n[相場のレジーム（地合い）] 総合: {d['regime']['headline']}")
    for key in ("trend", "volatility", "correlation"):
        print("  - " + d["regime"][key]["desc"])

    print(f"\n[本日の論点: 何がマーケットを主導したか] |z| >= {d['zscore_threshold']}（ローリング{d['zscore_window']}日）")
    tp = d["talking_points"]
    if tp.empty:
        print("  目立った論点はありませんでした。")
    else:
        from html_report import _fmt_metric_value, _pca_metric_story, humanize_metric

        def _print_member(row, label):
            metric_name = str(row["metric"])
            value_str = _fmt_metric_value(metric_name, row["value"])
            print(f"      {label}: {value_str} (z={row['zscore']:+.2f})")
            movers = row.get("movers") or []
            if movers:
                movers_str = ", ".join(
                    f"{m['name']}({m['ticker']}) {m['return']:+.2%}" if m.get("name") else f"{m['ticker']} {m['return']:+.2%}"
                    for m in movers
                )
                print(f"        関連銘柄: {movers_str}")

        # 同じニュース要約に一致した論点はグルーピングし、共通の背景を1回だけ表示する
        groups: dict[str, list] = {}
        order: list[str] = []
        for idx, row in tp.iterrows():
            news = row.get("news")
            key = news["summary"] if news else f"__unique_{idx}"
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(idx)

        for key in order:
            idxs = groups[key]
            first_row = tp.loc[idxs[0]]
            news = first_row.get("news")
            metric_name = str(first_row["metric"])
            label = humanize_metric(metric_name)
            if news:
                print(f"  - {news['summary']}")
                for src in news["sources"]:
                    print(f"      出典: {src['title']} ({src['url']})")
            else:
                pca_story = _pca_metric_story(metric_name, first_row["value"], d["pca_stock_axes"], d["pca_sector_axes"], ctx.universe_df)
                print(f"  - {pca_story if pca_story else label + 'が普段より大きく動きましたが、対応する材料は特定できませんでした（要因不明）。'}")

            if len(idxs) > 1:
                print(f"      （以下{len(idxs)}件の論点が共通してこの背景に該当するとみられます）")
            for i in idxs:
                row = tp.loc[i]
                _print_member(row, humanize_metric(str(row["metric"])))

    print("\n[補足: セクター寄与度ウォーターフォール（自前計算）]")
    for name, val in d["sector_contrib"].items():
        print(f"  {name:28s} {val:+.4%}")

    print(f"\n[本日動いたセクターの背景: 上位/下位{len(d['sector_explanations']) // 2}]")
    for item in d["sector_explanations"]:
        z_str = f", z={item['zscore']:+.2f}" if item["zscore"] is not None else ""
        print(f"  - {item['name']}: {item['contribution']:+.4%}{z_str}")
        if item["movers"]:
            movers_str = ", ".join(
                f"{m['name']}({m['ticker']}) {m['return']:+.2%}" if m.get("name") else f"{m['ticker']} {m['return']:+.2%}"
                for m in item["movers"]
            )
            print(f"      関連銘柄: {movers_str}")
        if item["news"]:
            print(f"      {item['news']['summary']}")
            for src in item["news"]["sources"]:
                print(f"        出典: {src['title']} ({src['url']})")
        else:
            print("      対応する材料は特定できませんでした（要因不明）。")

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
    print("  " + _pca_narrative(d["pc_scores"], d["residual_ratio"], meta, d["pca_stock_axes"], ctx.universe_df, d["factor_ret_history"]))
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
