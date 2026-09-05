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
h2 {
  font-size: 1rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border);
  padding-bottom: 6px;
  margin-bottom: 14px;
}
.tp-row { margin-bottom: 14px; }
.tp-label { display: flex; justify-content: space-between; font-size: 0.92rem; margin-bottom: 4px; }
.tp-name { color: var(--text); }
.tp-z { font-variant-numeric: tabular-nums; color: var(--muted); }
.bar-track { background: #21262c; border-radius: 3px; height: 8px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 3px; }
.pos { background: var(--pos); }
.neg { background: var(--neg); }
.news-placeholder { color: var(--muted); font-size: 0.85rem; margin-top: 4px; font-style: italic; }
.news-box { margin-top: 8px; padding: 10px 12px; background: #1c2128; border-radius: 4px; border-left: 3px solid var(--accent); }
.news-summary { font-size: 0.85rem; line-height: 1.6; }
.news-sources { margin: 6px 0 0; padding-left: 18px; font-size: 0.78rem; }
.news-sources a { color: var(--accent); }
.news-sources li { margin-bottom: 2px; }
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


def _fmt_pct(v: float, digits: int = 2) -> str:
    if pd.isna(v):
        return "N/A"
    return f"{v:+.{digits}%}"


def _render_news(news: dict | None) -> str:
    if not news:
        return "<div class='news-placeholder'>裏付けニュース: 要因不明</div>"
    sources = "".join(
        f"<li><a href='{html.escape(s['url'])}' target='_blank' rel='noopener'>{html.escape(s['title'])}</a></li>"
        for s in news["sources"]
    )
    return f"""<div class="news-box">
      <div class="news-summary">裏付けニュース: {html.escape(news['summary'])}</div>
      <ul class="news-sources">{sources}</ul>
    </div>"""


def _render_talking_points(tp: pd.DataFrame) -> str:
    if tp.empty:
        return "<p style='color:var(--muted)'>本日、しきい値を超える論点はありませんでした。</p>"
    max_abs_z = max(tp["zscore"].abs().max(), 1.5)
    rows = []
    for _, row in tp.iterrows():
        pct = min(100, abs(row["zscore"]) / max_abs_z * 100)
        cls = _cls(row["zscore"])
        name = html.escape(str(row["metric"]))
        rows.append(f"""
        <div class="tp-row">
          <div class="tp-label">
            <span class="tp-name">{name}</span>
            <span class="tp-z">値={row['value']:+.4f} &nbsp; z={row['zscore']:+.2f}</span>
          </div>
          <div class="bar-track"><div class="bar-fill {cls}" style="width:{pct:.1f}%"></div></div>
          {_render_news(row.get("news"))}
        </div>""")
    return "".join(rows)


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


def _sparkline_svg(series: pd.Series, color: str, w: int = 260, h: int = 60, fmt_last: str = "{:+.3f}") -> str:
    vals = series.dropna()
    if len(vals) < 2:
        return "<p style='color:var(--muted);font-size:0.8rem'>データ不足</p>"
    lo, hi = vals.min(), vals.max()
    span = (hi - lo) or 1.0
    pad = 4
    xs = np.linspace(pad, w - pad, len(vals))
    ys = [pad + (1 - (v - lo) / span) * (h - 2 * pad) for v in vals.values]
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    last_val = vals.iloc[-1]
    label_above = ys[-1] > h / 2  # 折れ線が下寄りなら上に、上寄りなら下にラベルを置いて重なりを避ける
    label_dy = -8 if label_above else 14
    return f"""
    <svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">
      <polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.6" />
      <circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="2.5" fill="{color}" />
      <text x="{xs[-1]:.1f}" y="{ys[-1]:.1f}" dy="{label_dy}" dx="-4" text-anchor="end" font-size="11" fill="{color}">{fmt_last.format(last_val)}</text>
    </svg>"""


def _render_pca_section(pc_scores: pd.DataFrame, residual_ratio: pd.Series, meta: dict, days: int) -> str:
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
    return f"""
    <p style="color:var(--muted);font-size:0.85rem">
      軸推定日: {meta['estimated_at'][:10]} / 対象銘柄数: {meta['n_tickers']} / 説明分散比率: {exp_txt}
    </p>
    <div style="display:flex; gap:24px; flex-wrap:wrap; margin-bottom:16px">{pc_charts}</div>
    <div style="font-size:0.78rem;color:var(--muted);margin-bottom:4px">残差比率（PC1〜PC5で説明できなかった当日分散の比率、直近{days}日）</div>
    {resid_chart}"""


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
    {_render_talking_points(d['talking_points'])}
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
    <h2>PCA射影（銘柄レベル、直近60日）</h2>
    {_render_pca_section(d['pc_scores'], d['residual_ratio'], d['pca_axes_meta']['stocks'], 60)}
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
