"""日経225構成銘柄ユニバースの管理（米国版 universe.py の日本版）。

Wikipedia日本語版の「日経平均株価」ページには、日経の業種区分（食品・繊維・
化学...のNikkei独自34分類）ごとに構成銘柄表がある。これをTOPIX-17（東証の
セクターETF: 1617〜1633）の17業種に集約してsector列とする（仕様書の
「東証33業種→17業種に集約」の簡易版。Nikkeiの分類とTSE公式33業種は完全一致
ではないため、本マッピングは近似である点に注意）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup

from config import JP_SECTOR_ETFS, JP_STYLE_ETFS, UNIVERSE_CURRENT_JP, UNIVERSE_STORE_JP

WIKI_URL_JP = "https://ja.wikipedia.org/wiki/%E6%97%A5%E7%B5%8C%E5%B9%B3%E5%9D%87%E6%A0%AA%E4%BE%A1"
HEADERS = {"User-Agent": "Mozilla/5.0 (daily-market-review research tool)"}

# Nikkei業種見出し（末尾の「（n銘柄）」を除いた部分） -> TOPIX-17業種（近似マッピング）
NIKKEI_TO_TSE17 = {
    "食品": "食品",
    "水産": "食品",
    "繊維": "素材・化学",
    "パルプ・紙": "素材・化学",
    "化学": "素材・化学",
    "ゴム": "素材・化学",
    "医薬品": "医薬品",
    "窯業": "建設・資材",
    "鉱業": "エネルギー資源",
    "石油": "エネルギー資源",
    "鉄鋼": "鉄鋼・非鉄",
    "非鉄・金属": "鉄鋼・非鉄",
    "機械": "機械",
    "造船": "機械",
    "電気機器": "電機・精密",
    "精密機器": "電機・精密",
    "自動車": "自動車・輸送機",
    "その他製造": "素材・化学",
    "建設": "建設・資材",
    "商社": "商社・卸売",
    "小売業": "小売",
    "銀行": "銀行",
    "証券": "金融（除く銀行）",
    "保険": "金融（除く銀行）",
    "その他金融": "金融（除く銀行）",
    "不動産": "不動産",
    "鉄道・バス": "運輸・物流",
    "陸運": "運輸・物流",
    "海運": "運輸・物流",
    "空運": "運輸・物流",
    "倉庫": "運輸・物流",
    "通信": "情報通信・サービスその他",
    "電力": "電力・ガス",
    "ガス": "電力・ガス",
    "サービス": "情報通信・サービスその他",
}


def fetch_nikkei225_constituents() -> pd.DataFrame:
    """Wikipedia日本語版から日経225構成銘柄・業種を取得する。

    戻り値の列: symbol(.T付き), name, nikkei_sector, sector(TSE17近似)
    """
    r = requests.get(WIKI_URL_JP, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "lxml")
    content = soup.select_one("#mw-content-text")

    current_heading = None
    rows = []
    for el in content.find_all(["h2", "h3", "h4", "table"]):
        if el.name in ("h2", "h3", "h4"):
            current_heading = el.get_text(strip=True)
        elif el.name == "table":
            if "wikitable" not in el.get("class", []):
                continue
            header_cells = [th.get_text(strip=True) for th in el.find_all("th")][:3]
            if "証券コード" not in header_cells:
                continue
            sector_name = current_heading.split("（")[0].split("(")[0].strip() if current_heading else "不明"
            for tr in el.find_all("tr")[1:]:
                tds = tr.find_all("td")
                if len(tds) < 2:
                    continue
                code = tds[0].get_text(strip=True)
                name = tds[1].get_text(strip=True)
                if not code:
                    continue
                rows.append({"symbol": f"{code}.T", "name": name, "nikkei_sector": sector_name})

    df = pd.DataFrame(rows).drop_duplicates(subset=["symbol"]).reset_index(drop=True)
    unmapped = sorted(set(df["nikkei_sector"]) - set(NIKKEI_TO_TSE17))
    if unmapped:
        print(f"  [warn] TSE17未マッピングのNikkei業種: {unmapped}（universe_jp.NIKKEI_TO_TSE17に追加してください）")
    df["sector"] = df["nikkei_sector"].map(NIKKEI_TO_TSE17).fillna("未分類")
    return df


def refresh_universe_jp() -> pd.DataFrame:
    new_df = fetch_nikkei225_constituents()
    now = datetime.now(timezone.utc).isoformat()

    old_symbols: set[str] = set()
    if UNIVERSE_CURRENT_JP.exists():
        old = json.loads(UNIVERSE_CURRENT_JP.read_text(encoding="utf-8"))
        old_symbols = set(old.get("symbols", []))

    new_symbols = set(new_df["symbol"])
    added = sorted(new_symbols - old_symbols)
    removed = sorted(old_symbols - new_symbols)

    if added or removed:
        events = [{"date": now, "symbol": s, "action": "added"} for s in added]
        events += [{"date": now, "symbol": s, "action": "removed"} for s in removed]
        events_df = pd.DataFrame(events)
        if UNIVERSE_STORE_JP.exists():
            history = pd.concat([pd.read_parquet(UNIVERSE_STORE_JP), events_df], ignore_index=True)
        else:
            history = events_df
        history.to_parquet(UNIVERSE_STORE_JP, index=False)

    UNIVERSE_CURRENT_JP.write_text(
        json.dumps({"updated_at": now, "symbols": sorted(new_symbols)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    new_df.to_json(UNIVERSE_CURRENT_JP.with_suffix(".detail.json"), orient="records", force_ascii=False, indent=2)
    return new_df


def load_current_universe_jp() -> pd.DataFrame:
    detail_path = UNIVERSE_CURRENT_JP.with_suffix(".detail.json")
    if detail_path.exists():
        return pd.read_json(detail_path)
    return refresh_universe_jp()


def full_ticker_list_jp() -> list[str]:
    from config import JP_INDEX_TICKER, JP_NIKKEI_ETF_PROXY, JP_TOPIX_PROXY

    constituents = load_current_universe_jp()["symbol"].tolist()
    etfs = list(JP_SECTOR_ETFS.keys()) + list(JP_STYLE_ETFS.keys())
    extras = [JP_INDEX_TICKER, JP_TOPIX_PROXY, JP_NIKKEI_ETF_PROXY]
    seen, result = set(), []
    for t in constituents + etfs + extras:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


if __name__ == "__main__":
    import console_utf8  # noqa: F401

    df = refresh_universe_jp()
    print(f"日経225構成銘柄: {len(df)}件")
    print(df["sector"].value_counts())
