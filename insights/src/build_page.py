"""insights/data/editions/*.json から「分析の視点」タブのHTMLを生成する。

最新号を output/index.html、各号を output/YYYY-MM-DD.html に書き出す。
"""

from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITIONS = ROOT / "data" / "editions"
OUTPUT = ROOT / "output"

VERDICTS = {"支持": "ok", "条件付き": "warn", "反証": "bad", "要観察": "watch"}

CSS = """
:root { --bg:#0d1117; --panel:#161b22; --panel2:#21262c; --border:#30363d; --text:#e6edf3;
  --muted:#8b949e; --accent:#58a6ff; --ok:#3fb950; --warn:#d29922; --bad:#f85149; --watch:#a371f7; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); line-height:1.65;
  font-family:-apple-system,"Segoe UI","Hiragino Sans","Yu Gothic",sans-serif; }
.wrap { max-width:1120px; margin:0 auto; padding:24px 20px 56px; }
.top { display:flex; justify-content:space-between; gap:12px; align-items:center; color:var(--muted); font-size:.8rem; }
select { background:var(--panel2); color:var(--text); border:1px solid var(--border); border-radius:5px; padding:4px 8px; }
h1 { font-size:1.5rem; line-height:1.35; margin:10px 0 8px; }
.lead { color:var(--muted); max-width:820px; margin:0 0 18px; }
.snap { display:grid; grid-template-columns:repeat(auto-fit,minmax(135px,1fr)); gap:8px; margin-bottom:18px; }
.snap div { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:8px 12px; }
.snap span { display:block; color:var(--muted); font-size:.72rem; }
.snap b { font-size:1rem; font-variant-numeric:tabular-nums; }
.filters { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px; }
.filters button { background:var(--panel2); border:1px solid var(--border); color:var(--text);
  padding:5px 12px; border-radius:5px; cursor:pointer; font-size:.8rem; }
.filters button.active { background:var(--accent); color:#04101f; border-color:var(--accent); font-weight:600; }
.grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; align-items:start; }
.card { background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:16px 18px; min-width:0; }
.meta { display:flex; justify-content:space-between; gap:8px; font-size:.75rem; color:var(--muted); }
.badge { font-weight:600; }
.ok { color:var(--ok); } .warn { color:var(--warn); } .bad { color:var(--bad); } .watch { color:var(--watch); }
h2 { font-size:1.08rem; line-height:1.4; margin:6px 0 8px; }
h3 { font-size:.74rem; color:var(--muted); margin:12px 0 2px; font-weight:600; }
p { margin:0; font-size:.88rem; } ul { margin:0; padding-left:1.1em; font-size:.84rem; } li { margin:2px 0; }
.post { background:var(--panel2); border-left:3px solid var(--accent); padding:7px 10px; border-radius:0 5px 5px 0; }
.scroll { overflow-x:auto; margin-top:10px; }
table { width:100%; border-collapse:collapse; font-size:.8rem; font-variant-numeric:tabular-nums; }
caption { text-align:left; color:var(--muted); font-size:.74rem; padding-bottom:4px; }
th,td { padding:4px 8px; border-bottom:1px solid var(--border); text-align:right; white-space:nowrap; }
th:first-child,td:first-child { text-align:left; } th { color:var(--muted); font-weight:500; }
.note { color:var(--muted); font-size:.74rem; margin-top:4px; }
.src { margin-top:12px; font-size:.74rem; color:var(--muted); }
a { color:var(--accent); text-decoration:none; } a:hover { text-decoration:underline; }
.section { font-size:1.15rem; margin:30px 0 10px; }
.x { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:10px 14px; margin-bottom:8px; }
.x p + p { color:var(--muted); font-size:.82rem; }
.method { color:var(--muted); font-size:.76rem; margin-top:26px; border-top:1px solid var(--border); padding-top:12px; }
@media (max-width:760px) { .grid { grid-template-columns:minmax(0,1fr); } .wrap { padding:16px 16px 40px; } }
"""

