# 分析の視点

X とニュースで拾った論点を、公開データで検証して掲載するタブ。

## 更新手順

```bash
python insights/src/compute_signals.py   # data/signals.json を更新
# data/editions/YYYY-MM-DD.json を追加（signals.json の数値のみ引用する）
python insights/src/build_page.py        # output/ を生成
```

平日 06:30 SGT に Claude デスクトップアプリの定期タスク `market-insights-daily` が上記を実行し、main へ push する。
アプリが閉じている間は動かず、次回起動時に実行される。GitHub Actions では動かない。

各号は固定スナップショットで、過去号はページ右上から参照できる。
X はタイムラインを直接取得せず、検索経由の投稿のみ扱う。投稿は要約し、未検証である旨を明記する。
