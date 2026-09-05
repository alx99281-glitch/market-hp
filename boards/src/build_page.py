"""タブ3: 中央銀行審議委員まとめページの組み立て。

プロフィール（写真は本人イニシャルのアバターで代替、公式略歴ページへリンク）+
タカ派/ハト派スコア順の並び替え表示。
"""

from __future__ import annotations

import html
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"

AVATAR_COLORS = ["#1f6feb", "#8957e5", "#db6d28", "#2ea043", "#cf222e", "#0969da", "#bf3989"]


def initials(name_en: str) -> str:
    parts = [p for p in name_en.replace(".", "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper()


def avatar_color(name_en: str) -> str:
    return AVATAR_COLORS[sum(ord(c) for c in name_en) % len(AVATAR_COLORS)]


def score_bar(score: int) -> str:
    # -5..+5 を 0..100% にマップ。負(ハト派)は青、正(タカ派)は赤。
    pct = (score + 5) / 10 * 100
    color = "#f85149" if score > 0 else ("#58a6ff" if score < 0 else "#8b949e")
    label = "タカ派" if score > 1 else ("ハト派" if score < -1 else "中立")
    return f"""
    <div class="score-row">
      <div class="score-track">
        <div class="score-mid"></div>
        <div class="score-fill" style="left:{min(pct,50):.0f}%; width:{abs(pct-50):.0f}%; background:{color}"></div>
      </div>
      <div class="score-label" style="color:{color}">{label} ({score:+d})</div>
    </div>"""


def member_card(m: dict) -> str:
    ini = initials(m["name_en"])
    color = avatar_color(m["name_en"])
    return f"""
    <div class="card">
      <div class="card-head">
        <div class="avatar" style="background:{color}">{ini}</div>
        <div>
          <div class="name">{html.escape(m['name_ja'])} <span class="name-en">{html.escape(m['name_en'])}</span></div>
          <div class="role">{html.escape(m['role'])} <span class="since">({html.escape(m['since'])})</span></div>
        </div>
      </div>
      <div class="bio">{html.escape(m['bio'])}</div>
      {score_bar(m['score'])}
      <div class="rationale">{html.escape(m['rationale'])}</div>
      <a class="bio-link" href="{html.escape(m['bio_url'])}" target="_blank" rel="noopener">公式略歴 →</a>
    </div>"""


def section(title: str, members: list[dict]) -> str:
    ordered = sorted(members, key=lambda m: -m["score"])
    cards = "".join(member_card(m) for m in ordered)
    return f"""
  <section>
    <h2>{html.escape(title)}（タカ派→ハト派順）</h2>
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
    h2 { font-size:1.05rem; border-bottom:1px solid var(--border); padding-bottom:8px; margin-bottom:16px; margin-top:36px; }
    .grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(300px,1fr)); gap:14px; }
    .card { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:14px 16px; display:flex; flex-direction:column; }
    .card-head { display:flex; align-items:center; gap:12px; margin-bottom:10px; }
    .avatar { width:44px; height:44px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:0.9rem; color:#fff; flex-shrink:0; }
    .name { font-size:0.98rem; font-weight:600; }
    .name-en { font-weight:400; color:var(--muted); font-size:0.82rem; }
    .role { font-size:0.8rem; color:var(--muted); margin-top:2px; }
    .since { font-size:0.75rem; }
    .bio { font-size:0.82rem; color:var(--text); opacity:0.9; margin-bottom:10px; line-height:1.5; }
    .score-row { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
    .score-track { position:relative; flex:1; height:8px; background:#21262c; border-radius:4px; }
    .score-mid { position:absolute; left:50%; top:-2px; bottom:-2px; width:1px; background:var(--border); }
    .score-fill { position:absolute; top:0; bottom:0; border-radius:4px; }
    .score-label { font-size:0.78rem; font-weight:600; white-space:nowrap; width:96px; text-align:right; }
    .rationale { font-size:0.78rem; color:var(--muted); line-height:1.5; margin-bottom:8px; flex:1; }
    .bio-link { font-size:0.78rem; color:var(--accent); text-decoration:none; }
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
  <p class="subtitle">日銀・FRBの金融政策メンバー — タカ派/ハト派スコア順 (更新: {html.escape(data['updated_at'])})</p>
  <div class="methodology">{html.escape(data['methodology'])}</div>
  {body}
  <footer>
    出所: 各氏の公式略歴ページ（Federal Reserve Board / Bank of Japan）、報道各社の報道内容を基に編集部が作成<br>
    写真は本人イニシャルのアバターで代替。実際の顔写真は各氏の公式略歴ページ（カードの「公式略歴」リンク）で確認できる
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
