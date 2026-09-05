"""タブ3: 中央銀行審議委員まとめページの組み立て（v2）。

- タカ派/ハト派は横一本の軸(スペクトラム)上に全員をプロットしてまとめて比較できるようにする
  （個別カードごとのバーは廃止）。
- プロフィールカードは写真(公式サイトから直接埋め込み)+役職+スコアバッジ+短いプロフィールの
  コンパクトな形にする。
"""

from __future__ import annotations

import html
import json
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"

AVATAR_COLORS = ["#1f6feb", "#8957e5", "#db6d28", "#2ea043", "#cf222e", "#0969da", "#bf3989"]


def initials(name_en: str) -> str:
    parts = [p for p in name_en.replace(".", "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper()


def avatar_color(name_en: str) -> str:
    return AVATAR_COLORS[sum(ord(c) for c in name_en) % len(AVATAR_COLORS)]


def score_color(score: int) -> str:
    return "#f85149" if score > 0 else ("#58a6ff" if score < 0 else "#8b949e")


def score_label(score: int) -> str:
    return "タカ派" if score > 1 else ("ハト派" if score < -1 else "中立")


def spectrum_svg(members: list[dict], width: int = 980) -> str:
    """全員をタカ派/ハト派の一本軸上にプロットする。

    1人1行（スコア降順）で並べ、行ごとに縦位置をずらすことでラベルの重なりを
    確実に防ぐ（横位置のみでスコアを表現し、縦位置は単なる並び順）。
    """
    ordered = sorted(members, key=lambda m: (-m["score"], m["name_ja"]))
    row_h = 20
    top_pad = 16
    height = top_pad * 2 + len(ordered) * row_h

    left_pad, right_pad = 70, 70
    plot_w = width - left_pad - right_pad

    def x_for(score: int) -> float:
        return left_pad + (score + 5) / 10 * plot_w

    axis_y = top_pad - 8
    parts = [
        f'<line x1="{left_pad}" y1="{top_pad}" x2="{left_pad}" y2="{height - top_pad + row_h}" stroke="#21262c" stroke-width="1"/>',
    ]
    for s in range(-5, 6):
        x = x_for(s)
        tick_color = "#484f58" if s != 0 else "#8b949e"
        parts.append(f'<line x1="{x:.1f}" y1="{top_pad - 6}" x2="{x:.1f}" y2="{height - top_pad + row_h - 6}" stroke="{tick_color}" stroke-width="0.5" opacity="0.35"/>')

    parts.append(f'<text x="{left_pad}" y="{height - 4}" fill="#58a6ff" font-size="11">← ハト派（緩和的）</text>')
    parts.append(f'<text x="{width - right_pad}" y="{height - 4}" fill="#f85149" font-size="11" text-anchor="end">タカ派（引き締め的） →</text>')

    for i, m in enumerate(ordered):
        score = m["score"]
        x = x_for(score)
        y = top_pad + 6 + i * row_h
        color = score_color(score)
        anchor = "start" if x < width / 2 else "end"
        dx = 9 if anchor == "start" else -9
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}" stroke="#0d1117" stroke-width="1"/>')
        parts.append(
            f'<text x="{x + dx:.1f}" y="{y + 4:.1f}" fill="#e6edf3" font-size="11.5" '
            f'text-anchor="{anchor}">{html.escape(m["name_ja"])}</text>'
        )

    return f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" style="max-width:{width}px">{"".join(parts)}</svg>'


def member_card(m: dict) -> str:
    color = avatar_color(m["name_en"])
    ini = initials(m["name_en"])
    photo = m.get("photo_url")
    if photo:
        avatar_html = (
            f'<img class="avatar-img" src="{html.escape(photo)}" alt="{html.escape(m["name_ja"])}" '
            f'onerror="this.outerHTML=\'<div class=&quot;avatar&quot; style=&quot;background:{color}&quot;>{ini}</div>\'">'
        )
    else:
        avatar_html = f'<div class="avatar" style="background:{color}">{ini}</div>'

    sc = m["score"]
    return f"""
    <div class="card">
      {avatar_html}
      <div class="card-body">
        <div class="name">{html.escape(m['name_ja'])}</div>
        <div class="name-en">{html.escape(m['name_en'])}</div>
        <div class="role">{html.escape(m['role'])} <span class="since">{html.escape(m['since'])}</span></div>
        <span class="score-badge" style="color:{score_color(sc)};border-color:{score_color(sc)}">{score_label(sc)} ({sc:+d})</span>
        <div class="bio">{html.escape(m['bio'])}</div>
        <div class="rationale">{html.escape(m['rationale'])}</div>
        <a class="bio-link" href="{html.escape(m['bio_url'])}" target="_blank" rel="noopener">公式略歴 →</a>
      </div>
    </div>"""


def section(title: str, members: list[dict]) -> str:
    ordered = sorted(members, key=lambda m: -m["score"])
    cards = "".join(member_card(m) for m in ordered)
    return f"""
  <section>
    <h2>{html.escape(title)}</h2>
    <div class="spectrum-wrap">{spectrum_svg(members)}</div>
    <div class="grid">{cards}</div>
  </section>"""


def build_html() -> str:
    data = json.loads((DATA_DIR / "members.json").read_text(encoding="utf-8"))

    css = """
    :root { color-scheme: dark; --bg:#0d1117; --panel:#161b22; --border:#30363d; --text:#e6edf3; --muted:#8b949e; --accent:#58a6ff; }
    * { box-sizing: border-box; }
    body { background:var(--bg); color:var(--text); margin:0; padding:24px 16px 60px; font-family:-apple-system,"Segoe UI","Hiragino Sans","Yu Gothic",sans-serif; max-width:1100px; margin-left:auto; margin-right:auto; }
    h1 { font-size:1.4rem; margin-bottom:4px; }
    .subtitle { color:var(--muted); font-size:0.85rem; margin-top:0; margin-bottom:8px; }
    .methodology { background:var(--panel); border:1px solid var(--border); border-left:4px solid var(--accent); border-radius:6px; padding:12px 16px; font-size:0.82rem; color:var(--muted); margin-bottom:28px; line-height:1.6; }
    h2 { font-size:1.05rem; border-bottom:1px solid var(--border); padding-bottom:8px; margin-bottom:14px; margin-top:36px; }
    .spectrum-wrap { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:12px 16px 4px; margin-bottom:16px; overflow-x:auto; }
    .grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(230px,1fr)); gap:12px; }
    .card { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:12px; display:flex; gap:10px; }
    .avatar-img { width:48px; height:58px; object-fit:cover; border-radius:6px; flex-shrink:0; background:#21262c; }
    .avatar { width:48px; height:58px; border-radius:6px; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:0.85rem; color:#fff; flex-shrink:0; }
    .card-body { min-width:0; flex:1; }
    .name { font-size:0.88rem; font-weight:600; line-height:1.3; }
    .name-en { font-size:0.7rem; color:var(--muted); margin-bottom:2px; }
    .role { font-size:0.72rem; color:var(--muted); margin-bottom:5px; }
    .since { font-size:0.68rem; }
    .score-badge { display:inline-block; font-size:0.7rem; font-weight:600; padding:1px 8px; border:1px solid; border-radius:10px; margin-bottom:6px; }
    .bio { font-size:0.72rem; color:var(--text); opacity:0.85; line-height:1.45; margin-bottom:4px; }
    .rationale { font-size:0.68rem; color:var(--muted); line-height:1.45; margin-bottom:5px; }
    .bio-link { font-size:0.7rem; color:var(--accent); text-decoration:none; }
    footer { margin-top:32px; padding-top:14px; border-top:1px solid var(--border); color:var(--muted); font-size:0.78rem; }
    """

    body = section("FRB (FOMC投票メンバー)", data["frb"]) + section("日本銀行 政策委員会", data["boj"])

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>中央銀行審議委員まとめ</title>
<style>{css}</style>
</head>
<body>
  <h1>中央銀行審議委員まとめ</h1>
  <p class="subtitle">日銀・FRBの金融政策メンバー (更新: {html.escape(data['updated_at'])})</p>
  <div class="methodology">{html.escape(data['methodology'])}</div>
  {body}
  <footer>
    出所: 各氏の公式略歴ページ（Federal Reserve Board / Bank of Japan / 各地区連銀）、報道各社の報道内容を基に編集部が作成<br>
    写真は各氏の公式略歴ページから直接埋め込み。読み込めない場合はイニシャルのアバターで代替表示される
  </footer>
</body>
</html>
"""


def write_page() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "index.html"
    out_path.write_text(build_html(), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    path = write_page()
    print(f"審議委員まとめページを生成しました: {path}")
