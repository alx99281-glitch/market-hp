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

クラウド環境から Yahoo Finance には接続できないので、`compute_signals.py` と `fetch_market_data.py` は Actions でだけ動かす。
取得する銘柄は `data/universe.json` で管理する。S&P500 と日経225の採用銘柄は `daily-review/data` にある。

各号は固定スナップショットで、過去号はページ右上から参照できる。
X はタイムラインを直接取得せず、検索経由の投稿のみ扱う。投稿は要約し、未検証である旨を明記する。
