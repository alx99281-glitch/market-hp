# 分析の視点

X とニュースで拾った論点を、公開データで検証して掲載するタブ。

## 更新手順

```bash
python insights/src/compute_signals.py   # data/signals.json を更新
# data/editions/YYYY-MM-DD.json を追加（signals.json の数値のみ引用する）
python insights/src/build_page.py        # output/ を生成
```

平日の自動更新は次の2段階で動く。PCは使わない。

1. GitHub Actions の `insights-data.yml` が NY 引け後に株価を取得し、`market-data` ブランチへ上書きする。
2. 07:00 SGT のクラウド定期実行が、そのデータで分析して号を作り、main へ push する。

### データが古いとき（定期実行の手順4より優先して行う）

GitHub Actions の schedule は数時間〜10時間程度遅れることがあり、07:00 SGT の時点で前営業日分が入っていない場合がある。
`manifest.json` の `last_date` が期待する取引日より古ければ、すぐに諦めず次を行う。

1. GitHub MCP の `actions_run_trigger`（method `run_workflow`, workflow `insights-data.yml`, ref `main`）で取得ジョブを手動起動する。
2. `actions_list`（`list_workflow_runs`, `insights-data.yml`）で、起動したrunが `completed` になるまで確認する（通常2〜3分。Monitorでの条件待ちを使い、`sleep` で長時間待たない。最大15分）。
3. `conclusion` が `success` なら `market-data` を取り直して手順を続ける。失敗・タイムアウト、または再取得後も古い場合（Yahoo側の未更新など）は、公開せず報告して終了する。

クラウド環境から Yahoo Finance には接続できないので、`compute_signals.py` と `fetch_market_data.py` は Actions でだけ動かす。
取得する銘柄は `data/universe.json` で管理する。S&P500 と日経225の採用銘柄は `daily-review/data` にある。

各号は固定スナップショットで、過去号はページ右上から参照できる。
X はタイムラインを直接取得せず、検索経由の投稿のみ扱う。投稿は要約し、未検証である旨を明記する。
