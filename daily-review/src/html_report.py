"""静的HTMLレポート生成（SPEC_1.md フェーズ5）。

ダークテーマ、データ出所明記。追加の依存ライブラリ（jinja2等）は使わず、
素のPython文字列組み立てで生成する（「静的HTML生成」という要件自体が
シンプルさを求めているため）。

出力先: reports/us/YYYY-MM-DD.html （URL構造は仕様書に準拠）
"""

from __future__ import annotations

import html
from pathlib import Path

import numpy as np
import pandas as pd

from config import REPORTS_DIR
from report import gather_report_data

CSS = """
:root {
  color-scheme: dark;
  --bg: #0d1117;
  --panel: #161b22;
  --border: #30363d;
  --text: #e6edf3;
  --muted: #8b949e;
  --pos: #3fb950;
  --neg: #f85149;
  --accent: #58a6ff;
}
* { box-sizing: border-box; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, "Segoe UI", "Hiragino Sans", "Yu Gothic", sans-serif;
  max-width: 900px;
  margin: 0 auto;
  padding: 24px 16px 64px;
  line-height: 1.6;
}
h1 { font-size: 1.4rem; margin-bottom: 4px; }
.subtitle { color: var(--muted); margin-top: 0; margin-bottom: 24px; font-size: 0.9rem; }
.headline {
  background: var(--panel);
  border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  border-radius: 6px;
  padding: 16px 20px;
  font-size: 1.15rem;
  margin-bottom: 28px;
}
section { margin-bottom: 32px; }
.explain { color: var(--muted); font-size: 0.85rem; line-height: 1.7; margin: 0 0 12px; }
.explain b { font-weight: 600; }
h2 {
  font-size: 1rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border);
  padding-bottom: 6px;
  margin-bottom: 14px;
}
.pos { background: var(--pos); }
.neg { background: var(--neg); }
.tp-item { margin-bottom: 14px; }
.tp-box { background: #1c2128; border: 1px solid var(--border); border-radius: 6px; padding: 12px 14px; }
.tp-bullet { font-size: 0.95rem; line-height: 1.6; display: flex; gap: 8px; }
.tp-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-top: 6px; flex-shrink: 0; }
.tp-group-note { font-size: 0.72rem; color: var(--muted); margin: 8px 0 4px; padding-left: 17px; }
.tp-group-members { padding-left: 17px; display: flex; flex-direction: column; gap: 4px; }
.tp-group-member { font-size: 0.78rem; color: var(--text); }
.tp-group-member b { font-weight: 600; }
.tp-sources { margin: 6px 0 0; padding-left: 18px; font-size: 0.78rem; }
.tp-sources a { color: var(--accent); }
.tp-sources li { margin-bottom: 2px; }
.pca-box { background: #1c2128; border: 1px solid var(--border); border-radius: 6px; padding: 14px 16px; }
.pca-narrative { font-size: 0.92rem; line-height: 1.7; margin-bottom: 6px; }
table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--border); }
th { color: var(--muted); font-weight: 500; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
@media (max-width: 640px) { .two-col { grid-template-columns: 1fr; } }
.waterfall-row { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; font-size: 0.85rem; }
.waterfall-name { width: 180px; flex-shrink: 0; color: var(--muted); }
.waterfall-bar-wrap { flex: 1; display: flex; align-items: center; }
.waterfall-center { width: 1px; background: var(--border); align-self: stretch; }
.waterfall-bar { height: 14px; border-radius: 2px; }
.waterfall-val { width: 80px; text-align: right; font-variant-numeric: tabular-nums; flex-shrink: 0; }
.badge {
  display: inline-block; font-size: 0.72rem; padding: 1px 8px; border-radius: 10px;
  border: 1px solid var(--border); color: var(--muted); margin-left: 8px;
}
footer {
  margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--border);
  color: var(--muted); font-size: 0.78rem;
}
footer div { margin-bottom: 2px; }
"""


def _cls(v: float) -> str:
    return "pos" if v >= 0 else "neg"


