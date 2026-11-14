"""JPX(日本取引所)の信用取引・投資部門別データを取得する。GitHub Actions で実行する。

    python insights/src/fetch_jpx.py <出力先> [前回の出力先]

出力:
- margin_stock_daily.parquet: 銘柄別信用取引残高(日次・全銘柄)。JPXのサイトには直近5営業日分しか
  ないので、前回の出力に今回分を足して履歴を伸ばす。
  列: date, code, name_en, sell_shs, buy_shs, sell_val, buy_val (株・円)
- margin_weekly.parquet: 信用取引現在高(週次、二市場・委託)。列: date, buy_shs, buy_val, sell_shs, sell_val
  (千株・百万円、制度+一般)。サイトに載っている週を全部読む。
- investor_weekly.parquet: 投資部門別売買状況(週次、二市場、金額・千円)。
  列: week_start, week_end, ind_cash_sell, ind_cash_buy, ind_margin_sell, ind_margin_buy, foreign_sell, foreign_buy
- jp_names.json: 証券コード → 社名・業種(東証の上場銘柄一覧)
"""

from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd

BASE = "https://www.jpx.co.jp"
UA = {"User-Agent": "Mozilla/5.0 (market-hp data fetch)"}
MARGIN_STOCK_PAGE = BASE + "/markets/statistics-equities/margin/01.html"
MARGIN_WEEKLY_PAGE = BASE + "/markets/statistics-equities/margin/04.html"
INVESTOR_PAGE = BASE + "/markets/statistics-equities/investor-type/index.html"
LISTED_PAGE = BASE + "/markets/statistics-equities/misc/01.html"


