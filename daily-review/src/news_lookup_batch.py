"""層5: ニュース照合の無人実行バッチ（SPEC_1.md「Claude API + web search」）。

layer2（+layer3/4）で抽出された本日の論点ごとに、Anthropic API の
web_search ツールで裏付けニュースを検索し、要約と出典URLを news_store に
保存する。日次バッチの最後（report.py / html_report.py の前）に実行する想定。

前提: 環境変数 ANTHROPIC_API_KEY が設定されていること。
このリポジトリ内の対話環境（Claude Code）ではAPIキーを保持していないため、
このスクリプト自体はここでは実行確認していない。ロジックは
https://docs.anthropic.com/ の Web search tool 仕様に基づく。
"""

from __future__ import annotations

import os
import sys

import pandas as pd

from decompose import run_layer1
from market_context import MarketContext
from news_store import load_news, save_news
from pca import run_layer3
from zscore import run_layer2

MODEL = "claude-sonnet-5"
MAX_SEARCHES_PER_RUN = 8  # コスト・レート制御のため1回のバッチで検索する論点数の上限


def _build_query(ctx: MarketContext, date: pd.Timestamp, metric: str) -> str:
    label = metric.split(":", 1)[-1].replace("_", " ")
    date_str = date.strftime("%Y年%m月%d日") if ctx.name == "jp" else date.strftime("%Y-%m-%d")
    market_kw = "日本株 東京市場" if ctx.name == "jp" else "US stock market"
    return f"{date_str} {market_kw} {label} なぜ 材料 ニュース"


def _search_one(client, ctx: MarketContext, date: pd.Timestamp, metric: str) -> dict | None:
    query = _build_query(ctx, date, metric)
    prompt = (
        f"次のクエリでWeb検索し、{ctx.label}市場で{date.strftime('%Y-%m-%d')}に起きた、"
        f"「{metric}」という観点に関連する材料・ニュースを2〜3文で要約してください。"
        f"見つからなければ「不明」とだけ答えてください。検索クエリ: {query}"
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        messages=[{"role": "user", "content": prompt}],
    )

    summary_parts = []
    sources = []
    for block in resp.content:
        if block.type == "text":
            summary_parts.append(block.text)
        if block.type == "web_search_tool_result":
            for item in getattr(block, "content", []) or []:
                if getattr(item, "type", None) == "web_search_result":
                    sources.append({"title": item.title, "url": item.url})

    summary = "".join(summary_parts).strip()
    if not summary or "不明" in summary[:10]:
        return None
    return {"summary": summary, "sources": sources[:5]}


def run_news_lookup(ctx: MarketContext, target_date: pd.Timestamp | None = None) -> int:
    """本日の論点を抽出し、未検索のものだけ検索して保存する。戻り値: 新規保存件数。"""
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError("pip install anthropic が必要です") from e

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("環境変数 ANTHROPIC_API_KEY が設定されていません")

    client = anthropic.Anthropic(api_key=api_key)

    l1 = run_layer1(ctx)
    l3 = run_layer3(ctx, l1.returns)
    l2 = run_layer2(ctx, l1, l3)
    date = target_date or l1.index_ret.dropna().index[-1]
    tp = l2.talking_points(date, top_n=MAX_SEARCHES_PER_RUN)

    saved = 0
    for metric in tp["metric"]:
        if load_news(ctx.name, date, metric) is not None:
            continue  # 既に検索済み（再検索しない）
        result = _search_one(client, ctx, date, metric)
        if result is not None:
            save_news(ctx.name, date, metric, result["summary"], result["sources"])
            saved += 1
    return saved


def run_weekly_structure_news_lookup(ctx: MarketContext) -> int:
    """構造変化フラグが立った直近週があれば、その週についてもニュース照合を行う。"""
    from structure_monitor import _history_path

    path = _history_path(ctx)
    if not path.exists():
        return 0
    history = pd.read_parquet(path)
    if history.empty or not bool(history.iloc[-1]["structure_change_flag"]):
        return 0

    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError("pip install anthropic が必要です") from e
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("環境変数 ANTHROPIC_API_KEY が設定されていません")
    client = anthropic.Anthropic(api_key=api_key)

    week_ending = pd.Timestamp(history.iloc[-1]["week_ending"])
    metric = "structure:weekly_change"
    if load_news(ctx.name, week_ending, metric) is not None:
        return 0
    result = _search_one(client, ctx, week_ending, "市場構造の変化（主導するセクター・テーマの交代）")
    if result is not None:
        save_news(ctx.name, week_ending, metric, result["summary"], result["sources"])
        return 1
    return 0


if __name__ == "__main__":
    import console_utf8  # noqa: F401
    from market_context import jp_context, us_context

    ctx = jp_context() if "--jp" in sys.argv else us_context()
    n = run_news_lookup(ctx)
    print(f"新規に{n}件のニュース照合結果を保存しました。")
