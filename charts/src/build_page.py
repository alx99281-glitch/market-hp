"""タブ1: ローソク足チャートページの組み立て。

データ(OHLC・中央銀行イベント・一般市場イベント)をJSONとしてHTMLに埋め込み、
Plotly.js（cdnjs, ローカルhtmlなのでCDN許容）でローソク足+レンジスライダー+
カスタム日付範囲+ホバー時ニュース表示を実装する。
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"

PLOTLY_URL = "https://cdnjs.cloudflare.com/ajax/libs/plotly.js/4.0.0/plotly.min.js"


def load_json(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def build_html() -> str:
    spx = load_json("spx_ohlc.json")
    n225 = load_json("n225_ohlc.json")
    cb_events = load_json("central_bank_events.json")
    general_events = load_json("general_market_events.json")

    data_json = json.dumps(
        {"spx": spx, "n225": n225, "cb_events": cb_events, "general_events": general_events},
        ensure_ascii=False,
    )

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>マーケットチャート（日経平均・S&amp;P500）</title>
<script src="{PLOTLY_URL}"></script>
<style>
  :root {{
    --bg: #0d1117; --panel: #161b22; --border: #30363d; --text: #e6edf3;
    --muted: #8b949e; --accent: #58a6ff; --pos: #3fb950; --neg: #f85149;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg); color: var(--text); margin: 0; padding: 24px 16px 60px;
    font-family: -apple-system, "Segoe UI", "Hiragino Sans", "Yu Gothic", sans-serif;
    max-width: 1100px; margin-left: auto; margin-right: auto;
  }}
  h1 {{ font-size: 1.4rem; margin-bottom: 4px; }}
  .subtitle {{ color: var(--muted); font-size: 0.85rem; margin-top: 0; margin-bottom: 20px; }}
  .tabs {{ display: flex; gap: 8px; margin-bottom: 16px; }}
  .tab-btn {{
    background: var(--panel); border: 1px solid var(--border); color: var(--text);
    padding: 8px 20px; border-radius: 6px; cursor: pointer; font-size: 0.9rem;
  }}
  .tab-btn.active {{ background: var(--accent); border-color: var(--accent); color: #04101f; font-weight: 600; }}
  .controls {{
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 14px;
    background: var(--panel); border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px;
  }}
  .controls label {{ font-size: 0.82rem; color: var(--muted); }}
  .controls input[type=date] {{
    background: #0d1117; color: var(--text); border: 1px solid var(--border);
    border-radius: 4px; padding: 4px 6px; font-size: 0.85rem;
  }}
  .controls button {{
    background: var(--accent); color: #04101f; border: none; border-radius: 4px;
    padding: 6px 14px; font-size: 0.85rem; font-weight: 600; cursor: pointer;
  }}
  .controls button.secondary {{ background: transparent; color: var(--accent); border: 1px solid var(--accent); }}
  #chart {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 6px; }}
  .news-panel {{
    margin-top: 14px; background: var(--panel); border: 1px solid var(--border);
    border-left: 4px solid var(--accent); border-radius: 6px; padding: 14px 18px; min-height: 70px;
  }}
  .news-panel .date {{ font-size: 0.8rem; color: var(--muted); margin-bottom: 6px; }}
  .news-panel .event {{ margin-bottom: 8px; font-size: 0.92rem; line-height: 1.6; }}
  .news-panel .badge {{
    display: inline-block; font-size: 0.7rem; padding: 1px 8px; border-radius: 10px;
    margin-right: 6px; font-weight: 600;
  }}
  .badge.frb {{ background: #1f6feb33; color: #58a6ff; border: 1px solid #1f6feb; }}
  .badge.boj {{ background: #f8514933; color: #f85149; border: 1px solid #f85149; }}
  .badge.general {{ background: #3fb95033; color: #3fb950; border: 1px solid #3fb950; }}
  .legend-note {{ font-size: 0.78rem; color: var(--muted); margin-top: 6px; }}
  footer {{ margin-top: 24px; padding-top: 14px; border-top: 1px solid var(--border); color: var(--muted); font-size: 0.78rem; }}
</style>
</head>
<body>
  <h1>マーケットチャート（10年）</h1>
  <p class="subtitle">日経平均株価 / S&amp;P500 — ローソク足に中央銀行イベント等を重ね、日付にカーソルを合わせるとニュースを表示</p>

  <div class="tabs">
    <button class="tab-btn active" id="btn-n225" onclick="switchIndex('n225')">日経平均株価</button>
    <button class="tab-btn" id="btn-spx" onclick="switchIndex('spx')">S&amp;P500</button>
  </div>

  <div class="controls">
    <label>期間指定:</label>
    <input type="date" id="dateFrom">
    <span style="color:var(--muted)">〜</span>
    <input type="date" id="dateTo">
    <button onclick="applyCustomRange()">適用</button>
    <button class="secondary" onclick="resetRange()">全期間表示</button>
  </div>

  <div id="chart" style="height:560px"></div>
  <div class="legend-note">
    <span class="badge frb">FRB</span>FOMC会合
    <span class="badge boj">日銀</span>金融政策決定会合
    <span class="badge general">材料</span>その他の市場材料
    　― グラフ下部の縦線が該当日
  </div>

  <div class="news-panel" id="newsPanel">
    <div class="date">ローソク足にカーソルを合わせてください</div>
    <div class="event" style="color:var(--muted)">中央銀行イベントや主要な市場材料がある日は、ここに表示されます。</div>
  </div>

  <footer>
    データ出所: Yahoo Finance (yfinance) / 中央銀行イベント: FRB・日銀公表資料を基に手動整備<br>
    ニュース収録は代表的なイベントの一部（全営業日を網羅する自動収集は未実装。daily-review側のニュース照合バッチと同様の仕組みで拡充予定）<br>
    生成: build_page.py
  </footer>

<script>
const DATA = {data_json};

function eventsForDate(dateStr) {{
  const cb = DATA.cb_events.filter(e => e.date === dateStr);
  const gen = DATA.general_events.filter(e => e.date === dateStr);
  return {{ cb, gen }};
}}

function bankBadgeClass(bank) {{ return bank === 'FRB' ? 'frb' : 'boj'; }}

function typeLabel(t) {{
  return {{hike:'利上げ', cut:'利下げ', hold:'据え置き', emergency_cut:'緊急利下げ',
           policy_change:'政策変更', unknown:'会合（結果未確認）'}}[t] || t;
}}

function renderNewsPanel(dateStr) {{
  const panel = document.getElementById('newsPanel');
  const {{ cb, gen }} = eventsForDate(dateStr);
  if (cb.length === 0 && gen.length === 0) {{
    panel.innerHTML = `<div class="date">${{dateStr}}</div><div class="event" style="color:var(--muted)">特筆すべき中央銀行イベント・登録済み材料はありません。</div>`;
    return;
  }}
  let html = `<div class="date">${{dateStr}}</div>`;
  cb.forEach(e => {{
    html += `<div class="event"><span class="badge ${{bankBadgeClass(e.bank)}}">${{e.bank}}</span>${{typeLabel(e.type)}} — ${{e.detail}}</div>`;
  }});
  gen.forEach(e => {{
    html += `<div class="event"><span class="badge general">材料</span>${{e.detail}}</div>`;
  }});
  panel.innerHTML = html;
}}

function eventShapes(dates) {{
  const dateSet = new Set(dates);
  const shapes = [];
  DATA.cb_events.forEach(e => {{
    if (dateSet.has(e.date)) {{
      shapes.push({{type:'line', xref:'x', yref:'paper', x0:e.date, x1:e.date, y0:0, y1:1,
                    line:{{color: e.bank === 'FRB' ? '#1f6feb' : '#f85149', width:1, dash:'dot'}}, opacity:0.5}});
    }}
  }});
  return shapes;
}}

let currentIndex = 'n225';

function ohlcTraces(key) {{
  const rows = DATA[key];
  const dates = rows.map(r => r.t);
  return {{
    dates,
    trace: {{
      x: dates, open: rows.map(r=>r.o), high: rows.map(r=>r.h),
      low: rows.map(r=>r.l), close: rows.map(r=>r.c),
      type: 'candlestick', name: key === 'n225' ? '日経平均' : 'S&P500',
      increasing: {{line:{{color:'#3fb950'}}}}, decreasing: {{line:{{color:'#f85149'}}}},
    }}
  }};
}}

function drawChart(key) {{
  const {{ dates, trace }} = ohlcTraces(key);
  const layout = {{
    paper_bgcolor: '#161b22', plot_bgcolor: '#161b22',
    font: {{color: '#e6edf3'}},
    margin: {{t:10, l:50, r:20, b:40}},
    xaxis: {{
      rangeslider: {{visible: true, bgcolor:'#0d1117', bordercolor:'#30363d'}},
      rangeselector: {{
        bgcolor: '#21262c', activecolor: '#1f6feb', font: {{color:'#e6edf3'}},
        buttons: [
          {{count:6, label:'6ヶ月', step:'month', stepmode:'backward'}},
          {{count:1, label:'1年', step:'year', stepmode:'backward'}},
          {{count:3, label:'3年', step:'year', stepmode:'backward'}},
          {{count:5, label:'5年', step:'year', stepmode:'backward'}},
          {{step:'all', label:'全期間'}},
        ]
      }},
      gridcolor: '#21262c',
    }},
    yaxis: {{gridcolor: '#21262c', title: '価格'}},
    shapes: eventShapes(dates),
    showlegend: false,
  }};
  Plotly.react('chart', [trace], layout, {{responsive:true, displaylogo:false}});

  const chartDiv = document.getElementById('chart');
  chartDiv.on('plotly_hover', function(evt) {{
    if (evt.points && evt.points.length > 0) {{
      renderNewsPanel(evt.points[0].x);
    }}
  }});

  if (dates.length) {{
    document.getElementById('dateFrom').value = dates[0];
    document.getElementById('dateTo').value = dates[dates.length - 1];
  }}
}}

function switchIndex(key) {{
  currentIndex = key;
  document.getElementById('btn-n225').classList.toggle('active', key === 'n225');
  document.getElementById('btn-spx').classList.toggle('active', key === 'spx');
  drawChart(key);
}}

function applyCustomRange() {{
  const from = document.getElementById('dateFrom').value;
  const to = document.getElementById('dateTo').value;
  if (!from || !to) return;
  Plotly.relayout('chart', {{'xaxis.range': [from, to], 'xaxis.autorange': false}});
}}

function resetRange() {{
  Plotly.relayout('chart', {{'xaxis.autorange': true}});
}}

drawChart('n225');
</script>
</body>
</html>
"""
    return html


def write_page() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "index.html"
    out_path.write_text(build_html(), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    path = write_page()
    print(f"チャートページを生成しました: {path}")
