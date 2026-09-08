# 日次マーケット振り返りシステム（米国・日本版）

SPEC_1.md フェーズ1〜7の実装。HPの3タブ構成のうち「タブ2: 毎日の市場サマリー」の
土台にあたる。米国版・日本版は `market_context.py` の `MarketContext` で切り替える
共通コード（decompose.py / pca.py / zscore.py / structure_monitor.py / report.py /
html_report.py / html_structure.py はどちらの市場にも使う）。

## 現在の実装状況

| フェーズ | 内容 | 状態 |
|---|---|---|
| 1 | データ層（永続化・初回一括取得・差分追記・Stooqフォールバック） | 完了（米国・日本） |
| 2 | 層1〜2（リターン分解 + zスコア異常検知） | 完了（米国・日本） |
| 3 | 層3（PCA: 週次軸推定 + 日次射影 + 残差比率） | 完了（銘柄レベル+セクターETFレベル） |
| 4 | 層4（構造変化モニタ、週次+月次サマリー） | 完了（米国・日本） |
| 5 | HTMLレポート生成 | 完了（日次レポート+構造ページ、米国・日本） |
| 6 | 日本版 | 完了（層1〜4・HTML。データソースは日経225） |
| 7 | 層5（ニュース照合） | 完了（本日分は実データで検証済み。無人バッチはAPIキー未設定のため未実行） |
| 8 | スケジューリング・自動アップロード | 未着手 |

## 使い方

```bash
python -m pip install -r requirements.txt
cd src

# 初回のみ
python fetch_us_universe.py   # S&P500構成銘柄503 + セクターETF11 + ファクターETF6 + 指数、3年分
python fetch_jp_universe.py   # 日経225構成銘柄225 + TOPIX-17セクターETF + グロース/バリューETF + 指数、3年分

# 週次: ファンダメンタルズ・スナップショット更新（Value/Growth/Quality/Size用）
python fundamentals.py         # 米国
python fundamentals.py --jp    # 日本

# 毎日（引け後）: ニュース照合 → コンソールレポート / 静的HTMLレポート生成
export ANTHROPIC_API_KEY=...           # 層5の無人実行に必要（未設定ならスキップ可）
python news_lookup_batch.py            / python news_lookup_batch.py --jp
python report.py                       / python report.py --jp
python html_report.py                  / python html_report.py --jp
# -> reports/us/YYYY-MM-DD.html, reports/us/latest.html （日本版は reports/jp/ 配下）

# 週次: 構造ページ更新（層4を差分計算してHTML化）
python html_structure.py       / python html_structure.py --jp
# -> reports/structure/us/index.html （日本版は reports/structure/jp/ 配下）
```

## 実装上の判断・注意点（未決事項への回答）

- **8ファクターの土台システム**: 既存システムは無かったため新規実装。
  - Momentum / Beta / Volatility / Liquidity は価格・出来高データのみで
    自前計算（クインタイル・ロングショート、上位20% - 下位20%の等加重リターン）。
  - Value(PBR) / Growth(売上成長率) / Quality(ROE) / Size(時価総額) は
    yfinanceのファンダメンタルズ・スナップショットに依存するため、
    `fundamentals.py` で週次更新を想定した別ジョブに分離（数百銘柄の
    `Ticker.info` 取得は数分かかるため）。日次では最新スナップショットを
    全期間に適用する近似（ファンダメンタルズ自体は日次で大きく変わらないため）。
  - 各ファクター・セクターとも、対応するETF（米国: MTUM/VLUE/QUAL/USMV/IWM/SPY、
    セクターSPDR11本。日本: 2516/2517グロース・バリューETF、TOPIX-17セクター
    ETF1617〜1633）ベースの簡易版を並記し、整合性チェックできるようにした。
    自前計算名とETF簡易版名の対応は `config.US_FACTOR_ETF_MAP` /
    `JP_FACTOR_ETF_MAP` で明示（部分一致による誤対応を防ぐため）。
