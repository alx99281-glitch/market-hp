"""構造ページ（層4）の静的HTML生成。SPEC_1.mdの出力形式に準拠。

出力先: reports/structure/us/index.html, reports/structure/jp/index.html
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config import REPORTS_DIR
from html_report import CSS, _sparkline_svg
from market_context import MarketContext
from structure_monitor import (
    CORR_FLAG_THRESHOLD,
    STRUCTURE_ZSCORE_WINDOW,
    latest_week_over_week_narrative,
    monthly_summary,
    rolling_zscore_weekly,
    run_layer4,
)


def _explain(text: str) -> str:
    return f'<p class="explain">{text}</p>'


def _pc1_trend_headline(history: pd.DataFrame) -> str:
    if len(history) < 2:
        return "履歴が不足しているため判定できません。"
    z = rolling_zscore_weekly(history.set_index("week_ending")["pc1_explained"]).iloc[-1]
    cur = history["pc1_explained"].iloc[-1]
    if pd.isna(z):
        return f"PC1説明力は{cur:.1%}（zスコア算出に必要な履歴が不足）。"
    if z >= 1.0:
        interp = "上昇基調＝マクロ要因（金利・為替・指数全体の動き）が支配的な相場に傾いています。"
    elif z <= -1.0:
        interp = "低下基調＝個別銘柄要因（業績・材料）が支配的な相場に傾いています。"
    else:
        interp = "直近の平均的な水準の範囲内です。"
    return f"PC1説明力 {cur:.1%}（z={z:+.2f}）。{interp}"


def _pc_interpretation_html(history: pd.DataFrame) -> str:
    if history.empty:
        return "<p style='color:var(--muted)'>データなし</p>"
    row = history.iloc[-1]
    items = []
    for pc, label in [("pc1", "PC1（第1主成分）"), ("pc2", "PC2（第2主成分）"), ("pc3", "PC3（第3主成分）")]:
        items.append(
            f"<li><b>{label}</b>: 正方向＝{html.escape(row[f'{pc}_top_sectors'])} / "
            f"負方向＝{html.escape(row[f'{pc}_bottom_sectors'])}</li>"
        )
    return "<ul style='font-size:0.9rem; line-height:1.9'>" + "".join(items) + "</ul>"


def _flag_history_html(history: pd.DataFrame, weeks: int = 12) -> str:
    recent = history.tail(weeks)
    rows = "".join(
        f"<tr><td>{r['week_ending'].strftime('%Y-%m-%d')}</td>"
        f"<td class='num'>{r['pc1_short_long_corr']:.2f}</td>"
        f"<td class='num'>{r['pc2_short_long_corr']:.2f}</td>"
        f"<td>{'<span style=\"color:var(--neg)\">構造変化の疑い</span>' if r['structure_change_flag'] else '—'}</td></tr>"
        for _, r in recent.iterrows()
    )
    return f"""<table><thead><tr><th>週末</th><th class='num'>PC1相関(短期/長期)</th>
      <th class='num'>PC2相関(短期/長期)</th><th>フラグ</th></tr></thead><tbody>{rows}</tbody></table>"""


def _monthly_table_html(monthly: pd.DataFrame) -> str:
    if monthly.empty:
        return "<p style='color:var(--muted)'>データなし</p>"
    rows = "".join(
        f"<tr><td>{month}</td><td class='num'>{r.pc1_explained:.1%}</td>"
        f"<td class='num'>{r.pc1_short_long_corr:.2f}</td>"
        f"<td class='num'>{r.residual_ratio_week_avg:.1%}</td>"
        f"<td class='num'>{r.sector_corr_60d:.2f}</td>"
        f"<td>{'構造変化あり' if r.structure_change_flag_any else '—'}</td></tr>"
        for month, r in monthly.iterrows()
    )
    return f"""<table><thead><tr><th>月</th><th class='num'>PC1説明力(平均)</th>
      <th class='num'>PC1相関(平均)</th><th class='num'>残差比率(平均)</th>
      <th class='num'>セクター間相関60日(平均)</th><th>構造変化</th></tr></thead><tbody>{rows}</tbody></table>"""


def render_structure_html(ctx: MarketContext, history: pd.DataFrame) -> str:
    h = history.set_index("week_ending")
    weeks_display = 52
    pc1_chart = _sparkline_svg(h["pc1_explained"].tail(weeks_display), "#58a6ff", w=760, h=70, fmt_last="{:.1%}")
    corr_chart = _sparkline_svg(h["pc1_short_long_corr"].tail(weeks_display), "#3fb950", w=760, h=70, fmt_last="{:.2f}")
    resid_chart = _sparkline_svg(h["residual_ratio_week_avg"].tail(weeks_display), "#f85149", w=760, h=70, fmt_last="{:.1%}")
    seccorr_chart = _sparkline_svg(h["sector_corr_60d"].tail(weeks_display), "#f0883e", w=760, h=70, fmt_last="{:.2f}")

    narrative = latest_week_over_week_narrative(history)
    narrative_html = (
        "<ul>" + "".join(f"<li>{html.escape(n)}</li>" for n in narrative) + "</ul>"
        if narrative else "<p style='color:var(--muted)'>先週比での顕著な変化はありませんでした。</p>"
    )

    monthly = monthly_summary(history)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>構造ページ（{ctx.label}）</title>
<style>{CSS}</style>
</head>
<body>
  <h1>構造ページ（{ctx.label}）</h1>
  <p class="subtitle">週次更新 <span class="badge">{html.escape(ctx.index_display)}</span></p>

  <div class="headline">{html.escape(_pc1_trend_headline(history))}</div>

  <section>
    <h2>先週比の変化</h2>
    {narrative_html}
  </section>

  <section>
    <h2>現在の主成分の解釈</h2>
    {_pc_interpretation_html(history)}
  </section>

  <section>
    <h2>PC1説明力の推移（分散比率、直近{weeks_display}週）</h2>
    {_explain(
        "全銘柄の値動きのうち、最も大きな共通パターン(PC1)が説明できる割合。"
        "<b style='color:var(--neg)'>上昇＝相場が「ひとかたまり」で動いている状態</b>"
        "（金利・為替などマクロ要因が支配的）。"
        "<b style='color:var(--accent)'>低下＝銘柄ごとにバラバラに動く「銘柄選択相場」</b>"
        "（決算・個別材料が支配的）。"
    )}
    {pc1_chart}
  </section>

  <section>
    <h2>短期軸(60日) vs 長期軸(250日) のPC1ローディング相関（直近{weeks_display}週）</h2>
    {_explain(
        f"直近60日の値動きの「組み合わせ方」が、直近250日(約1年)の組み合わせ方とどれだけ"
        f"似ているか。<b style='color:var(--accent)'>相関が{CORR_FLAG_THRESHOLD}を下回ると"
        f"「構造変化の疑い」フラグが立つ</b>＝これまで一緒に動いていた銘柄グループが"
        f"入れ替わってきている、相場の「主役交代」のサイン。"
    )}
    {corr_chart}
  </section>

  <section>
    <h2>残差比率の週次平均の推移（直近{weeks_display}週）</h2>
    {_explain(
        "その週の値動きのうち、主要な共通パターン(PC1〜PC5)では説明できなかった部分の平均比率。"
        "<b style='color:var(--accent)'>上昇＝個別銘柄・個別材料主導の週</b>、"
        "<b style='color:var(--neg)'>低下＝過去のパターンに沿った、説明しやすい週</b>。"
    )}
    {resid_chart}
  </section>

  <section>
    <h2>セクター間平均相関60日の推移（直近{weeks_display}週）</h2>
    {_explain(
        "セクター同士の値動きが、平均してどれだけ連動しているか。"
        "<b style='color:var(--neg)'>上昇＝ほぼ全セクターが同じ方向に動く「ひとかたまり」相場</b>、"
        "<b style='color:var(--accent)'>低下＝セクターごとに明暗が分かれる相場</b>。"
        "PC1説明力とほぼ同じ動きをする、より直感的な指標。"
    )}
    {seccorr_chart}
  </section>

  <section>
    <h2>構造変化フラグ履歴（直近12週）</h2>
    {_flag_history_html(history)}
  </section>

  <section>
    <h2>月次サマリー</h2>
    {_monthly_table_html(monthly)}
  </section>

  <footer>
    <div>データ出所: Yahoo Finance (yfinance) / PCA: 自前計算（numpy固有値分解）</div>
    <div>短期軸=60日ローリング, 長期軸=250日ローリング, zスコア窓={STRUCTURE_ZSCORE_WINDOW}週</div>
    <div>レポート生成時刻(UTC): {generated_at}</div>
  </footer>
</body>
</html>
"""


def write_structure_page(ctx: MarketContext) -> Path:
    from decompose import compute_returns, sector_etf_returns

    returns = compute_returns(ctx.price_store)
    sector_returns = sector_etf_returns(returns, ctx.sector_etfs)
    history = run_layer4(ctx, returns, sector_returns)

    out_dir = REPORTS_DIR / "structure" / ctx.output_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(render_structure_html(ctx, history), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    import sys

    import console_utf8  # noqa: F401
    from market_context import jp_context, us_context

    ctx = jp_context() if "--jp" in sys.argv else us_context()
    path = write_structure_page(ctx)
    print(f"構造ページを生成しました: {path}")
