"""各委員の公式略歴ページから、本人の顔写真URLを抽出してmembers.jsonに追記する。

画像は公式サイト(federalreserve.gov / boj.or.jp)から直接埋め込み(ホットリンク)で
表示する。ダウンロード・再配布はしない（著作権リスクを避けるため、常に一次情報源
から直接読み込む形にする）。
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "members.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (research tool; contact: local use)"}

# 除外するUIアイコン等（本人写真ではないもの）
EXCLUDE_PATTERNS = [
    "social-media", "USAGov", "OpenGov", "common2", "logo", "menu.png",
    "close.png", "search.gif", "page_top", "sns_",
]


def extract_photo_url(bio_url: str) -> str | None:
    try:
        r = requests.get(bio_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] 取得失敗 {bio_url}: {e}")
        return None

    candidates = re.findall(r'src="([^"]+\.(?:jpg|jpeg|png|JPG))"', r.text)
    for c in candidates:
        if any(p in c for p in EXCLUDE_PATTERNS):
            continue
        return c if c.startswith("http") else urljoin(bio_url, c)
    return None


def main() -> None:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    for bank_key in ("frb", "boj"):
        for member in data[bank_key]:
            url = extract_photo_url(member["bio_url"])
            member["photo_url"] = url
            print(f"{member['name_ja']:12s} -> {url}")
            time.sleep(0.5)

    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("保存しました。")


if __name__ == "__main__":
    main()
