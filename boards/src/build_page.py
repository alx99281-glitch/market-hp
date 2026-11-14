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
HISTORY_PATH = DATA_DIR / "score_history.json"
STATEMENTS_PATH = DATA_DIR / "statements.json"
STANCE = {"hawk": ("タカ派的", "hawk"), "dove": ("ハト派的", "dove"), "neutral": ("中立", "neu"), "none": ("政策言及なし", "neu")}

BOARDS = {"frb": "FRB (FOMC投票メンバー)", "boj": "日本銀行 政策委員会"}

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


def position(score: int) -> str:
    return f"{score_label(score)} ({score:+d})"


def sync_history(data: dict) -> dict | None:
    """今回のスコアを履歴に記録し、前回分（今回より前の直近の記録）を返す。"""
    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else []
    entry = {"date": data["updated_at"]}
    for board in BOARDS:
        entry[board] = {m["name_en"]: m["score"] for m in data[board]}
    past = [h for h in history if h["date"] < entry["date"]]
    later = [h for h in history if h["date"] > entry["date"]]
    HISTORY_PATH.write_text(
        json.dumps(past + [entry] + later, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return past[-1] if past else None


def attach_previous(members: list[dict], prev: dict | None) -> None:
    for m in members:
        m["prev_score"] = prev.get(m["name_en"]) if prev else None


def changes_panel(members: list[dict], prev: dict | None, prev_date: str | None) -> str:
    """前回からスコアが動いた委員、新任、退任を表にする。"""
    if prev is None:
        return '<div class="changes"><p>前回比は次回の更新から表示します。</p></div>'
    current = {m["name_en"] for m in members}
    rows = []
    for m in sorted(members, key=lambda m: -m["score"]):
        before = m["prev_score"]
        note = html.escape(m.get("change_note", ""))
        if before is None:
            rows.append(f'<tr><td>{html.escape(m["name_ja"])}</td><td>新任 → {position(m["score"])}</td><td>{note}</td></tr>')
        elif before != m["score"]:
            cls = "hawk" if m["score"] > before else "dove"
            word = "タカ派寄り" if m["score"] > before else "ハト派寄り"
            rows.append(
                f'<tr><td>{html.escape(m["name_ja"])}</td>'
                f'<td class="{cls}">{position(before)} → {position(m["score"])} ・ {word}</td><td>{note}</td></tr>'
            )
    for name, before in prev.items():
        if name not in current:
            rows.append(f"<tr><td>{html.escape(name)}</td><td>{position(before)} → 退任</td><td></td></tr>")
    if not rows:
        return f'<div class="changes"><p>前回({html.escape(prev_date)})からの変更はありません。</p></div>'
    return (
        f'<div class="changes"><p>前回({html.escape(prev_date)})からの変更</p><div class="scroll"><table>'
        f'<thead><tr><th>氏名</th><th>立ち位置</th><th>理由</th></tr></thead><tbody>{"".join(rows)}</tbody>'
        "</table></div></div>"
    )


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
        before = m.get("prev_score")
        if before is not None and before != score:
            px = x_for(before)
            parts.append(f'<line x1="{px:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="{color}" stroke-width="1.5" stroke-dasharray="3 3"/>')
            parts.append(f'<circle cx="{px:.1f}" cy="{y:.1f}" r="4" fill="#0d1117" stroke="{color}" stroke-width="1.5"/>')
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}" stroke="#0d1117" stroke-width="1"/>')
        parts.append(
            f'<text x="{x + dx:.1f}" y="{y + 4:.1f}" fill="#e6edf3" font-size="11.5" '
            f'text-anchor="{anchor}">{html.escape(m["name_ja"])}</text>'
        )

    return f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" style="max-width:{width}px">{"".join(parts)}</svg>'


def member_card(m: dict, n_statements: int = 0, board: str = "") -> str:
    color = avatar_color(m["name_en"])
    ini = initials(m["name_en"])
    photo = m.get("photo") or m.get("photo_url")
    if photo:
        avatar_html = (
            f'<img class="avatar-img" src="{html.escape(photo)}" alt="{html.escape(m["name_ja"])}" '
            f'onerror="this.outerHTML=\'<div class=&quot;avatar&quot; style=&quot;background:{color}&quot;>{ini}</div>\'">'
        )
    else:
        avatar_html = f'<div class="avatar" style="background:{color}">{ini}</div>'

    sc = m["score"]
    before = m.get("prev_score")
    shift = ""
    if before is not None and before != sc:
        shift = f'<div class="shift {"hawk" if sc > before else "dove"}">前回 {position(before)} → 今回 {position(sc)}</div>'
    return f"""
    <div class="card">
      {avatar_html}
      <div class="card-body">
        <div class="name">{html.escape(m['name_ja'])}</div>
        <div class="name-en">{html.escape(m['name_en'])}</div>
        <div class="role">{html.escape(m['role'])} <span class="since">{html.escape(m['since'])}</span></div>
        <div class="term">任期: {html.escape(m.get('term', '未確認'))}</div>
        <span class="score-badge" style="color:{score_color(sc)};border-color:{score_color(sc)}">{score_label(sc)} ({sc:+d})</span>
        {shift}
        <div class="bio">{html.escape(m['bio'])}</div>
        <div class="rationale">{html.escape(m['rationale'])}</div>
        <div class="links"><a class="bio-link" href="{html.escape(m['bio_url'])}" target="_blank" rel="noopener">公式略歴 →</a>
        <a class="bio-link" href="#talk-{board}" data-bank="{board}" data-member="{html.escape(m['name_en'])}" onclick="pick(this)">発言 {n_statements}件 →</a></div>
      </div>
    </div>"""


def timeline(board: str, members: list[dict], items: list[dict]) -> str:
    """その中銀の発言を新しい順に並べ、委員ごとに絞り込めるようにする。"""
    by_name = {m["name_en"]: m for m in members}
    rows = []
    for it in sorted(items, key=lambda x: x["date"], reverse=True):
        m = by_name.get(it["member"])
        name = m["name_ja"] if m else it["member"]
        label, cls = STANCE.get(it.get("stance", "none"), STANCE["none"])
        src = it.get("source") or {}
        link = (f'<a href="{html.escape(src["url"])}" target="_blank" rel="noopener">{html.escape(src.get("label", "出所"))}</a>'
                if src.get("url") else "")
        rows.append(
            f'<li data-member="{html.escape(it["member"])}"><div class="t-date">{html.escape(it["date"])}</div>'
            f'<div class="t-body"><div class="t-head"><b>{html.escape(name)}</b><span class="t-type">{html.escape(it.get("type", ""))}</span>'
            f'<span class="t-stance {cls}">{label}</span></div><p>{html.escape(it["summary"])}</p><div class="t-src">{link}</div></div></li>'
        )
    counts = {m["name_en"]: sum(1 for it in items if it["member"] == m["name_en"]) for m in members}
    chips = f'<button class="active" data-member="all">すべて ({len(items)})</button>' + "".join(
        f'<button data-member="{html.escape(m["name_en"])}">{html.escape(m["name_ja"])} ({counts[m["name_en"]]})</button>'
        for m in members
    )
    body = "".join(rows) or '<li class="empty">まだ発言を収集していません。</li>'
    return (f'<div class="talk" id="talk-{board}"><h3>発言の時系列(新しい順)</h3><div class="chips" data-bank="{board}">{chips}</div>'
            f'<ul class="tl" id="tl-{board}">{body}</ul><p class="empty-pick" hidden>この委員の発言はまだ収集していません。</p></div>')


def section(board: str, title: str, members: list[dict], prev: dict | None, prev_date: str | None, items: list[dict]) -> str:
    attach_previous(members, prev)
    ordered = sorted(members, key=lambda m: -m["score"])
    cards = "".join(
        member_card(m, sum(1 for it in items if it["member"] == m["name_en"]), board) for m in ordered
    )
    return f"""
  <section id="sec-{board}">
    <h2>{html.escape(title)}</h2>
    {changes_panel(members, prev, prev_date)}
    <div class="spectrum-wrap">{spectrum_svg(members)}</div>
    <div class="grid">{cards}</div>
    {timeline(board, members, items)}
  </section>"""


TALK_JS = """
function filterTalk(bank, member) {
  const box = document.querySelector('.chips[data-bank="' + bank + '"]');
  box.querySelectorAll('button').forEach(b => b.classList.toggle('active', b.dataset.member === member));
  let shown = 0;
  document.querySelectorAll('#tl-' + bank + ' li[data-member]').forEach(li => {
    const on = member === 'all' || li.dataset.member === member;
    li.style.display = on ? '' : 'none';
    if (on) shown++;
  });
  box.parentElement.querySelector('.empty-pick').hidden = shown > 0 || member === 'all';
}
function pick(a) { filterTalk(a.dataset.bank, a.dataset.member); }
document.querySelectorAll('.chips').forEach(box => box.addEventListener('click', ev => {
  const b = ev.target.closest('button');
  if (b) filterTalk(box.dataset.bank, b.dataset.member);
}));
"""


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
    .changes { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:10px 14px; margin-bottom:12px; font-size:0.8rem; }
    .changes p { margin:0; color:var(--muted); }
    .scroll { overflow-x:auto; margin-top:6px; }
    .changes table { width:100%; border-collapse:collapse; }
    .changes th, .changes td { padding:4px 8px; border-bottom:1px solid var(--border); text-align:left; }
    .changes th { color:var(--muted); font-weight:500; white-space:nowrap; }
    .changes td:first-child, .changes td:nth-child(2) { white-space:nowrap; }
    .hawk { color:#f85149; } .dove { color:#58a6ff; }
    .shift { font-size:0.7rem; font-weight:600; margin-bottom:6px; }
    .term { font-size:0.7rem; color:#d29922; margin-bottom:5px; }
    .links { display:flex; gap:12px; flex-wrap:wrap; }
    .jump { position:sticky; top:0; z-index:5; background:var(--bg); display:flex; gap:6px; flex-wrap:wrap; padding:8px 0; margin-bottom:12px; border-bottom:1px solid var(--border); }
    .jump a { background:#21262c; border:1px solid var(--border); color:var(--text); padding:4px 12px; border-radius:999px; font-size:0.78rem; text-decoration:none; }
    section, .talk { scroll-margin-top:52px; }
    .talk { margin-top:22px; background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:12px 16px; }
    .talk h3 { margin:0 0 8px; font-size:0.95rem; }
    .chips { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px; }
    .chips button { background:#21262c; border:1px solid var(--border); color:var(--text); padding:3px 10px; border-radius:5px; cursor:pointer; font-size:0.74rem; }
    .chips button.active { background:var(--accent); color:#04101f; border-color:var(--accent); font-weight:600; }
    .tl { list-style:none; margin:0; padding:0; }
    .tl li { display:grid; grid-template-columns:92px 1fr; gap:10px; padding:9px 0; border-top:1px solid var(--border); }
    .t-date { color:var(--muted); font-size:0.78rem; font-variant-numeric:tabular-nums; }
    .t-head { display:flex; gap:8px; align-items:baseline; flex-wrap:wrap; font-size:0.84rem; }
    .t-type { color:var(--muted); font-size:0.72rem; }
    .t-stance { font-size:0.7rem; font-weight:600; border:1px solid; border-radius:10px; padding:0 7px; }
    .t-stance.neu { color:var(--muted); }
    .tl p { margin:3px 0 2px; font-size:0.8rem; line-height:1.55; }
    .t-src { font-size:0.7rem; } .t-src a { color:var(--accent); text-decoration:none; }
    .empty, .empty-pick { color:var(--muted); font-size:0.8rem; }
    @media (max-width:600px) { .tl li { grid-template-columns:1fr; gap:2px; } }
    footer { margin-top:32px; padding-top:14px; border-top:1px solid var(--border); color:var(--muted); font-size:0.78rem; }
    """

    prev = sync_history(data)
    prev_date = prev["date"] if prev else None
    st = json.loads(STATEMENTS_PATH.read_text(encoding="utf-8")) if STATEMENTS_PATH.exists() else {"items": []}
    body = "".join(
        section(board, title, data[board], prev[board] if prev else None, prev_date,
                [it for it in st["items"] if it["bank"] == board])
        for board, title in BOARDS.items()
    )
    st_date = html.escape(st.get("updated_at", "-"))

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
  <nav class="jump"><a href="#sec-frb">FRB</a><a href="#talk-frb">FRBの発言</a><a href="#sec-boj">日銀</a><a href="#talk-boj">日銀の発言</a></nav>
  <div class="methodology">{html.escape(data['methodology'])}<br>{html.escape(data.get('term_note', ''))}<br>発言の時系列: 更新 {st_date}。要旨は報道・公式資料の要約で、立ち位置のラベルは編集部の判断。</div>
  {body}
  <footer>
    出所: 各氏の公式略歴ページ（Federal Reserve Board / Bank of Japan / 各地区連銀）、報道各社の報道内容を基に編集部が作成<br>
    写真はFRB・各地区連銀・日本銀行の公式略歴ページの肖像。読み込めない場合はイニシャルのアバターで代替表示される
  </footer>
<script>{TALK_JS}</script>
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