def humanize_metric(name: str) -> str:
    """層2の技術的なメトリクス名を、レポートの読み手向けの平易な日本語に変換する。"""
    if ":" in name:
        prefix, label = name.split(":", 1)
    else:
        prefix, label = name, ""

    if prefix == "sector":
        return f"{label}セクターの値動き"
    if prefix == "factor":
        return f"{label}ファクターの値動き"
    if prefix == "sector_internal_dispersion":
        return f"{label}セクター内での銘柄ごとの値動きのばらつき"
    if prefix == "dispersion" and label == "cross_sectional":
        return "指数構成銘柄全体の値動きのばらつき"
    if prefix == "correlation" and label == "sector_avg":
        return "セクター間の値動きの連動性"
    if prefix == "breadth" and label == "advance_pct":
        return "値上がり銘柄比率（市場の厚み）"
    if prefix in ("pca", "pca_sector"):
        scope = "銘柄" if prefix == "pca" else "セクター"
        if label == "residual_ratio":
            return f"過去の値動きパターン（{scope}ベース）では説明できない動きの大きさ"
        return f"市場の値動きパターン（{scope}ベース、第{label.replace('PC','')}主成分）"
    return name


def _fmt_pct(v: float, digits: int = 2) -> str:
    if pd.isna(v):
        return "N/A"
    return f"{v:+.{digits}%}"


def _fmt_metric_value(metric: str, value: float) -> str:
    """メトリクスの生の値を、種類に応じて読みやすい形式にする。"""
    if metric.startswith("pca:") or metric.startswith("pca_sector:"):
        if metric.endswith("residual_ratio"):
            return f"{value:.0%}"
        return f"{value:+.3f}（主成分スコア）"
    if metric == "breadth:advance_pct":
        return f"{value:.0%}"
    return f"{value:+.2%}"


def _render_sources(news: dict | None) -> str:
    """ニュースの出典リンクだけを、説明ボックスの外側に描画する。"""
    if not news or not news.get("sources"):
        return ""
    links = "".join(
        f"<li><a href='{html.escape(s['url'])}' target='_blank' rel='noopener'>{html.escape(s['title'])}</a></li>"
        for s in news["sources"]
    )
    return f"<ul class='tp-sources'>{links}</ul>"


def _pca_metric_story(metric: str, value: float, stock_axes: dict | None, sector_axes: dict | None, universe: pd.DataFrame) -> str | None:
    """PCA由来の論点（pca:.. / pca_sector:..）を、ローディングに基づく定性的な結論に変換する。

    ニュースが見つからない場合でも「要因不明」で終わらせず、主成分分析という
    定量分析の結果から言える範囲のことは言い切る（どのセクターの組み合わせが
    動いたパターンかを、そのパターンのローディング自体から直接言語化する）。
    """
    if metric.startswith("pca:"):
        prefix, label, axes, scope = "pca", metric[4:], stock_axes, "銘柄"
    elif metric.startswith("pca_sector:"):
        prefix, label, axes, scope = "pca_sector", metric[len("pca_sector:"):], sector_axes, "セクター"
    else:
        return None
    if axes is None:
        return None

    if label == "residual_ratio":
        if value >= 0.7:
            return (
                f"過去の主要な値動きパターン（{scope}ベース）では説明できない動きが目立ちました"
                f"（説明できなかった比率: 約{value:.0%}）。個別{'銘柄' if prefix == 'pca' else 'セクター'}固有の"
                f"材料が主導した可能性が高く、指数全体で語れる共通の要因は見当たりません。"
            )
        return (
            f"過去の主要な値動きパターン（{scope}ベース）で比較的よく説明できる値動きでした"
            f"（説明できた比率: 約{1 - value:.0%}）。特定の銘柄・材料というより、市場全体に"
            f"共通する既知のパターンの延長で動いた一日と言えます。"
        )

    try:
        pc_index = int(label.replace("PC", "")) - 1
    except ValueError:
        return None
    from pca import item_loading_summary, sector_loading_summary

    top, bottom = sector_loading_summary(axes, universe, pc_index) if prefix == "pca" else item_loading_summary(axes, pc_index)
    if not top or not bottom:
        return None
    stronger, weaker = (top, bottom) if value > 0 else (bottom, top)
    return (
        f"市場の値動きパターン（{scope}ベース、第{pc_index + 1}主成分）が普段より大きく動きました。"
        f"このパターンは通常「{'・'.join(top)}」が一方に、「{'・'.join(bottom)}」が逆方向に動く形で現れ、"
        f"本日は「{'・'.join(stronger)}」が相対的に強く、「{'・'.join(weaker)}」が相対的に弱い値動きだったとみられます。"
    )


