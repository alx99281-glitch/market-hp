"""層5: 無料RSSフィードによるニュース照合（Anthropic APIキー不要版）。

Claude API + web検索（news_lookup_batch.py）の代替。無料の公開RSSフィード
の見出しをキーワード一致でマッチングする。API検索と違い意味理解はできず、
単純な文字列一致のため精度は落ちるが、料金は完全にゼロで追加設定も不要。

RSSフィードは直近の記事しか含まれないため、「引け後すぐに実行し、その日の
見出しと照合する」用途にのみ有効（過去日への遡及照合はできない）。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (daily-market-review research tool)"}

FEEDS_US = [
    ("CNBC Economy", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("CNBC Markets", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
    ("WSJ Markets", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
]

FEEDS_JP = [
    ("Yahoo!ニュース 経済", "https://news.yahoo.co.jp/rss/topics/business.xml"),
    ("NHK 経済", "https://www3.nhk.or.jp/rss/news/cat5.xml"),
]


def fetch_feed_items(url: str, timeout: int = 15) -> list[dict]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] RSS取得失敗 {url}: {e}")
        return []
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title and link:
            items.append({"title": title, "url": link})
    return items


def fetch_all(market: str) -> list[dict]:
    """指定市場向けの全フィードから見出しを集約する（フィード名を出典タイトルに含める）。"""
    feeds = FEEDS_US if market == "us" else FEEDS_JP
    all_items = []
    for feed_name, url in feeds:
        for item in fetch_feed_items(url):
            all_items.append({"title": item["title"], "url": item["url"], "source": feed_name})
    return all_items


def match_keywords(items: list[dict], keywords: list[str], max_results: int = 3) -> list[dict]:
    """見出しにkeywordsのいずれかが含まれる記事を返す（単純な部分文字列一致）。"""
    keywords = [k for k in keywords if k and len(k) >= 2]
    if not keywords:
        return []
    matched = []
    seen_urls = set()
    for item in items:
        title_lower = item["title"].lower()
        if any(kw.lower() in title_lower for kw in keywords) and item["url"] not in seen_urls:
            matched.append(item)
            seen_urls.add(item["url"])
        if len(matched) >= max_results:
            break
    return matched
