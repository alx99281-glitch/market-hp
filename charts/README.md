# マーケットチャート

日経平均・S&P500の10年ローソク足。初期表示は直近3年で、表示範囲に合わせて縦軸を自動調整する。
ローソク足をクリックすると、その日に市場を動かした材料(日米それぞれ3点程度)をチャート下に表示する。
← → キーで前後の日に移動できる。

## データ

- `data/spx_ohlc.json`, `data/n225_ohlc.json`: `src/fetch_chart_data.py` が取得(Yahoo Finance、10年)。
  GitHub Actions の `daily-update.yml` が平日に取得し、ページを作り直す。
- `data/news/YYYY-MM.json`: 日々の材料。月ごとのファイルで、ページはクリックした月だけ読み込む。

```json
{"2026-11-05": {
  "us": {"items": [{"title": "見出し", "detail": "1〜2文の説明", "direction": "up|down|flat",
                    "source": {"label": "出所", "url": "https://..."}}]},
  "jp": {"items": [...]}
}}
```

  報道で確認できない日は `items` を空にし、`note` に「報道を確認できず」などと書く(収集済みとして扱う)。
- `data/central_bank_events.json`, `data/general_market_events.json`: FOMC・日銀会合と主な材料(点線とパネル下部に表示)。

## 日々の材料の集め方

- 新しい日: 毎朝の「分析の視点」の定期実行が前日の米国(`us`)を、夕方の「日本・アジア」の定期実行がその日の日本(`jp`)を足す。
- 過去分: 2時間ごとの定期実行がさかのぼって集める。`python charts/src/news_backlog.py 12` が未収集の日を
  (直近7日 → 日米どちらかが2%以上動いた日を大きい順 → 残りを新しい順)で出すので、その順に調べて足す。
  対象は直近3年。全部埋まったら定期実行を止める。
- 定期実行は `data/news` だけをコミットし、`output/` は作り直さない(複数の定期実行が同じ生成ファイルを書き換えて
  push が競合するのを避けるため)。材料はクリック時に読み込むので、追加すればすぐ表示される。
  収録日の目盛は平日の `daily-update.yml` がページを作り直すときに更新される。

```bash
python src/fetch_chart_data.py
python src/build_page.py   # -> output/index.html
```

Plotly.js 4.0.0(cdnjs)を使う。閲覧時にインターネット接続が必要。