def _render_member_row(row: pd.Series, metric_label: str) -> str:
    metric_name = str(row["metric"])
    value_str = _fmt_metric_value(metric_name, row["value"])
    movers = row.get("movers") or []
    movers_str = "、".join(
        f"{m['name']}({m['ticker']}) {m['return']:+.2%}" if m.get("name") else f"{m['ticker']} {m['return']:+.2%}"
        for m in movers
    )
    movers_part = f" ／ 関連銘柄: {html.escape(movers_str)}" if movers_str else ""
    return (
        f"<div class='tp-group-member'><b>{metric_label}</b>: {value_str} "
        f"(zスコア {row['zscore']:+.2f}){movers_part}</div>"
    )


def _render_talking_points(tp: pd.DataFrame, stock_axes: dict | None = None, sector_axes: dict | None = None, universe: pd.DataFrame | None = None) -> str:
    """「何がマーケットを主導したか」を箇条書きで示す。

    説明ボックスの中身は優先順に: (1)ニュースが見つかった場合はその要約文、
    (2)PCA由来の論点はローディングから導ける定性的な結論、(3)それ以外は
    技術指標名を人間向けに言い換えた一文。出典リンクはボックスの外・下に
    分離する（説明文と出典を視覚的に分けるため）。

    複数の論点が同一のニュース要約に一致した場合（例: 複数セクターが同じ
    マクロ要因のキーワードにヒットした場合）は、同じ説明文を論点の数だけ
    繰り返さず、1つの共通見出し＋対象論点の一覧としてまとめる
    （「Xと同じ背景」という参照を連発すると何が起きているか却って分かりにくい
    ため、共通の背景を1回だけ説明する形にしている）。
    """
    if tp.empty:
        return "<p style='color:var(--muted)'>本日、しきい値を超える目立った論点はありませんでした。</p>"

    # summary文（Noneも含む＝要因不明/PCA由来はグループ化しない）でグルーピング
    groups: dict[str, list[int]] = {}
    for idx, row in tp.iterrows():
        news = row.get("news")
        key = news["summary"] if news else None
        if key is None:
            groups[f"__unique_{idx}"] = [idx]
        else:
            groups.setdefault(key, []).append(idx)

    html_blocks = []
    for key, idxs in groups.items():
        first_row = tp.loc[idxs[0]]
        news = first_row.get("news")
        cls = _cls(first_row["zscore"])
        metric_name = str(first_row["metric"])
        metric_label = html.escape(humanize_metric(metric_name))

        if news:
            main_text = html.escape(news["summary"])
        else:
            pca_story = _pca_metric_story(metric_name, first_row["value"], stock_axes, sector_axes, universe)
            main_text = (
                html.escape(pca_story) if pca_story else
                f"{metric_label}が普段より大きく動きましたが、対応する材料は特定できませんでした（要因不明）。"
            )

        if len(idxs) == 1:
            html_blocks.append(f"""
        <div class="tp-item">
          <div class="tp-box">
            <div class="tp-bullet"><span class="tp-dot {cls}"></span>{main_text}</div>
            {_render_member_row(first_row, metric_label)}
          </div>
          {_render_sources(news)}
        </div>""")
        else:
            member_rows = "".join(
                _render_member_row(tp.loc[i], html.escape(humanize_metric(str(tp.loc[i]["metric"]))))
                for i in idxs
            )
            html_blocks.append(f"""
        <div class="tp-item">
          <div class="tp-box">
            <div class="tp-bullet"><span class="tp-dot {cls}"></span>{main_text}</div>
            <div class="tp-group-note">以下{len(idxs)}件の論点が共通してこの背景に該当するとみられます:</div>
            <div class="tp-group-members">{member_rows}</div>
          </div>
          {_render_sources(news)}
        </div>""")
    return "".join(html_blocks)


def _render_waterfall(series: pd.Series, scale: float | None = None) -> str:
    if series.empty:
        return "<p style='color:var(--muted)'>データなし</p>"
    scale = scale or series.abs().max() or 1.0
    rows = []
    for name, val in series.items():
        pct = min(100, abs(val) / scale * 100) / 2  # 中央基準で左右50%まで
        cls = _cls(val)
        if val >= 0:
            bar_html = f'<div style="width:50%"></div><div class="waterfall-bar {cls}" style="width:{pct:.1f}%"></div>'
        else:
            bar_html = f'<div class="waterfall-bar {cls}" style="width:{pct:.1f}%; margin-left:{50-pct:.1f}%"></div><div style="width:50%"></div>'
        rows.append(f"""
        <div class="waterfall-row">
          <div class="waterfall-name">{html.escape(str(name))}</div>
          <div class="waterfall-bar-wrap">{bar_html}</div>
          <div class="waterfall-val">{val:+.3%}</div>
        </div>""")
    return "".join(rows)


