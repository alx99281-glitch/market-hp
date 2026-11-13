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

## 号に載せるセクション

カード(分析の視点)に加えて、各号に次の2つを載せる。どちらも editions の JSON に入れ、`build_page.py` が描画する(キーがなければ表示しない)。

### 大きく動いたもの(`big_moves`)

チャートを見て「お!」と思う動きを、株価に限らず、為替、商品、金利、経済指標から選ぶ。

1. `python insights/src/scan_big_moves.py insights/data/analysis/YYYY-MM-DD_big_moves_candidates.json --asof <号の基準日(米国の最終取引日)>` で候補を出す。
   各系列を自分自身の過去と比べ、1か月の変化が分布の端にあるもの、1年以上ぶりの高値・安値、1日の変化が分布の端にあるもの、経済指標(FRED)の大きな変化や何年ぶりかの水準を拾う。
   `--asof` を付けないと、取引途中の東京の値などが混ざる。
2. 候補から6〜10個を選び、それぞれに「なぜ目立つか(何年ぶり、分布のどこか)」と短い解説を付ける。同じ話(例: AI関連の下げ)は1〜2枚にまとめ、日本株、海外株、クロスアセット、経済指標がばらけるようにする。
3. 各要素: `label`, `group`, `metric`(例「1か月 -40.3%」), `since`(例「1996年8月以来の高水準」), `comment`, `direction`(`up`/`down`), `series`(候補JSONの `series` をそのまま使う), 任意で `source`({label, url})。
4. 採用銘柄(S&P500、日経225)の履歴は約3年しかないので、「過去3年で」と期間を書く。月次の経済指標は最新月を書く(例「3.05%(9月)」)。

経済指標は GitHub Actions が FRED の CSV から取得し、market-data の `fred.parquet` に置く。系列は `data/universe.json` の `fred` で管理する。

### 大物投資家の相場観(`investors`)

著名投資家(ヘッジファンド、資産運用会社、著名アナリストなど)の直近の相場観を一覧にし、傾向をまとめる。

1. WebSearch で、直近1〜2週間の発言・インタビュー・持ち高(13Fなど)を広く探す(人物は固定しない。例: ダリオ、ドラッケンミラー、チューダー・ジョーンズ、アックマン、バーリ、グリフィン、マークス、ガンドラック、ダイモン、フィンク、バークシャー、日本の著名投資家)。新しい発言がない人物は、前号の内容を日付付きで残してよいが、古いものは外していく。
2. `items`: `name`, `role`, `date`(発言の時期。不明なら「時期不明」), `topic`, `stance`(強気/弱気/中立/慎重/混在), `view`(要旨。長く引用しない), `source`({label, url}), `status`(報道/投稿の要約、未検証/二次情報 など)。新しい順に並べる。
3. `trend`: テーマ別に `theme`, `bull`, `bear`, `neutral` を書き、誰がどちら側かを並べる。
4. `summary`: 多数派はどちらか、論点の共通項、その日のカードや相場との関係、見方が割れている点を書く。日本の投資家の発言が見つからなければ、その旨を書く。
5. 13Fは四半期末時点の持ち高なので、その旨を書く。確認できない発言は載せない。

## 取得データの注意

先物と為替の「前日終値」は、取得した時点では確定前の値のことがあり、後で更新される(11/12の金先物は3,882.3→3,918.9)。号の数値は取得時点のものと明記し、後で大きく違うと分かったら、その号の `method` に訂正を書く。

各号は固定スナップショットで、過去号はページ右上から参照できる。
X はタイムラインを直接取得せず、検索経由の投稿のみ扱う。投稿は要約し、未検証である旨を明記する。
