"""信用取引の需給レポートを作る。GitHub Actions で fetch_jpx.py の後に実行する(株価取得に yfinance を使う)。

    python insights/src/margin_report.py <market-data ディレクトリ>

出力: <dir>/margin_report.json
- total: 二市場の信用買い残・売り残(週次、金額)、信用倍率、前週比、4週・52週変化、2002年以降の分位、3年分の推移
- individuals: 投資部門別の個人の現金・信用の売買(週次)。個人売買に占める信用の比率、信用の差引
- top: 信用買い残(金額)の上位銘柄。売り残、信用倍率、前日比・5日比、推定平均取得単価と評価損益率
- notes: 推定方法の説明

評価損益率は推定値。銘柄別の信用買い残は日次の履歴が20営業日以上あれば、買い残の増加分をその日の終値で
取得したとみなして平均単価を更新する(減少分は平均単価のまま返済)。履歴が短い間は、直近60営業日の
売買代金加重平均価格(VWAP)を平均取得単価とみなす。制度信用の期限(6か月)以前の建玉や、
日中の約定価格の違いは反映できない。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

TOP_N = 10


def yf_ticker(code: str) -> str:
    return code[:4] + ".T"


def total_section(w: pd.DataFrame) -> dict:
    w = w.sort_values("date").reset_index(drop=True)
    w["ratio"] = w["buy_val"] / w["sell_val"]
    last = w.iloc[-1]

    def chg(n):
        if len(w) <= n:
            return None
        return round((last["buy_val"] / w.iloc[-1 - n]["buy_val"] - 1) * 100, 2)

    pct = round((w["buy_val"] <= last["buy_val"]).mean() * 100, 1)
    recent = w[w["date"] >= (pd.to_datetime(last["date"]) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")]
    peak = w.loc[w["buy_val"].idxmax()]
    return {
        "date": last["date"],
        "buy_val_oku": round(last["buy_val"] / 100, 0),     # 百万円 → 億円
        "sell_val_oku": round(last["sell_val"] / 100, 0),
        "ratio": round(float(last["ratio"]), 2),
        "buy_chg_1w_pct": chg(1), "buy_chg_4w_pct": chg(4), "buy_chg_52w_pct": chg(52),
        "buy_percentile_since_2002": pct,
        "buy_peak": {"date": peak["date"], "buy_val_oku": round(peak["buy_val"] / 100, 0)},
        "series_buy_oku": [[r.date, round(r.buy_val / 100, 0)] for r in recent.itertuples()],
        "series_ratio": [[r.date, round(r.ratio, 2)] for r in recent.itertuples()],
    }


def individuals_section(inv: pd.DataFrame) -> dict:
    if inv is None or inv.empty:
        return {}
    inv = inv.sort_values("week_end").copy()
    cash = inv["ind_cash_sell"] + inv["ind_cash_buy"]
    marg = inv["ind_margin_sell"] + inv["ind_margin_buy"]
    inv["margin_share_pct"] = marg / (cash + marg) * 100
    inv["margin_net_oku"] = (inv["ind_margin_buy"] - inv["ind_margin_sell"]) / 1e5  # 千円 → 億円
    inv["cash_net_oku"] = (inv["ind_cash_buy"] - inv["ind_cash_sell"]) / 1e5
    inv["foreign_net_oku"] = (inv["foreign_buy"] - inv["foreign_sell"]) / 1e5
    rows = [
        {"week": f"{r.week_start}〜{r.week_end[5:]}", "margin_share_pct": round(r.margin_share_pct, 1),
         "margin_net_oku": round(r.margin_net_oku, 0), "cash_net_oku": round(r.cash_net_oku, 0),
         "foreign_net_oku": round(r.foreign_net_oku, 0)}
        for r in inv.tail(12).itertuples()
    ]
    return {"weeks": rows[::-1], "n_weeks_history": int(len(inv))}


def est_cost(hist: pd.DataFrame, px: pd.DataFrame) -> tuple[float | None, str]:
    """hist: date, buy_shs (日次)。px: Close, Volume (日次)。"""
    px = px.dropna(subset=["Close"])
    if px.empty:
        return None, ""
    tail = px.tail(60)
    vwap = float((tail["Close"] * tail["Volume"]).sum() / tail["Volume"].sum()) if tail["Volume"].sum() else float(tail["Close"].mean())
    h = hist.dropna(subset=["buy_shs"]).sort_values("date")
    if len(h) < 20:
        return vwap, "60日VWAP"
    closes = px["Close"].copy()
    closes.index = closes.index.strftime("%Y-%m-%d")
    first = h.iloc[0]
    start_px = px[px.index.strftime("%Y-%m-%d") < first["date"]].tail(60)
    cost = float((start_px["Close"] * start_px["Volume"]).sum() / start_px["Volume"].sum()) if len(start_px) and start_px["Volume"].sum() else vwap
    shs = float(first["buy_shs"])
    for r in h.iloc[1:].itertuples():
        add = r.buy_shs - shs
        if add > 0 and r.date in closes.index:
            cost = (cost * shs + float(closes[r.date]) * add) / (shs + add)
        shs = float(r.buy_shs)
    return cost, f"買い残の増減から推定({len(h)}営業日)"


def top_section(ms: pd.DataFrame, names: dict) -> list[dict]:
    import yfinance as yf

    ms = ms.copy()
    ms["date"] = ms["date"].astype(str)
    dates = sorted(ms["date"].unique())
    last = dates[-1]
    cur = ms[ms["date"] == last]
    # ETF・投信(コードが1xxx/2xxxの一部)は除いて個別株だけにする
    cur = cur[cur["code"].map(lambda c: c in names and "ETF" not in names[c].get("sector", "") and names[c].get("sector") not in ("", "-", "nan"))]
    top = cur.sort_values("buy_val", ascending=False).head(TOP_N)
    tickers = [yf_ticker(c) for c in top["code"]]
    px_all = yf.download(tickers, period="2y", auto_adjust=False, group_by="ticker", progress=False, threads=True)
    out = []
    for r in top.itertuples():
        hist = ms[ms["code"] == r.code][["date", "buy_shs", "sell_shs", "buy_val"]].sort_values("date")

        def ago(n):
            return hist.iloc[-1 - n] if len(hist) > n else None

        d1, d5 = ago(1), ago(5)
        t = yf_ticker(r.code)
        try:
            px = px_all[t] if isinstance(px_all.columns, pd.MultiIndex) else px_all
        except KeyError:
            px = pd.DataFrame()
        cost, method = est_cost(hist, px) if not px.empty else (None, "")
        close = float(px["Close"].dropna().iloc[-1]) if not px.empty and px["Close"].notna().any() else None
        out.append({
            "code": r.code[:4], "name": names.get(r.code, {}).get("name", r.name_en), "sector": names.get(r.code, {}).get("sector", ""),
            "buy_val_oku": round(r.buy_val / 1e8, 1), "buy_shs_k": round(r.buy_shs / 1e3, 0) if r.buy_shs == r.buy_shs else None,
            "sell_shs_k": round(r.sell_shs / 1e3, 0) if r.sell_shs == r.sell_shs else None,
            "ratio": round(r.buy_shs / r.sell_shs, 1) if r.sell_shs and r.sell_shs == r.sell_shs else None,
            "buy_chg_1d_pct": round((r.buy_shs / d1.buy_shs - 1) * 100, 1) if d1 is not None and d1.buy_shs else None,
            "buy_chg_5d_pct": round((r.buy_shs / d5.buy_shs - 1) * 100, 1) if d5 is not None and d5.buy_shs else None,
            "close": round(close, 1) if close else None, "est_cost": round(cost, 1) if cost else None,
            "est_pnl_pct": round((close / cost - 1) * 100, 1) if close and cost else None, "method": method,
        })
    return out


def main():
    d = Path(sys.argv[1])
    names = json.loads((d / "jp_names.json").read_text(encoding="utf-8")) if (d / "jp_names.json").exists() else {}
    rep = {"notes": __doc__.split("評価損益率は推定値。")[1].strip().replace("\n", "")}
    try:
        rep["total"] = total_section(pd.read_parquet(d / "margin_weekly.parquet"))
    except Exception as e:
        print(f"[warn] total: {e}", file=sys.stderr)
    try:
        rep["individuals"] = individuals_section(pd.read_parquet(d / "investor_weekly.parquet"))
    except Exception as e:
        print(f"[warn] individuals: {e}", file=sys.stderr)
    try:
        ms = pd.read_parquet(d / "margin_stock_daily.parquet")
        rep["stock_date"] = str(ms["date"].max())
        rep["stock_history_days"] = int(ms["date"].nunique())
        rep["top"] = top_section(ms, names)
    except Exception as e:
        print(f"[warn] top: {e}", file=sys.stderr)
    (d / "margin_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "total"} | {"total": {k: v for k, v in rep.get("total", {}).items() if not k.startswith("series")}},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