def _render_factor_table(factor_ret: pd.Series, factor_etf_ret: pd.Series, factor_etf_map: dict[str, str]) -> str:
    # 自前計算ファクター名 -> ETFベース簡易版の表示名 の対応は ctx.factor_etf_map
    # （市場ごとにconfig.US_FACTOR_ETF_MAP / JP_FACTOR_ETF_MAPで定義）を使う。
    # 名前の部分一致による誤対応（例: SPYを「ベータファクターETF」と誤認）を防ぐため
    # 常に明示テーブル経由で引く。
    rows = []
    for name, val in factor_ret.items():
        etf_key = factor_etf_map.get(name)
        etf_val = factor_etf_ret.get(etf_key) if etf_key else None
        rows.append(
            f"<tr><td>{html.escape(name)}</td>"
            f"<td class='num'>{_fmt_pct(val, 3)}</td>"
            f"<td class='num'>{_fmt_pct(etf_val, 3) if etf_val is not None else '—'}</td></tr>"
        )
    return "".join(rows)


def _render_contributors_table(tb: pd.DataFrame) -> str:
    top = tb[tb["group"] == "top"]
    bottom = tb[tb["group"] == "bottom"]

    def rows(df):
        return "".join(
            f"<tr><td>{html.escape(r['ticker'])}</td>"
            f"<td class='num'>{r['return']:+.2%}</td>"
            f"<td class='num'>{r['contribution']:+.3%}</td></tr>"
            for _, r in df.iterrows()
        )

    return f"""
    <div class="two-col">
      <div>
        <h3 style="font-size:0.85rem;color:var(--pos);margin-bottom:6px;">寄与上位10</h3>
        <table><thead><tr><th>銘柄</th><th class='num'>リターン</th><th class='num'>寄与度</th></tr></thead>
        <tbody>{rows(top)}</tbody></table>
      </div>
      <div>
        <h3 style="font-size:0.85rem;color:var(--neg);margin-bottom:6px;">寄与下位10</h3>
        <table><thead><tr><th>銘柄</th><th class='num'>リターン</th><th class='num'>寄与度</th></tr></thead>
        <tbody>{rows(bottom)}</tbody></table>
      </div>
    </div>"""


