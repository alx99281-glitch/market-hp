"""日次更新の一括実行スクリプト。

これまでreport.py / html_report.pyは「ストック済みの価格データ」を読むだけで、
新しい当日分を取得する処理を呼んでいなかった（daily_update()が未接続だった）。
このスクリプトが本来の「毎日引け後に実行するバッチ」の入口になる。

実行内容（米国・日本それぞれ）:
  1. 価格データの差分取得（当日分を追記。既存データは再取得しない）
  2. ニュース照合（ANTHROPIC_API_KEYが設定されていれば実行、無ければスキップ）
  3. コンソールレポート表示
  4. 静的HTMLレポート生成（reports/{market}/latest.html 等）
  5. 構造ページ（層4）も差分更新して再生成（週次データだが、生成自体は軽いので毎回実行してよい）

使い方:
  python run_daily.py         # 米国のみ
  python run_daily.py --jp    # 日本のみ
  python run_daily.py --all   # 米国・日本両方
"""

from __future__ import annotations

import os
import sys

import console_utf8  # noqa: F401
from html_report import write_report
from html_structure import write_structure_page
from market_context import MarketContext, jp_context, us_context
from report import print_daily_report
from universe import full_ticker_list as full_ticker_list_us
from universe_jp import full_ticker_list_jp


def run_for_market(ctx: MarketContext) -> None:
    print(f"\n{'=' * 70}\n{ctx.label}版 日次更新を開始します\n{'=' * 70}")

    tickers = full_ticker_list_us() if ctx.name == "us" else full_ticker_list_jp()
    new_rows = ctx.price_store.daily_update(tickers)
    print(f"価格データ差分取得: {len(new_rows)}行を追加")

    if os.environ.get("ANTHROPIC_API_KEY"):
        from news_lookup_batch import run_news_lookup, run_weekly_structure_news_lookup

        try:
            n = run_news_lookup(ctx)
            print(f"ニュース照合: {n}件を新規保存")
            n2 = run_weekly_structure_news_lookup(ctx)
            if n2:
                print(f"構造変化の週次ニュース照合: {n2}件を新規保存")
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] ニュース照合をスキップしました: {e}")
    else:
        print("ANTHROPIC_API_KEY未設定のため、ニュース照合はスキップします")

    print_daily_report(ctx)

    html_path = write_report(ctx)
    print(f"\nHTMLレポート生成: {html_path}")

    structure_path = write_structure_page(ctx)
    print(f"構造ページ更新: {structure_path}")


def update_macro_data() -> None:
    """USDJPY・米金利・原油（PCAの解釈やマクロ相関に使う）を差分更新する。"""
    from macro import daily_update_macro, fetch_macro_data, macro_store

    if not macro_store().load().shape[0]:
        fetch_macro_data()
    else:
        n = daily_update_macro()
        print(f"マクロデータ差分取得: {len(n)}行を追加")


if __name__ == "__main__":
    update_macro_data()

    if "--all" in sys.argv:
        run_for_market(us_context())
        run_for_market(jp_context())
    elif "--jp" in sys.argv:
        run_for_market(jp_context())
    else:
        run_for_market(us_context())

    print("\n完了。市場データを公開するには、リポジトリのルートで以下を実行してください:")
    print("  git add -A && git commit -m \"日次更新\" && git push")
