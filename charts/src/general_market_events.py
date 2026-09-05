"""中央銀行イベント以外の主要な市場材料（代表例のみ、全期間網羅ではない）。

本来は仕様書どおりClaude API + web検索で日次バッチ的に全営業日を埋めるべき
だが、この環境ではAPIキーを使った無人実行ができないため、確度の高い
既知の大型イベントを手動でシードしている。将来的に daily-review 側の
news_lookup_batch.py と同じ仕組みで日次拡充する想定（central_bank_events.py
と同じJSON形式で追記していけばチャート側にそのまま反映される）。
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

EVENTS = [
    ("2018-02-05", "US", "「Volmageddon」。インフレ懸念による金利上昇を背景にVIX関連ETN(XIV)が破綻的急落、ダウ平均は一時1,600ドル超下落"),
    ("2018-12-24", "US", "クリスマスイブの急落。FRBの利上げ継続姿勢と政府機関閉鎖懸念で S&P500がこの弱気相場の安値を記録"),
    ("2020-02-24", "US", "新型コロナウイルスの世界的感染拡大懸念で株式市場が急落開始"),
    ("2020-03-09", "US", "サウジ・ロシアの原油価格戦争と新型コロナ懸念でNY株式市場がサーキットブレーカー発動"),
    ("2020-03-16", "US", "新型コロナ対応の金融政策にもかかわらずダウ平均が過去最大の下げ幅を記録"),
    ("2020-03-23", "US", "新型コロナショックの株価底値（この後、金融緩和を背景に反発相場入り）"),
    ("2020-11-09", "US", "ファイザー社が新型コロナワクチンの高い有効性を発表、景気敏感株・バリュー株が急伸"),
    ("2023-03-10", "US", "シリコンバレー銀行(SVB)が経営破綻、地銀不安が金融市場に波及"),
    ("2024-08-02", "US", "米雇用統計の下振れで景気後退懸念が強まり、世界同時株安の引き金に"),
    ("2024-08-05", "JP", "円キャリートレードの巻き戻しと米景気後退懸念により日経平均が一日で12.4%急落（過去最大の下げ幅）"),
    ("2025-01-27", "US", "中国発の低コストAIモデル「DeepSeek」の登場で米AI関連・半導体株が急落（NVIDIAは1日で過去最大の時価総額減少）"),
]


def build_events() -> list[dict]:
    return [{"date": d, "region": r, "detail": detail} for d, r, detail in EVENTS]


if __name__ == "__main__":
    events = build_events()
    out_path = DATA_DIR / "general_market_events.json"
    out_path.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(events)}件の一般市場イベントを保存しました -> {out_path}")
