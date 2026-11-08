"""分析の視点 2026-11-08 号の検証スクリプト。

データ: /tmp/market-data (GitHub Actions が Yahoo Finance から取得), daily-review/data。
結果: insights/data/analysis/2026-11-08.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MD = Path("/tmp/market-data")
OUT = ROOT / "insights/data/analysis/2026-11-08.json"

d = pd.read_parquet(MD / "daily.parquet")
d["date"] = pd.to_datetime(d["date"])
px = d.pivot(index="date", columns="ticker", values="close").sort_index()
op = d.pivot(index="date", columns="ticker", values="open").sort_index()
vol = d.pivot(index="date", columns="ticker", values="volume").sort_index()
intra = pd.read_parquet(MD / "intraday_60m.parquet")
intra["date"] = pd.to_datetime(intra["date"], utc=True)
jp = pd.read_parquet(ROOT / "daily-review/data/prices_jp.parquet")
jp["date"] = pd.to_datetime(jp["date"])
jpc = jp.pivot(index="date", columns="ticker", values="close").sort_index()
us = pd.read_parquet(ROOT / "daily-review/data/prices.parquet")
us["date"] = pd.to_datetime(us["date"])
usc = us.pivot(index="date", columns="ticker", values="close").sort_index()

res = {}
T = pd.Timestamp("2026-11-06")


def r(x, n=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def dedup(dates, gap=20, index=None):
    out, last = [], None
    for dt in dates:
        i = index.get_loc(dt)
        if last is None or i - last > gap:
            out.append(dt)
            last = i
    return out


def fwd(series, dates, hs=(1, 5, 20, 60)):
    s = series.dropna()
    rows = []
    for dt in dates:
        i = s.index.get_loc(dt)
        row = {"date": dt.strftime("%Y-%m-%d"), "ret": r(s.iloc[i] / s.iloc[i - 1] * 100 - 100)}
        hi = s.iloc[max(0, i - 250): i + 1].max()
        row["dd_from_250d_high"] = r(s.iloc[i] / hi * 100 - 100, 1)
        for h in hs:
            row[f"f{h}"] = r(s.iloc[i + h] / s.iloc[i] * 100 - 100) if i + h < len(s) else None
        rows.append(row)
    return rows


def summ(rows, hs=(1, 5, 20, 60)):
    out = {}
    for h in hs:
        v = [x[f"f{h}"] for x in rows if x[f"f{h}"] is not None]
        if v:
            out[f"f{h}"] = {"n": len(v), "mean": r(np.mean(v)), "median": r(np.median(v)),
                            "up_pct": r(np.mean(np.array(v) > 0) * 100, 0)}
    return out


# ---------------------------------------------------------------- 1. 東京 11/6: 全面安の中身
n225 = px["^N225"].dropna()
rets_jp = jpc.pct_change(fill_method=None) * 100
stocks = [c for c in jpc.columns if c.endswith(".T") and not c.startswith(("13", "16"))]
semis = [c for c in ["8035.T", "6857.T", "6920.T", "6146.T", "4062.T", "285A.T", "7735.T", "6723.T", "6526.T", "3436.T"] if c in jpc.columns]
day = {}
for dt in ["2026-11-04", "2026-11-05", "2026-11-06"]:
    x = rets_jp.loc[dt, stocks].dropna()
    xs = rets_jp.loc[dt, semis].dropna()
    rest = x.drop(xs.index, errors="ignore")
    day[dt] = {"n": int(len(x)), "down_pct": r((x < 0).mean() * 100, 1), "median": r(x.median()),
               "semis_median": r(xs.median()), "rest_median": r(rest.median()),
               "xs_std": r(x.std()), "nikkei": r(rets_jp.loc[dt, "^N225"]),
               "topix_etf_1306": r(rets_jp.loc[dt, "1306.T"])}
res["tokyo_breadth"] = day
sec = [c for c in jpc.columns if c.startswith("16") and c not in ("1605.T",)]
res["tokyo_sector_etf_1106"] = {c: r(rets_jp.loc[T, c]) for c in sorted(sec)}
res["tokyo_sector_etf_1105"] = {c: r(rets_jp.loc["2026-11-05", c]) for c in sorted(sec)}

# 履歴(3年): 225銘柄の下落比率と横断的なばらつき
hist = pd.DataFrame({"down_pct": (rets_jp[stocks] < 0).mean(axis=1) * 100,
                     "xs_std": rets_jp[stocks].std(axis=1),
                     "nk": rets_jp["^N225"],
                     "cnt": rets_jp[stocks].notna().sum(axis=1)})
hist = hist[hist.cnt > 200]
big = hist[(hist.nk <= -3.5)]
big_rows = []
for dt, row in big.iterrows():
    i = n225.index.get_loc(dt) if dt in n225.index else None
    f5 = r(n225.iloc[i + 5] / n225.iloc[i] * 100 - 100) if i is not None and i + 5 < len(n225) else None
    f20 = r(n225.iloc[i + 20] / n225.iloc[i] * 100 - 100) if i is not None and i + 20 < len(n225) else None
    big_rows.append({"date": dt.strftime("%Y-%m-%d"), "nk": r(row.nk), "down_pct": r(row.down_pct, 1),
                     "xs_std": r(row.xs_std), "f5": f5, "f20": f20})
res["tokyo_big_down_days_3y"] = big_rows
res["tokyo_xs_std_pctile_1106"] = r((hist.xs_std < hist.loc[T, "xs_std"]).mean() * 100, 1)
res["tokyo_down_pct_rank_1106"] = int((hist.down_pct >= hist.loc[T, "down_pct"]).sum())
res["tokyo_hist_days"] = int(len(hist))

# 日中: 1321 / 1306 の寄り付きギャップと日中変化
def intraday_day(tk, dstr):
    x = intra[intra.ticker == tk].copy()
    x["d"] = x.date.dt.tz_convert("Asia/Tokyo").dt.date.astype(str)
    days = sorted(x.d.unique())
    k = days.index(dstr)
    prev = x[x.d == days[k - 1]].close.iloc[-1]
    cur = x[x.d == dstr]
    return {"gap": r(cur.open.iloc[0] / prev * 100 - 100), "open_to_close": r(cur.close.iloc[-1] / cur.open.iloc[0] * 100 - 100),
            "day": r(cur.close.iloc[-1] / prev * 100 - 100), "low_vs_open": r(cur.low.min() / cur.open.iloc[0] * 100 - 100)}

res["tokyo_intraday"] = {tk: {dt: intraday_day(tk, dt) for dt in ["2026-11-05", "2026-11-06"]} for tk in ["1321.T", "1306.T"]}

# 日経平均 -5%以下の日(2000年以降)とその後
dn = n225.pct_change() * 100
ev = dedup(list(dn[dn <= -5].index), 20, n225.index)
rows = fwd(n225, ev)
res["nikkei_m5_events"] = rows
res["nikkei_m5_summary"] = summ([x for x in rows if x["date"] != "2026-11-06"])
res["nikkei_all_summary"] = {f"f{h}": r((n225.shift(-h) / n225 - 1).mean() * 100) for h in (5, 20, 60)}
hi26 = n225["2026-01-01":].max()
res["nikkei_high_2026"] = {"date": n225["2026-01-01":].idxmax().strftime("%Y-%m-%d"), "close": r(hi26, 0),
                           "dd_pct": r(n225.loc[T] / hi26 * 100 - 100, 1)}

# ---------------------------------------------------------------- 2. 月曜の東京: CME日経先物と米国の戻り
nkd = px["NKD=F"]
both = pd.DataFrame({"nkd": nkd, "nk": n225}).dropna()
both["basis"] = both.nkd / both.nk * 100 - 100
both["nk_next"] = both.nk.shift(-1) / both.nk * 100 - 100
open_n = op["^N225"].reindex(both.index)
both["nk_next_open"] = open_n.shift(-1) / both.nk * 100 - 100
b = both.dropna()
b = b[b.index >= "2010-01-01"]
res["nkd_basis_1106"] = r(both.loc[T, "basis"])
res["nkd_vs_nextday"] = {
    "n": int(len(b)), "corr_close": r(b.basis.corr(b.nk_next), 2),
    "sign_hit_pct": r((np.sign(b.basis) == np.sign(b.nk_next)).mean() * 100, 1),
    "beta_close": r(np.polyfit(b.basis, b.nk_next, 1)[0], 2),
}
bb = b[b.basis >= 1.0]
res["nkd_basis_ge1"] = {"n": int(len(bb)), "next_mean": r(bb.nk_next.mean()), "next_median": r(bb.nk_next.median()),
                        "up_pct": r((bb.nk_next > 0).mean() * 100, 0),
                        "next_minus_basis_median": r((bb.nk_next - bb.basis).median())}
# 日経が-3%以下で引けた翌日に先物が+1%以上: 翌日の結果
cond = b[(b.index.isin(dn[dn <= -3].index)) & (b.basis >= 1.0)]
res["nkd_after_big_down"] = [{"date": i.strftime("%Y-%m-%d"), "nk": r(dn.loc[i]), "basis": r(x.basis), "next": r(x.nk_next)} for i, x in cond.iterrows()]
# アジアの同日比較
res["asia_1106"] = {t: r(px[t].pct_change(fill_method=None).loc[T] * 100) for t in ["^N225", "^KS11", "^TWII", "^HSI", "000660.KS", "005930.KS", "2330.TW", "285A.T", "6857.T", "8035.T", "^SOX", "TSM", "MU"]}

# ---------------------------------------------------------------- 3. 米国の戻り: 寄り天か
def us_intraday(tk, dstr):
    x = intra[intra.ticker == tk].copy()
    x["d"] = x.date.dt.tz_convert("America/New_York").dt.date.astype(str)
    days = sorted(x.d.unique())
    k = days.index(dstr)
    prev = x[x.d == days[k - 1]].close.iloc[-1]
    cur = x[x.d == dstr]
    return {"gap": r(cur.open.iloc[0] / prev * 100 - 100), "high_vs_prev": r(cur.high.max() / prev * 100 - 100),
            "close_vs_prev": r(cur.close.iloc[-1] / prev * 100 - 100),
            "open_to_close": r(cur.close.iloc[-1] / cur.open.iloc[0] * 100 - 100),
            "first_hour_vol_share": r(cur.volume.iloc[:2].sum() / cur.volume.sum() * 100, 0)}

res["us_intraday_1106"] = {tk: us_intraday(tk, "2026-11-06") for tk in ["SMH", "QQQ", "SPY"]}
res["smh_volume"] = {"1105": int(vol.loc["2026-11-05", "SMH"]), "1106": int(vol.loc[T, "SMH"]),
                     "avg20_before_1105": int(vol["SMH"].loc[:"2026-11-04"].tail(20).mean())}
sox = px["^SOX"].dropna()
res["sox_retrace"] = {"from_1104": r(sox.loc[T] / sox.loc["2026-11-04"] * 100 - 100),
                      "share_of_1105_drop_recovered": r((sox.loc[T] - sox.loc["2026-11-05"]) / (sox.loc["2026-11-04"] - sox.loc["2026-11-05"]) * 100, 0)}
# SOX -6%以下の日の翌日に+3%以上戻した場合 vs そうでない場合の20/60日後(起点は急落日)
sr = sox.pct_change() * 100
ev = dedup(list(sr[sr <= -6].index), 10, sox.index)
grp = {"bounce": [], "nobounce": []}
detail = []
for dt in ev:
    i = sox.index.get_loc(dt)
    if i + 60 >= len(sox) or i + 1 >= len(sox):
        if dt.strftime("%Y-%m-%d") == "2026-11-05":
            continue
        continue
    nxt = sox.iloc[i + 1] / sox.iloc[i] * 100 - 100
    f20 = sox.iloc[i + 20] / sox.iloc[i] * 100 - 100
    f60 = sox.iloc[i + 60] / sox.iloc[i] * 100 - 100
    key = "bounce" if nxt >= 3 else "nobounce"
    grp[key].append((f20, f60))
    detail.append({"date": dt.strftime("%Y-%m-%d"), "ret": r(sr.loc[dt]), "next": r(nxt), "f20": r(f20), "f60": r(f60)})
res["sox_m6_nextday"] = {k: {"n": len(v), "f20_median": r(np.median([a for a, _ in v])) if v else None,
                             "f60_median": r(np.median([c for _, c in v])) if v else None,
                             "f20_up_pct": r(np.mean([a > 0 for a, _ in v]) * 100, 0) if v else None,
                             "f60_up_pct": r(np.mean([c > 0 for _, c in v]) * 100, 0) if v else None}
                         for k, v in grp.items()}
res["sox_m6_detail"] = detail

# ---------------------------------------------------------------- 4. 作る側/使う側の逆回転
makers = ["NVDA", "AMD", "MU", "TSM", "ASML", "SMH"]
users = ["AAPL", "AMZN", "MSFT", "GOOGL"]
dd = {}
for dt in ["2026-11-04", "2026-11-05", "2026-11-06"]:
    rr = px.pct_change(fill_method=None).loc[dt] * 100
    dd[dt] = {t: r(rr[t]) for t in makers + users + ["SPY", "RSP", "^DJI", "XLP", "XLU", "XLK", "IWM"]}
res["makers_users_daily"] = dd
cum = {t: r(px.loc[T, t] / px.loc["2026-11-03", t] * 100 - 100) for t in makers + users + ["SPY", "RSP", "XLP", "XLU"]}
res["cum_since_1103"] = cum
res["makers_minus_users"] = {dt: r(np.mean([dd[dt][t] for t in makers]) - np.mean([dd[dt][t] for t in users])) for dt in dd}
res["makers_minus_users_cum"] = r(np.mean([cum[t] for t in makers]) - np.mean([cum[t] for t in users]))
# 電力株(テキサス): 11/5までのデータのみ
pw = ["VST", "NRG", "CEG", "VRT", "GEV", "ETN", "PWR"]
res["power_cum_1103_1105"] = {t: r(usc.loc["2026-11-05", t] / usc.loc["2026-11-03", t] * 100 - 100) for t in pw if t in usc.columns}
res["power_1104"] = {t: r(usc[t].pct_change().loc["2026-11-04"] * 100) for t in pw if t in usc.columns}
res["us_stocks_last_date"] = usc["AAPL"].dropna().index.max().strftime("%Y-%m-%d")

# ---------------------------------------------------------------- 5. 強い雇用統計と金利・ドル・円
chg = {}
for t in ["^TNX", "^FVX", "^IRX", "^TYX"]:
    chg[t] = r((px[t].loc[T] - px[t].loc["2026-11-05"]) * 100, 1)
for t in ["DX-Y.NYB", "JPY=X", "EURUSD=X", "GC=F", "TLT", "XLP", "XLU", "IWM", "KRE", "XLF"]:
    chg[t] = r(px[t].pct_change(fill_method=None).loc[T] * 100)
res["macro_1106"] = chg
res["jpy_intraday_1106"] = {"prev_close": r(px.loc["2026-11-05", "JPY=X"]), "open": r(op.loc[T, "JPY=X"]),
                            "high": r(d[(d.ticker == "JPY=X") & (d.date == T)].high.iloc[0]),
                            "close": r(px.loc[T, "JPY=X"])}
# DXY+0.5%以上かつドル円-0.3%以下の日(2005年以降)
fx = pd.DataFrame({"dxy": px["DX-Y.NYB"].pct_change() * 100, "jpy": px["JPY=X"].pct_change() * 100}).dropna()
fx = fx[fx.index >= "2005-01-01"]
m = fx[(fx.dxy >= 0.5) & (fx.jpy <= -0.3)]
res["dxy_up_yen_up_days"] = {"n": int(len(m)), "of_days": int(len(fx)), "recent": [i.strftime("%Y-%m-%d") for i in m.index[-6:]]}
# 日経平均とドル円の60日相関(日次リターン)
cc = pd.DataFrame({"nk": n225.pct_change(), "jpy": px["JPY=X"].pct_change()}).dropna()
res["nk_jpy_corr_60d"] = r(cc.tail(60).corr().iloc[0, 1], 2)
res["nk_jpy_corr_250d"] = r(cc.tail(250).corr().iloc[0, 1], 2)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=0, default=str)[:12000])