- **セクターウェイト**:
  - 米国: S&P500の公式内訳ではなく、SPY(ETF)の保有構成
    （`yfinance` の `funds_data.sector_weightings`）をcap-weightの近似として使用。
  - 日本: TOPIX-17の公式時価総額ウェイトを無料で取得する手段が見つからなかった
    ため、日経225構成銘柄数のセクター別比率で代用（`sector_weights.compute_jp_sector_weights`）。
    時価総額ウェイトではない点に注意。正式なウェイトソースが見つかり次第置き換えるべき。
  - いずれも週次更新想定。
- **日本株個別データソース**: yfinanceの `.T` サフィックスで日経225構成銘柄
  （英数字コード含む、例: 285A.T）が安定して取得できることを確認。TOPIX500まで
  対象を広げていない（日経225の225銘柄のみ）。個別銘柄の一覧・業種は
  Wikipedia日本語版「日経平均株価」ページをスクレイピングして取得
  （`universe_jp.py`）。日経独自の業種区分をTOPIX-17業種に近似マッピングして
  いる（`universe_jp.NIKKEI_TO_TSE17`。TSE公式33業種分類とは完全一致ではない）。
  ^TOPX はyfinanceで取得不可だったため、1306.T（TOPIX連動ETF）で代用
  （仕様書に記載のフォールバック方針どおり）。
- **Stooqフォールバック**: コードは実装済みだが、2026年9月時点でStooqの
  CSVダウンロードエンドポイントにJSベースの簡易ボット対策が入っており、
  単純なHTTPリクエストでは取得できないことを確認した。失敗時は警告を出して
  処理を継続する設計にしてあるため、システム全体は止まらないが、
  「yfinance失敗時に確実にStooqへ切り替わる」状態には現状なっていない。
  日本株のStooqシンボル形式（`.jp`等）も未検証。信頼性が必要なら有料/無料
  APIキー方式の代替ソース（Alpha Vantage等）を検討する必要がある。
- **zスコアのローリング更新**: 仕様書は「差分更新（当日追加・N日前削除）」を
  求めているが、このデータ規模（3年 x 数百系列）では pandas の
  `rolling().mean()/.std()` による毎回のバッチ再計算で1秒未満のため、
  素朴なオンライン平均・分散アルゴリズムは実装していない
  （結果は同一、計算コストのみの違い）。
- **PCA（層3）**: scikit-learn等の追加ライブラリは使わず、numpyの固有値分解
  （`np.linalg.eigh`）で自前実装。共分散はEWMA（半減期60日、デフォルト）と
  単純ローリング250日を切替可能（`pca.estimate_axes(method=...)`）。
  軸の再推定は7日以上経過していれば実行（週次相当）、それ以外は保存済みの
  軸を使い回す。銘柄レベルPCAは必ずセクター/スタイルETFや指数を除いた
  構成銘柄のみで推定する（ETFを混ぜると誤ったPCA構造になるバグを実装中に
  発見・修正した）。セクターレベルPCAは自前集計ではなく実際のセクターETF
  価格から独立に計算する（個別銘柄データ取得が障害を起こした場合の
  フォールバックとして機能させるため）。
- **構造変化モニタ（層4）**: 短期軸(60日)・長期軸(250日)ともローリング窓
  （EWMAではなく単純共分散）で毎週末時点のデータのみを使って推定し直す
  （将来データを混入させない）。相関しきい値0.8は仕様書どおりPC1・PC2両方に
  同一値を適用しているが、実データで検証したところ **PC2の短期/長期相関は
  常時0.5前後まで下がることが多く、0.8を下回ることがほぼ常態化**していた
  （PC2はPC1より寄与率が小さく、60日窓では特に不安定なため）。フラグの
  「構造変化の疑い」は現状PC1側の変化を見る指標として運用し、PC2単独の
  閾値割れは参考情報にとどめるなど、しきい値の運用調整が必要（仕様書の
  未決事項にも明記されている点）。週次スナップショットは
  `data/structure_history_{market}.parquet` に差分保存し、初回のみ過去に
  遡って計算する（3年分で77週程度、数分で完了）。