JS = """
document.querySelectorAll('.filters button').forEach(b => b.onclick = () => {
  document.querySelectorAll('.filters button').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  document.querySelectorAll('.card').forEach(c => {
    c.style.display = (b.dataset.t === 'all' || c.dataset.t === b.dataset.t) ? '' : 'none';
  });
});
"""


def e(s) -> str:
    return html.escape(str(s))


def link(url: str, label: str) -> str:
    return f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer">{e(label)}</a>'


def table(t: dict) -> str:
    head = "".join(f"<th>{e(h)}</th>" for h in t["headers"])
    rows = "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>" for r in t["rows"])
    note = f'<div class="note">{e(t["note"])}</div>' if t.get("note") else ""
    return (f'<div class="scroll"><table><caption>{e(t["caption"])}</caption>'
            f"<thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>{note}")


def card(c: dict) -> str:
    cls = VERDICTS.get(c["verdict"], "watch")
    evidence = "".join(f"<li>{e(x)}</li>" for x in c["evidence"])
    sources = " / ".join(link(s["url"], s["label"]) for s in c["sources"])
    return f"""<article class="card" data-t="{e(c['theme'])}">
<div class="meta"><span>{e(c['theme'])}</span><span class="badge {cls}">検証: {e(c['verdict'])}</span></div>
<h2>{e(c['title'])}</h2>
<p>{e(c['claim'])}</p>
<h3>データ</h3><ul>{evidence}</ul>
{table(c['table']) if c.get('table') else ''}
<h3>日本株への含意</h3><p>{e(c['japan'])}</p>
<h3>見方を変える条件</h3><p>{e(c['falsify'])}</p>
<h3>発信用の一言</h3><p class="post">{e(c['post'])}</p>
<div class="src">ネタ元: {sources}</div>
</article>"""


def page(ed: dict, dates: list[str]) -> str:
    options = "".join(
        f'<option value="{d}.html"{" selected" if d == ed["date"] else ""}>{d}</option>' for d in dates
    )
    snap = "".join(f"<div><span>{e(s['label'])}</span><b>{e(s['value'])}</b></div>" for s in ed["snapshot"])
    themes = list(dict.fromkeys(c["theme"] for c in ed["cards"]))
    filters = '<button class="active" data-t="all">すべて</button>' + "".join(
        f'<button data-t="{e(t)}">{e(t)}</button>' for t in themes
    )
    cards = "".join(card(c) for c in ed["cards"])
    xs = "".join(
        f'<div class="x"><p>{link(x["url"], x["topic"])}（{e(x["status"])}）</p><p>{e(x["angle"])}</p></div>'
        for x in ed["x_topics"]
    )
    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>分析の視点 {e(ed['date'])}</title><style>{CSS}</style></head>
<body><div class="wrap">
<div class="top"><span>分析の視点 ・ {e(ed['as_of'])}</span>
<select aria-label="号を選択" onchange="location.href=this.value">{options}</select></div>
<h1>{e(ed['headline'])}</h1><p class="lead">{e(ed['lead'])}</p>
<div class="snap">{snap}</div>
<div class="filters">{filters}</div>
<div class="grid">{cards}</div>
<h2 class="section">Xで拾った論点</h2>{xs}
<p class="method">{e(ed['method'])} 情報提供を目的としたもので、投資勧誘ではありません。</p>
</div><script>{JS}</script></body></html>
"""


def main():
    eds = sorted(
        (json.loads(p.read_text(encoding="utf-8")) for p in EDITIONS.glob("*.json")),
        key=lambda d: d["date"], reverse=True,
    )
    dates = [d["date"] for d in eds]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for ed in eds:
        (OUTPUT / f"{ed['date']}.html").write_text(page(ed, dates), encoding="utf-8")
    (OUTPUT / "index.html").write_text(page(eds[0], dates), encoding="utf-8")
    print(f"built {len(eds)} edition(s), latest {dates[0]}")


if __name__ == "__main__":
    main()
