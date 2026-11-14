"""タブ: ローソク足チャートページの組み立て。

OHLC・中央銀行イベント・一般市場イベントをHTMLに埋め込み、Plotly.js でローソク足を描く。
初期表示は直近3年。ローソク足をクリックすると、その日に市場を動かした材料
(data/news/YYYY-MM.json、日次3点程度)をチャート下のパネルに表示する。
ニュースは月ごとのファイルを必要なときに読み込む。
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
NEWS_DIR = DATA_DIR / "news"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"

PLOTLY_URL = "https://cdnjs.cloudflare.com/ajax/libs/plotly.js/4.0.0/plotly.min.js"


def load_json(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def news_dates() -> list[str]:
    """ニュースを収録済みの日付(どちらかの市場に items がある日)。"""
    out = []
    for p in sorted(NEWS_DIR.glob("*.json")):
        month = json.loads(p.read_text(encoding="utf-8"))
        out += [d for d, v in month.items() if any((v.get(k) or {}).get("items") for k in ("us", "jp"))]
    return sorted(out)


CSS = """
:root { --bg:#0d1117; --panel:#161b22; --panel2:#21262c; --border:#30363d; --text:#e6edf3;
  --muted:#8b949e; --accent:#58a6ff; --pos:#3fb950; --neg:#f85149; }
* { box-sizing:border-box; }
body { background:var(--bg); color:var(--text); margin:0 auto; padding:24px 16px 60px; max-width:1100px;
  font-family:-apple-system,"Segoe UI","Hiragino Sans","Yu Gothic",sans-serif; }
h1 { font-size:1.4rem; margin-bottom:4px; }
.subtitle { color:var(--muted); font-size:.85rem; margin:0 0 16px; }
.tabs { display:flex; gap:8px; margin-bottom:12px; }
.tab-btn { background:var(--panel); border:1px solid var(--border); color:var(--text); padding:8px 20px;
  border-radius:6px; cursor:pointer; font-size:.9rem; }
.tab-btn.active { background:var(--accent); border-color:var(--accent); color:#04101f; font-weight:600; }
.controls { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:12px; background:var(--panel);
  border:1px solid var(--border); border-radius:6px; padding:8px 12px; }
.controls label { font-size:.8rem; color:var(--muted); }
.controls input[type=date] { background:var(--bg); color:var(--text); border:1px solid var(--border); border-radius:4px;
  padding:4px 6px; font-size:.85rem; }
.controls button { background:var(--panel2); color:var(--text); border:1px solid var(--border); border-radius:4px;
  padding:5px 12px; font-size:.82rem; cursor:pointer; }
.controls button.primary { background:var(--accent); color:#04101f; border-color:var(--accent); font-weight:600; }
.controls .sep { width:1px; height:22px; background:var(--border); margin:0 4px; }
#chart { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:6px; }
.legend-note { font-size:.76rem; color:var(--muted); margin-top:6px; }
.news-panel { margin-top:12px; background:var(--panel); border:1px solid var(--border); border-left:4px solid var(--accent);
  border-radius:6px; padding:12px 16px; min-height:90px; }
.np-head { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:8px; }
.np-head .date { font-size:1rem; font-weight:700; }
.np-head button { background:var(--panel2); color:var(--text); border:1px solid var(--border); border-radius:4px;
  padding:2px 10px; cursor:pointer; font-size:.8rem; }
.np-cols { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.np-col h3 { font-size:.82rem; margin:0 0 6px; color:var(--muted); font-weight:600; }
.np-col h3 b { font-size:.95rem; margin-left:6px; }
.item { border-top:1px solid var(--border); padding:7px 0; }
.item .ttl { font-size:.88rem; font-weight:600; line-height:1.45; }
.item .ttl .arw { margin-right:4px; }
.item p { margin:3px 0 2px; font-size:.8rem; line-height:1.55; color:#c9d1d9; }
.item .src { font-size:.7rem; } .item .src a { color:var(--accent); text-decoration:none; }
.up { color:var(--pos); } .down { color:var(--neg); } .flat { color:var(--muted); }
.muted { color:var(--muted); font-size:.82rem; }
.badge { display:inline-block; font-size:.68rem; padding:0 7px; border-radius:10px; margin-right:6px; font-weight:600; }
.badge.frb { color:#58a6ff; border:1px solid #1f6feb; } .badge.boj { color:#f85149; border:1px solid #f85149; }
.badge.general { color:#3fb950; border:1px solid #3fb950; }
.cb { font-size:.8rem; margin-top:8px; padding-top:6px; border-top:1px dashed var(--border); }
footer { margin-top:24px; padding-top:14px; border-top:1px solid var(--border); color:var(--muted); font-size:.76rem; }
@media (max-width:700px) { .np-cols { grid-template-columns:1fr; } }
"""

JS = r"""
const MKT = {n225: 'jp', spx: 'us'};
const NAME = {jp: '日本株(日経平均)', us: '米国株(S&P500)'};
const NEWS_SET = new Set(DATA.news_dates);
const monthCache = {};
let currentIndex = 'n225';
let selected = null;

function chgOf(key, date) {
  const rows = DATA[key];
  const i = DATA.idx[key][date];
  if (i === undefined || i === 0) return null;
  return (rows[i].c / rows[i - 1].c - 1) * 100;
}
function fmtChg(v) {
  if (v === null) return '<span class="flat">休場</span>';
  const cls = v > 0 ? 'up' : (v < 0 ? 'down' : 'flat');
  return `<span class="${cls}">${v > 0 ? '+' : ''}${v.toFixed(2)}%</span>`;
}
function esc(s) { return String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

async function loadMonth(ym) {
  if (!(ym in monthCache)) {
    monthCache[ym] = fetch(`../data/news/${ym}.json`, {cache: 'no-cache'})
      .then(r => r.ok ? r.json() : {}).catch(() => ({}));
  }
  return monthCache[ym];
}

function colHtml(mkt, key, day) {
  const block = (day && day[mkt]) || {};
  const items = block.items || [];
  const chg = chgOf(key, selected);
  let h = `<div class="np-col"><h3>${NAME[mkt]}<b>${fmtChg(chg)}</b></h3>`;
  if (!items.length) {
    h += `<div class="muted">${chg === null ? 'この日は休場です。' : 'この日の材料はまだ収集していません(順次さかのぼって追加中)。'}</div>`;
  }
  items.forEach(it => {
    const d = it.direction === 'up' ? ['up', '▲'] : (it.direction === 'down' ? ['down', '▼'] : ['flat', '・']);
    const src = it.source && it.source.url
      ? `<div class="src"><a href="${esc(it.source.url)}" target="_blank" rel="noopener">${esc(it.source.label || '出所')}</a></div>` : '';
    h += `<div class="item"><div class="ttl"><span class="arw ${d[0]}">${d[1]}</span>${esc(it.title)}</div>`
       + `<p>${esc(it.detail)}</p>${src}</div>`;
  });
  if (block.note) h += `<div class="muted">${esc(block.note)}</div>`;
  return h + '</div>';
}

function typeLabel(t) {
  return {hike:'利上げ', cut:'利下げ', hold:'据え置き', emergency_cut:'緊急利下げ', policy_change:'政策変更',
          unknown:'会合'}[t] || t;
}

async function showDay(date) {
  selected = date;
  const panel = document.getElementById('newsPanel');
  const day = (await loadMonth(date.slice(0, 7)))[date];
  if (selected !== date) return;
  const order = MKT[currentIndex] === 'jp' ? [['jp', 'n225'], ['us', 'spx']] : [['us', 'spx'], ['jp', 'n225']];
  let h = `<div class="np-head"><button onclick="step(-1)" aria-label="前の日">‹ 前日</button>`
        + `<span class="date">${date}</span><button onclick="step(1)" aria-label="次の日">翌日 ›</button></div>`;
  h += '<div class="np-cols">' + order.map(([m, k]) => colHtml(m, k, day)).join('') + '</div>';
  const cb = DATA.cb_events.filter(e => e.date === date);
  const gen = DATA.general_events.filter(e => e.date === date);
  if (cb.length || gen.length) {
    h += '<div class="cb">'
       + cb.map(e => `<div><span class="badge ${e.bank === 'FRB' ? 'frb' : 'boj'}">${e.bank}</span>${esc(typeLabel(e.type))} — ${esc(e.detail)}</div>`).join('')
       + gen.map(e => `<div><span class="badge general">材料</span>${esc(e.detail)}</div>`).join('') + '</div>';
  }
  panel.innerHTML = h;
  markSelected();
}

function step(dir) {
  const rows = DATA[currentIndex];
  let i = DATA.idx[currentIndex][selected];
  if (i === undefined) {
    const k = rows.findIndex(r => r.t > selected);
    i = k === -1 ? rows.length : k;
    if (dir < 0) i = i; else i = i - 1;
  }
  const j = Math.min(rows.length - 1, Math.max(0, i + dir));
  showDay(rows[j].t);
}

function eventShapes() {
  return DATA.cb_events.map(e => ({type:'line', xref:'x', yref:'paper', x0:e.date, x1:e.date, y0:0, y1:1,
    line:{color: e.bank === 'FRB' ? '#1f6feb' : '#f85149', width:1, dash:'dot'}, opacity:0.45}));
}

function markSelected() {
  if (!selected) return;
  const shapes = eventShapes().concat([{type:'line', xref:'x', yref:'paper', x0:selected, x1:selected, y0:0, y1:1,
    line:{color:'#e3b341', width:1.5}}]);
  Plotly.relayout('chart', {shapes});
}

let fitting = false;
function fitY(range) {
  const rows = DATA[currentIndex];
  const a = String(range[0]).slice(0, 10), b = String(range[1]).slice(0, 10);
  let lo = Infinity, hi = -Infinity;
  for (const r of rows) { if (r.t >= a && r.t <= b) { if (r.l < lo) lo = r.l; if (r.h > hi) hi = r.h; } }
  if (!isFinite(lo)) return;
  const pad = (hi - lo) * 0.05;
  fitting = true;
  Plotly.relayout('chart', {'yaxis.range': [lo - pad, hi + pad], 'yaxis.autorange': false}).then(() => { fitting = false; });
}

function yearsBack(last, n) {
  const d = new Date(last + 'T00:00:00Z');
  d.setUTCMonth(d.getUTCMonth() - Math.round(n * 12));
  return d.toISOString().slice(0, 10);
}

function setRange(from, to) {
  Plotly.relayout('chart', {'xaxis.range': [from, to]});
  document.getElementById('dateFrom').value = from;
  document.getElementById('dateTo').value = to;
}

function preset(n) {
  const rows = DATA[currentIndex], last = rows[rows.length - 1].t;
  setRange(n ? yearsBack(last, n) : rows[0].t, last);
}

function drawChart(key) {
  const rows = DATA[key];
  const dates = rows.map(r => r.t);
  const covered = dates.filter(d => NEWS_SET.has(d));
  const trace = {
    x: dates, open: rows.map(r => r.o), high: rows.map(r => r.h), low: rows.map(r => r.l), close: rows.map(r => r.c),
    type: 'candlestick', name: key === 'n225' ? '日経平均' : 'S&P500',
    increasing: {line: {color: '#3fb950'}}, decreasing: {line: {color: '#f85149'}},
  };
  const marks = {
    x: covered, y: covered.map(() => 0), yaxis: 'y2', type: 'scatter', mode: 'markers', hoverinfo: 'skip',
    marker: {symbol: 'line-ns-open', size: 6, color: '#58a6ff', opacity: 0.6}, name: 'ニュース収録日',
  };
  const last = dates[dates.length - 1];
  const from = yearsBack(last, 3);
  const layout = {
    paper_bgcolor: '#161b22', plot_bgcolor: '#161b22', font: {color: '#e6edf3'},
    margin: {t: 10, l: 56, r: 16, b: 36}, dragmode: 'pan', hovermode: 'x',
    xaxis: {range: [from, last], rangeslider: {visible: true, bgcolor: '#0d1117', bordercolor: '#30363d', thickness: 0.07},
            gridcolor: '#21262c', type: 'date'},
    yaxis: {gridcolor: '#21262c', domain: [0.04, 1]},
    yaxis2: {domain: [0, 0.03], visible: false, fixedrange: true, range: [-1, 1]},
    shapes: eventShapes(), showlegend: false,
  };
  const div = document.getElementById('chart');
  Plotly.react(div, [trace, marks], layout, {responsive: true, displaylogo: false, scrollZoom: true}).then(() => {
    document.getElementById('dateFrom').value = from;
    document.getElementById('dateTo').value = last;
    fitY([from, last]);
    if (div.removeAllListeners) { div.removeAllListeners('plotly_click'); div.removeAllListeners('plotly_relayout'); }
    div.on('plotly_click', ev => { if (ev.points && ev.points.length) showDay(String(ev.points[0].x).slice(0, 10)); });
    div.on('plotly_relayout', ev => {
      if (fitting) return;
      const r = ev['xaxis.range'] || (ev['xaxis.range[0]'] !== undefined && [ev['xaxis.range[0]'], ev['xaxis.range[1]']]);
      if (r) fitY(r);
      else if (ev['xaxis.autorange']) fitY([dates[0], last]);
    });
    if (selected) markSelected();
  });
}

function switchIndex(key) {
  currentIndex = key;
  document.getElementById('btn-n225').classList.toggle('active', key === 'n225');
  document.getElementById('btn-spx').classList.toggle('active', key === 'spx');
  drawChart(key);
  if (selected) showDay(selected);
}

function applyCustomRange() {
  const from = document.getElementById('dateFrom').value, to = document.getElementById('dateTo').value;
  if (from && to) setRange(from, to);
}

document.addEventListener('keydown', e => {
  if (!selected || e.target.tagName === 'INPUT') return;
  if (e.key === 'ArrowLeft') step(-1);
  if (e.key === 'ArrowRight') step(1);
});

drawChart('n225');
const rows0 = DATA.n225;
showDay(DATA.news_dates.length ? DATA.news_dates[DATA.news_dates.length - 1] : rows0[rows0.length - 1].t);
"""


def build_html() -> str:
    data = {
        "spx": load_json("spx_ohlc.json"),
        "n225": load_json("n225_ohlc.json"),
        "cb_events": load_json("central_bank_events.json"),
        "general_events": load_json("general_market_events.json"),
        "news_dates": news_dates(),
    }
    for k in ("spx", "n225"):
        data[k] = [{kk: r[kk] for kk in ("t", "o", "h", "l", "c")} for r in data[k]]
    last = {k: data[k][-1]["t"] for k in ("spx", "n225")}
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    n_news = len(data["news_dates"])
    first_news = data["news_dates"][0] if n_news else "-"
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>マーケットチャート</title>
<script src="{PLOTLY_URL}"></script>
<style>{CSS}</style>
</head>
<body>
  <h1>マーケットチャート</h1>
  <p class="subtitle">日経平均 / S&amp;P500。ローソク足をクリックすると、その日に市場を動かした材料(日米それぞれ3点程度)を下に表示します。
  ← → キーで前後の日に移動できます。</p>

  <div class="tabs">
    <button class="tab-btn active" id="btn-n225" onclick="switchIndex('n225')">日経平均株価</button>
    <button class="tab-btn" id="btn-spx" onclick="switchIndex('spx')">S&amp;P500</button>
  </div>

  <div class="controls">
    <button onclick="preset(0.5)">6か月</button><button onclick="preset(1)">1年</button>
    <button onclick="preset(3)">3年</button><button onclick="preset(5)">5年</button><button onclick="preset(0)">全期間</button>
    <span class="sep"></span>
    <label>期間</label><input type="date" id="dateFrom"><span class="muted">〜</span><input type="date" id="dateTo">
    <button class="primary" onclick="applyCustomRange()">適用</button>
  </div>

  <div id="chart" style="height:540px"></div>
  <div class="legend-note">
    <span class="badge frb">FRB</span>FOMC <span class="badge boj">日銀</span>決定会合(点線)
    ・ 黄色の線: 選択中の日 ・ 下端の青い目盛: ニュース収録済みの日({n_news}日分、{first_news}〜)
  </div>

  <div class="news-panel" id="newsPanel"><div class="muted">読み込み中…</div></div>

  <footer>
    株価: Yahoo Finance(日経平均 {last['n225']}、S&amp;P500 {last['spx']} まで)。平日に自動更新。<br>
    日々の材料: 報道を基に、その日の値動きに効いたものを日米それぞれ3点程度に要約(新しい日は毎朝追加し、過去分は順次さかのぼって収集)。
    要約は二次情報で、因果は報道の説明に基づきます。<br>
    中央銀行イベント: FRB・日銀の公表資料を基に整備。
  </footer>

<script>
const DATA = {data_json};
DATA.idx = {{}};
for (const k of ['spx', 'n225']) {{ DATA.idx[k] = {{}}; DATA[k].forEach((r, i) => DATA.idx[k][r.t] = i); }}
{JS}
</script>
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
    print(f"チャートページを生成しました: {path}")
