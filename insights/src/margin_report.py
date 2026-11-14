"""信用取引の需給レポートを作る。GitHub Actions で fetch_jpx.py の後に実行する(株価取得に yfinance を使う)。

    python insights/src/margin_report.py <market-data ディレクトリ>

出力: <dir>/margin_report.json
- total: 二市場の信用買い残・売り残(週次、金額)、信用倍率、前週比、4週・52週変化、2002年以降の分位、3年分の推移
- individuals: 投資部門別の個人の現金・信用の売買(週次)。個人売買に占める信用の比率、信用の差引
- top: 信用買い残(金額)の上位銘柄。売り残、信用倍率、前日比・5日比、推定平均取得単価と評価損益率
- notes: 推定方法の説明

評価損益率は推定値。取得単価は JPX が公表する銘柄別の買残金額(約定価額ベース)を買残株数で割った値で、
制度信用と一般信用を合わせた買い建玉全体の平均取得単価にあたる。評価には最新の終値を使う。手数料・金利・貸株料は含まない。
上位100銘柄の合計(top_agg)は、その100銘柄の買い建玉を時価で評価した額と取得額の差。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

TOP_N = 10
AGG_N = 100   # 評価損益の合計を出す銘柄数


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


def top_section(ms: pd.DataFrame, names: dict) -> tuple[list[dict], dict]:
    import yfinance as yf

    ms = ms.copy()
    ms["date"] = ms["date"].astype(str)
    last = ms["date"].max()
    cur = ms[ms["date"] == last]
    # ETF・投信など(業種のないもの)を除いて個別株だけにする
    cur = cur[cur["code"].map(lambda c: c in names and names[c].get("sector") not in (None, "", "-", "nan")
                               and "ETF" not in names[c].get("sector", ""))]
    cur = cur[(cur["buy_shs"] > 0) & cur["buy_val"].notna()]
    top = cur.sort_values("buy_val", ascending=False).head(AGG_N)
    tickers = [yf_ticker(c) for c in top["code"]]
    px_all = yf.download(tickers, period="5d", auto_adjust=False, group_by="ticker", progress=False, threads=True)

    def last_close(t):
        try:
            s = (px_all[t] if isinstance(px_all.columns, pd.MultiIndex) else px_all)["Close"].dropna()
            return float(s.iloc[-1]) if len(s) else None
        except KeyError:
            return None

    out, cost_sum, mkt_sum, n_ok = [], 0.0, 0.0, 0
    for i, r in enumerate(top.itertuples()):
        cost = r.buy_val / r.buy_shs
        close = last_close(yf_ticker(r.code))
        if close:
            cost_sum += r.buy_val
            mkt_sum += close * r.buy_shs
            n_ok += 1
        if i >= TOP_N:
            continue
        hist = ms[ms["code"] == r.code].sort_values("date")

        def ago(n):
            return hist.iloc[-1 - n] if len(hist) > n else None

        d1, d5 = ago(1), ago(5)
        out.append({
            "code": r.code[:4], "name": names.get(r.code, {}).get("name", r.name_en), "sector": names.get(r.code, {}).get("sector", ""),
            "buy_val_oku": round(r.buy_val / 1e8, 1), "buy_shs_k": round(r.buy_shs / 1e3, 0),
            "sell_shs_k": round(r.sell_shs / 1e3, 0) if r.sell_shs == r.sell_shs else None,
            "ratio": round(r.buy_shs / r.sell_shs, 1) if r.sell_shs and r.sell_shs == r.sell_shs else None,
            "buy_chg_1d_pct": round((r.buy_shs / d1.buy_shs - 1) * 100, 1) if d1 is not None and d1.buy_shs else None,
            "buy_chg_5d_pct": round((r.buy_shs / d5.buy_shs - 1) * 100, 1) if d5 is not None and d5.buy_shs else None,
            "close": round(close, 1) if close else None, "est_cost": round(cost, 1),
            "est_pnl_pct": round((close / cost - 1) * 100, 1) if close else None,
        })
    agg = {}
    if n_ok:
        all_buy = float(cur["buy_val"].sum())
        agg = {"n": n_ok, "cost_oku": round(cost_sum / 1e8, 0), "mkt_oku": round(mkt_sum / 1e8, 0),
               "pnl_oku": round((mkt_sum - cost_sum) / 1e8, 0), "pnl_pct": round((mkt_sum / cost_sum - 1) * 100, 1),
               "share_of_stock_buy_pct": round(cost_sum / all_buy * 100, 1) if all_buy else None}
    return out, agg


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
        rep["top"], rep["top_agg"] = top_section(ms, names)
    except Exception as e:
        print(f"[warn] top: {e}", file=sys.stderr)
    (d / "margin_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "total"} | {"total": {k: v for k, v in rep.get("total", {}).items() if not k.startswith("series")}},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