def _sparkline_svg(
    series: pd.Series, color: str, w: int = 260, h: int = 60, fmt_last: str = "{:+.3f}",
    show_dates: bool = False, date_fmt: str = "%Y-%m-%d",
) -> str:
    vals = series.dropna()
    if len(vals) < 2:
        return "<p style='color:var(--muted);font-size:0.8rem'>データ不足</p>"
    lo, hi = vals.min(), vals.max()
    span = (hi - lo) or 1.0
    pad = 4
    axis_h = 18 if show_dates else 0
    plot_h = h - axis_h
    xs = np.linspace(pad, w - pad, len(vals))
    ys = [pad + (1 - (v - lo) / span) * (plot_h - 2 * pad) for v in vals.values]
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    last_val = vals.iloc[-1]
    label_above = ys[-1] > plot_h / 2  # 折れ線が下寄りなら上に、上寄りなら下にラベルを置いて重なりを避ける
    label_dy = -8 if label_above else 14

    date_labels = ""
    if show_dates:
        dates = vals.index
        n = len(dates)
        # 開始・中間・終了の3点だけラベルを出す（詰め込みすぎて読めなくなるのを防ぐ）
        idxs = sorted({0, n // 2, n - 1})
        anchors = ["start", "middle", "end"][: len(idxs)] if len(idxs) == 3 else (["start", "end"] if len(idxs) == 2 else ["middle"])
        for i, anchor in zip(idxs, anchors):
            date_labels += (
                f'<text x="{xs[i]:.1f}" y="{plot_h + 13}" font-size="10" fill="var(--muted)" '
                f'text-anchor="{anchor}">{dates[i].strftime(date_fmt)}</text>'
            )

    return f"""
    <svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">
      <polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.6" />
      <circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="2.5" fill="{color}" />
      <text x="{xs[-1]:.1f}" y="{ys[-1]:.1f}" dy="{label_dy}" dx="-4" text-anchor="end" font-size="11" fill="{color}">{fmt_last.format(last_val)}</text>
      {date_labels}
    </svg>"""


def _pca_narrative(pc_scores: pd.DataFrame, residual_ratio: pd.Series, meta: dict, axes: dict | None = None, universe: pd.DataFrame | None = None) -> str:
    """主成分分析(PCA)の結果、本日は何が言えるかを平易な文章にまとめる。

    axes・universeが渡された場合は、最も動いた主成分がどのセクターの
    組み合わせに対応するかを言語化し、単なる数値の説明で終わらせない
    （「第1主成分」だけでは意味が伝わらないため、構造ページと同じ考え方で
    セクターローディングに結びつける）。
    """
    exp = meta["explained_variance_ratio"]
    last_date = pc_scores.dropna(how="all").index[-1]
    today_pc = pc_scores.loc[last_date]
    today_resid = residual_ratio.loc[last_date] if last_date in residual_ratio.index else float("nan")

    n_show = min(3, len(today_pc))
    dominant_i = int(today_pc.iloc[:n_show].abs().values.argmax())
    dominant_pc_num = dominant_i + 1
    dominant_exp = exp[dominant_i]
    dominant_score = today_pc.iloc[dominant_i]

    sector_sentence = ""
    if axes is not None and universe is not None:
        from pca import sector_loading_summary

        top, bottom = sector_loading_summary(axes, universe, dominant_i)
        if top and bottom:
            if dominant_score > 0:
                stronger, weaker = top, bottom
            else:
                stronger, weaker = bottom, top
            sector_sentence = (
                f"この変動パターンは普段、「{'・'.join(top)}」が一方に、「{'・'.join(bottom)}」が"
                f"逆方向に動く形で現れます。本日はこのパターンが強く出ており、"
                f"「{'・'.join(stronger)}」が相対的に強く、「{'・'.join(weaker)}」が相対的に弱い"
                f"値動きだった可能性があります。"
            )

    if pd.isna(today_resid):
        resid_sentence = "残差比率のデータが不足しているため、説明力は評価できません。"
    elif today_resid >= 0.7:
        resid_sentence = (
            f"本日の値動きのうち約{today_resid:.0%}は、過去の主要な値動きパターン（第1〜第5主成分）"
            f"では説明できませんでした。個別銘柄・個別材料が主導した、市場全体としては説明しにくい一日と言えます。"
        )
    elif today_resid <= 0.4:
        resid_sentence = (
            f"本日の値動きの約{1 - today_resid:.0%}は、過去の主要な値動きパターンで説明できました。"
            f"これまでと似た構造で相場が動いた一日と言えます。"
        )
    else:
        resid_sentence = (
            f"本日の値動きの約{1 - today_resid:.0%}は過去の主要な値動きパターンで説明できましたが、"
            f"残り約{today_resid:.0%}は個別要因によるものでした。"
        )

    macro_sentence = ""
    try:
        from macro import CORR_WINDOW, correlation_with

        macro_corr = correlation_with(pc_scores.iloc[:, dominant_i].dropna())
        if macro_corr:
            strong = {k: v for k, v in macro_corr.items() if abs(v) >= 0.4}
            macro_names = {"USDJPY": "USDJPY", "US10Y": "米10年金利", "Oil": "原油"}
            if strong:
                parts = "、".join(f"{macro_names.get(k, k)}(相関{v:+.2f})" for k, v in strong.items())
                macro_sentence = f" 直近{CORR_WINDOW}日では{parts}と相関が見られ、マクロ要因との連動が比較的明確です。"
            else:
                best_k, best_v = max(macro_corr.items(), key=lambda kv: abs(kv[1]))
                macro_sentence = (
                    f" 直近{CORR_WINDOW}日でUSDJPY・米金利・原油いずれとも相関は弱く"
                    f"（最大でも{macro_names.get(best_k, best_k)}の{best_v:+.2f}）、この主成分を単一の"
                    f"マクロ変数だけで説明するのは早計と言えます。"
                )
    except Exception:  # noqa: BLE001
        pass

    return (
        f"直近で最も動いたのは第{dominant_pc_num}主成分（過去の値動き全体の分散のうち{dominant_exp:.0%}を説明する"
        f"変動パターン）でした。{sector_sentence}{resid_sentence}{macro_sentence}"
    )


def _render_pca_section(pc_scores: pd.DataFrame, residual_ratio: pd.Series, meta: dict, days: int, axes: dict | None = None, universe: pd.DataFrame | None = None) -> str:
    exp = meta["explained_variance_ratio"]
    exp_txt = " / ".join(f"PC{i+1} {v:.1%}" for i, v in enumerate(exp))
    colors = ["#58a6ff", "#3fb950", "#f0883e"]
    pc_charts = "".join(
        f"""<div>
          <div style="font-size:0.78rem;color:var(--muted);margin-bottom:4px">{col}</div>
          {_sparkline_svg(pc_scores[col].tail(days), colors[i % len(colors)])}
        </div>"""
        for i, col in enumerate(pc_scores.columns[:3])
    )
    resid_chart = _sparkline_svg(residual_ratio.tail(days), "#f85149", w=780, h=70, fmt_last="{:.0%}")
    narrative = html.escape(_pca_narrative(pc_scores, residual_ratio, meta, axes, universe))
    return f"""
    <div class="pca-box">
      <div class="pca-narrative">{narrative}</div>
      <p style="color:var(--muted);font-size:0.78rem">
        （主成分分析(PCA)＝多数の銘柄の値動きを少数の共通パターンに要約する統計手法。
        軸推定日: {meta['estimated_at'][:10]} / 対象銘柄数: {meta['n_tickers']} / 各パターンの説明力: {exp_txt}）
      </p>
      <div style="display:flex; gap:24px; flex-wrap:wrap; margin:14px 0 16px">{pc_charts}</div>
      <div style="font-size:0.78rem;color:var(--muted);margin-bottom:4px">説明できなかった動きの比率（直近{days}日の推移）</div>
      {resid_chart}
    </div>"""


def render_html(d: dict) -> str:
    ctx = d["ctx"]
    date_str = d["date"].strftime("%Y-%m-%d")
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>日次市場サマリー（{ctx.label}） {date_str}</title>
<style>{CSS}</style>
</head>
<body>
  <h1>日次市場サマリー（{ctx.label}）</h1>
  <p class="subtitle">{date_str} <span class="badge">{html.escape(ctx.index_display)}</span></p>

  <div class="headline">{html.escape(d['headline'])}</div>

  <section>
    <h2>本日の論点（|z| ≥ {d['zscore_threshold']}, ローリング{d['zscore_window']}日）</h2>
    {_render_talking_points(d['talking_points'], d['pca_stock_axes'], d['pca_sector_axes'], ctx.universe_df)}
  </section>

  <section>
    <h2>セクター寄与度（自前計算・{html.escape(ctx.sector_weight_method)}）</h2>
    {_render_waterfall(d['sector_contrib'])}
  </section>

  <section>
    <h2>セクターETFベース簡易版（整合性チェック）</h2>
    {_render_waterfall(d['sector_etf_ret'])}
  </section>

  <section>
    <h2>ファクター日次リターン</h2>
    <table>
      <thead><tr><th>ファクター</th><th class='num'>自前計算</th><th class='num'>ETFベース簡易版</th></tr></thead>
      <tbody>{_render_factor_table(d['factor_ret'], d['factor_etf_ret'], ctx.factor_etf_map)}</tbody>
    </table>
  </section>

  <section>
    <h2>個別銘柄寄与</h2>
    {_render_contributors_table(d['top_bottom'])}
  </section>

  <section>
    <h2>主成分分析(PCA)から分かること</h2>
    {_render_pca_section(d['pc_scores'], d['residual_ratio'], d['pca_axes_meta']['stocks'], 60, d['pca_stock_axes'], ctx.universe_df)}
  </section>

  {"" if ctx.name != "us" else '''<section>
    <h2>日米連携指標</h2>
    <p style="color:var(--muted)">フェーズ6未実装</p>
  </section>'''}

  <footer>
    <div>データ出所: Yahoo Finance (yfinance) / セクターウェイト: {html.escape(ctx.sector_weight_method)}</div>
    <div>計算窓幅: zスコア={d['zscore_window']}日 / セクター間相関=20日 / Beta・Volatility・Liquidity=60日 / Momentum=252-21日</div>
    <div>レポート生成時刻(UTC): {d['generated_at'].isoformat(timespec='seconds')}</div>
  </footer>
</body>
</html>
"""


def write_report(ctx, target_date: pd.Timestamp | None = None) -> Path:
    d = gather_report_data(ctx, target_date)
    out_dir = REPORTS_DIR / ctx.output_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = d["date"].strftime("%Y-%m-%d")
    out_path = out_dir / f"{date_str}.html"
    out_path.write_text(render_html(d), encoding="utf-8")

    latest_path = out_dir / "latest.html"
    latest_path.write_text(render_html(d), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    import sys

    import console_utf8  # noqa: F401
    from market_context import jp_context, us_context

    ctx = jp_context() if "--jp" in sys.argv else us_context()
    path = write_report(ctx)
    print(f"HTMLレポートを生成しました: {path}")