def get(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()


def links(page: str, pattern: str) -> list[str]:
    html = get(page).decode("latin-1")
    return [BASE + h if h.startswith("/") else h for h in dict.fromkeys(re.findall(rf'href="([^"]*{pattern})"', html))]


# ---------- 銘柄別信用取引残高(PDF) ----------

NUM = re.compile(r"^-?[\d,]+$")


def parse_numbers(rest: str) -> list[int | None]:
    """'400 ▲ 1,300 0.0% 78,600 ...' の並びを数値に。▲(文字化けしても非ASCII)は次の数をマイナスにする。"""
    out: list[int | None] = []
    neg = False
    for tok in rest.split():
        if NUM.match(tok):
            v = int(tok.replace(",", ""))
            out.append(-v if neg else v)
            neg = False
        elif tok.endswith("%") or tok in ("*", "-"):
            out.append(None)
        elif not tok.isascii():
            neg = True
    return out


ROW = re.compile(r"(?P<code>[0-9A-Z]{4}0)\s+JP[0-9A-Z]{10}\S*?\s*(?P<kind>Shs|Val)\.\s+(?P<rest>.+)$")


def parse_margin_pdf(data: bytes, date: str) -> pd.DataFrame:
    import pdfplumber

    rows: dict[str, dict] = {}
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            lines = (page.extract_text() or "").split("\n")
            for i, line in enumerate(lines):
                m = ROW.search(line)
                if not m:
                    continue
                nums = parse_numbers(m["rest"])
                # 並び: 売残, 前日比, 比率, 買残, 前日比, 比率, ...
                if len(nums) < 6 or nums[0] is None or nums[3] is None:
                    continue
                r = rows.setdefault(m["code"], {"date": date, "code": m["code"]})
                if m["kind"] == "Shs":
                    r["sell_shs"], r["buy_shs"] = nums[0], nums[3]
                else:
                    r["sell_val"], r["buy_val"] = nums[0], nums[3]
                    name = line[: line.find(m["code"])].strip()
                    name = re.sub(r"\s+(Prime|Standard|Growth|Investment trusts|Others?)\s*(Loan|Margin)?\s*$", "", name)
                    r["name_en"] = re.sub(r"(Loan|Margin)$", "", name).strip()
    return pd.DataFrame(rows.values())


def margin_stock(prev: pd.DataFrame | None) -> pd.DataFrame:
    have = set(prev["date"].astype(str)) if prev is not None and len(prev) else set()
    frames = [prev] if prev is not None and len(prev) else []
    for url in links(MARGIN_STOCK_PAGE, r"_mtall\.pdf"):
        d = re.search(r"/(\d{8})_mtall", url).group(1)
        date = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        if date in have:
            continue
        df = parse_margin_pdf(get(url), date)
        print(f"margin {date}: {len(df)} 銘柄", file=sys.stderr)
        if len(df) > 1000:
            frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["date"] = out["date"].astype(str)
    return out.drop_duplicates(["date", "code"], keep="last").sort_values(["date", "code"]).reset_index(drop=True)


# ---------- 信用取引現在高(週次 xlsx) ----------

def margin_weekly() -> pd.DataFrame:
    """2002年以降の週次(過去推移表 mtgk.xls の合計列)に、直近数週(mtcurrent.xlsx の合計行)を足す。"""
    recs = {}
    hist = links(BASE + "/markets/statistics-equities/margin/05.html", r"_mtgk\.xls")
    if hist:
        x = pd.read_excel(io.BytesIO(get(hist[0])), header=None)
        for i in range(len(x)):
            d = pd.to_datetime(str(x.iat[i, 0])[:10], errors="coerce")
            if pd.isna(d) or pd.isna(x.iat[i, 1]):
                continue
            recs[d.strftime("%Y-%m-%d")] = {"sell_shs": float(x.iat[i, 1]), "sell_val": float(x.iat[i, 2]),
                                            "buy_shs": float(x.iat[i, 3]), "buy_val": float(x.iat[i, 4])}
    # 過去推移表の直近分(mtgk.xls より新しい週。列13-16が合計の売残・買残)
    for url in links(BASE + "/markets/statistics-equities/margin/05.html", r"tvdivq\d+\.xlsx"):
        try:
            x = pd.read_excel(io.BytesIO(get(url)), header=None)
            for i in range(len(x)):
                d = pd.to_datetime(str(x.iat[i, 0])[:10], errors="coerce")
                if pd.isna(d) or pd.isna(x.iat[i, 13]):
                    continue
                recs[d.strftime("%Y-%m-%d")] = {"sell_shs": float(x.iat[i, 13]), "sell_val": float(x.iat[i, 14]),
                                                "buy_shs": float(x.iat[i, 15]), "buy_val": float(x.iat[i, 16])}
        except Exception as e:
            print(f"[warn] 過去推移表(直近): {e}", file=sys.stderr)
    for url in links(MARGIN_WEEKLY_PAGE, r"_mtcurrent\.xlsx"):
        d = re.search(r"/(\d{8})_mtcurrent", url).group(1)
        try:
            x = pd.read_excel(io.BytesIO(get(url)), header=None)
            row = next(i for i in range(len(x)) if str(x.iat[i, 1]).startswith("信用取引残高合計"))
            # 列4=売残(二市場), 列6=買残(二市場)。株数の行の次が金額の行
            recs[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = {
                "sell_shs": float(x.iat[row, 4]), "sell_val": float(x.iat[row + 1, 4]),
                "buy_shs": float(x.iat[row, 6]), "buy_val": float(x.iat[row + 1, 6]),
            }
        except Exception as e:  # 書式が変わった週は飛ばす
            print(f"[warn] mtcurrent {d}: {e}", file=sys.stderr)
    df = pd.DataFrame([{"date": k, **v} for k, v in recs.items()])
    return df.sort_values("date").reset_index(drop=True)


# ---------- 投資部門別売買状況(週次 xlsx) ----------

def investor_weekly() -> pd.DataFrame:
    recs = []
    urls = []
    for page in (INVESTOR_PAGE, BASE + "/markets/statistics-equities/investor-type/00-01.html",
                 BASE + "/markets/statistics-equities/investor-type/00-02.html"):
        try:
            urls += links(page, r"stock_1_w_\d{8}_\d{8}\.xlsx")
        except Exception as e:
            print(f"[warn] {page}: {e}", file=sys.stderr)
    for url in dict.fromkeys(urls):
        a, b = re.search(r"stock_1_w_(\d{8})_(\d{8})", url).groups()
        try:
            x = pd.read_excel(io.BytesIO(get(url)), header=None)
            row = next(i for i in range(len(x)) if str(x.iat[i, 1]).startswith("二市場")) + 1  # 金額の行
            # 0始まりの列: 個人 現金 11-14, 個人 信用 15-18, 海外投資家 19-22 (売, 買, 差引, 合計)
            recs.append({
                "week_start": f"{a[:4]}-{a[4:6]}-{a[6:]}", "week_end": f"{b[:4]}-{b[4:6]}-{b[6:]}",
                "ind_cash_sell": float(x.iat[row, 11]), "ind_cash_buy": float(x.iat[row, 12]),
                "ind_margin_sell": float(x.iat[row, 15]), "ind_margin_buy": float(x.iat[row, 16]),
                "foreign_sell": float(x.iat[row, 19]), "foreign_buy": float(x.iat[row, 20]),
            })
        except Exception as e:
            print(f"[warn] investor {a}: {e}", file=sys.stderr)
    return pd.DataFrame(recs).drop_duplicates("week_end").sort_values("week_end").reset_index(drop=True)


def listed_names() -> dict:
    url = next(iter(links(LISTED_PAGE, r"data_j\.xlsx?")), None)
    if not url:
        return {}
    x = pd.read_excel(io.BytesIO(get(url)))
    cols = {c: c for c in x.columns}
    code_c = next(c for c in cols if "コード" in str(c) and "業種" not in str(c))
    name_c = next(c for c in cols if "銘柄名" in str(c))
    sec_c = next((c for c in cols if "33業種区分" in str(c)), None)
    out = {}
    for _, r in x.iterrows():
        code = str(r[code_c]).strip()
        out[(code + "0") if len(code) == 4 else code] = {"name": str(r[name_c]), "sector": str(r[sec_c]) if sec_c else ""}
    return out


def merge_prev(df: pd.DataFrame, prev_dir: Path | None, name: str, key: str) -> pd.DataFrame:
    """JPXのサイトには直近分しか載らないものがあるので、前回の出力と合わせて履歴を伸ばす。"""
    p = prev_dir / name if prev_dir else None
    if p and p.exists():
        df = pd.concat([pd.read_parquet(p), df], ignore_index=True)
    return df.drop_duplicates(key, keep="last").sort_values(key).reset_index(drop=True)


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    prev_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    prev_path = prev_dir / "margin_stock_daily.parquet" if prev_dir else None
    prev = pd.read_parquet(prev_path) if prev_path and prev_path.exists() else None
    steps = {
        "margin_stock_daily.parquet": lambda: margin_stock(prev),
        "margin_weekly.parquet": lambda: merge_prev(margin_weekly(), prev_dir, "margin_weekly.parquet", "date"),
        "investor_weekly.parquet": lambda: merge_prev(investor_weekly(), prev_dir, "investor_weekly.parquet", "week_end"),
    }
    for name, fn in steps.items():
        try:
            df = fn()
            df.to_parquet(out / name, compression="zstd", index=False)
            print(f"{name}: {len(df)} rows", file=sys.stderr)
        except Exception as e:
            print(f"[warn] {name}: {e}", file=sys.stderr)
            old = prev_dir / name if prev_dir else None
            if old and old.exists():  # 失敗したら前回分をそのまま残す
                (out / name).write_bytes(old.read_bytes())
    try:
        (out / "jp_names.json").write_text(json.dumps(listed_names(), ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[warn] names: {e}", file=sys.stderr)
        old = prev_dir / "jp_names.json" if prev_dir else None
        if old and old.exists():
            (out / "jp_names.json").write_bytes(old.read_bytes())


if __name__ == "__main__":
    main()