- **データ品質（異常値検出）**: 実装検証中に、日本のETF（1306.T, 1629.T）で
  2026年3月末の2日間だけ価格が正常値の1/500近くまで落ち込む異常値
  （出来高も同時に異常値）を発見した。分割・配当調整の問題ではなくデータ
  フィード側の生データ異常だったため、`decompose.clean_bad_ticks()` で
  前後7日の中央値と比較して3倍以上乖離する短期スパイク（最大3日間）を
  検出し、前後の正常値から線形補間する処理をリターン計算前に追加した。
- **ニュース照合（層5）**: 2つの実装がある。
  1. `free_news_lookup.py`（**デフォルトで有効、APIキー不要**）: CNBC/WSJ/
     Yahoo Finance（米国）、Yahoo!ニュース/NHK（日本）の無料RSSフィードから
     見出しを取得し、論点のセクター名・関連銘柄の会社名とのキーワード一致で
     照合する。`gather_report_data()` から自動的に呼ばれ、`news_store`に
     見つからない論点だけを対象にする。意味理解のない単純な文字列一致のため
     精度は限定的（例: 2026-09-08は原油急騰・中東情勢というマクロ要因で
     日本株が下落したが、セクター名では引っかからず「要因不明」のままだった
     ケースを確認済み）。マッチした場合は要約文に「（自動キーワード一致・
     要確認）」と明記し、精度が低いことが分かるようにしている。
  2. `news_lookup_batch.py`（**任意、要APIキー**）: Anthropic API
     （`web_search`ツール）を呼び出す、より高精度な検索。
     `ANTHROPIC_API_KEY`をGitHub Secretsに設定すればActions上で自動実行され、
     free_news_lookup.pyより優先して使われる（news_storeに先に保存されるため）。
  検証のため、2026-09-04分の実際の論点（米国: Consumer Discretionaryセクター内
  分散、日本: Valueファクター・電力ガスセクター）についてはClaude Code自身の
  Web検索で実際のニュースを調べ、`news_store.py`のキャッシュに手動投入した上で
  レポートに正しく反映されることを確認済み（`data/news_cache.json`）。
  対応するニュースが見つからない論点は「要因不明」と表示される。

## ディレクトリ構成

```
daily-review/
  src/
    config.py            設定・定数（未決事項の初期値、米国・日本のETF/ティッカー定義）
    market_context.py     MarketContext: 米国/日本の切り替え（us_context() / jp_context()）
    universe.py            S&P500構成銘柄の取得・週次差分記録
    universe_jp.py          日経225構成銘柄の取得・週次差分記録・TSE17業種マッピング
    sector_weights.py      セクターウェイト（米: SPY保有構成 / 日: 構成銘柄数比率）
    data_layer.py            価格データの永続化・差分取得（フェーズ1、米国・日本共通）
    fundamentals.py          ファンダメンタルズ・スナップショット（週次、米国・日本共通）
    decompose.py              層1: リターン分解（米国・日本共通、異常値クレンジング含む）
    pca.py                     層3: PCA（軸推定・保存・日次射影・残差比率、米国・日本共通）
    zscore.py                   層2: 異常検知（層3のPC/残差比率も統合、米国・日本共通）
    structure_monitor.py         層4: 構造変化モニタ（週次スナップショット差分計算、月次サマリー）
    news_store.py                 層5: ニュース照合結果のローカルキャッシュ
    free_news_lookup.py            層5: 無料RSSキーワード一致（APIキー不要、デフォルト）
    run_daily.py                    日次更新の一括実行（価格取得→ニュース照合→レポート生成）
    news_lookup_batch.py           層5: ニュース照合の無人実行バッチ（Anthropic API、要APIキー）
    report.py                       日次コンソールレポート用データ取得（米国・日本共通）
    html_report.py                   静的HTMLレポート生成（米国・日本共通）
    html_structure.py                 構造ページの静的HTML生成（米国・日本共通）
    fetch_us_universe.py              米国初回一括取得スクリプト
    fetch_jp_universe.py               日本初回一括取得スクリプト
  data/                  永続化データ（parquet/json、gitignore対象）
  reports/               生成レポート・ログ（us/, jp/, structure/us/, structure/jp/）
```
