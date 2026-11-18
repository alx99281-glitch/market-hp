"""Japan & Asia edition 2026-11-18: verification analyses.
Data: /tmp/market-data (GitHub Actions, Yahoo Finance / JPX), daily-review/data/prices_jp.parquet (to 2026-11-17).
"""
import json
import numpy as np
import pandas as pd

D = "/tmp/market-data/"
ASOF = pd.Timestamp("2026-11-18")
out = {}

daily = pd.read_parquet(D + "daily.parquet")
px = daily.pivot_table(index="date", columns="ticker", values="close")
op = daily.pivot_table(index="date", columns="ticker", values="open")
intr = pd.read_parquet(D + "intraday_60m.parquet")
jp = pd.read_parquet("daily-review/data/prices_jp.parquet")
jpc = jp.pivot_table(index="date", columns="ticker", values="close")
jpo = jp.pivot_table(index="date", columns="ticker", values="open")


def clean(df):
    """Drop obvious bad prints (price jumps >50% vs 11-day rolling median, e.g. 1306 2026-03/04, 1321 2026-10)."""
    med = df.rolling(11, center=True, min_periods=3).median()
    bad = (df / med > 1.5) | (df / med < 0.67)
    return df.mask(bad)


jpc = clean(jpc)
jpo = jpo.mask(jpc.isna())


def sig(s, n=250):
    r = s.dropna().pct_change().dropna() * 100
    return float(r.iloc[-1]), float(r.iloc[-1] / r.iloc[-n - 1:-1].std())


# ---------- today's bars for 1306/1321 from 60m data
bars = intr[intr.ticker.isin(["1306.T", "1321.T"])].copy()
bars["jst"] = bars.date.dt.tz_convert("Asia/Tokyo")
today = bars[bars.jst.dt.date == ASOF.date()]
tb = {}
for t, g in today.groupby("ticker"):
    g = g.sort_values("jst")
    prev = float(jpc[t].dropna().iloc[-1])
    tb[t] = dict(prev=prev, open=float(g.open.iloc[0]), high=float(g.high.max()), low=float(g.low.min()),
                 close=float(g.close.iloc[-1]),
                 path=[(r.jst.strftime("%H:%M"), round((r.close / prev - 1) * 100, 2)) for r in g.itertuples()],
                 low_time=g.loc[g.low.idxmin(), "jst"].strftime("%H:%M"))
    for k in ["open", "high", "low", "close"]:
        tb[t][k + "_pct"] = round((tb[t][k] / prev - 1) * 100, 2)
out["etf_today"] = tb

# ---------- 1. NT ratio (N225 / 1306 proxy)
n225 = px["^N225"].dropna()
t1306 = jpc["1306.T"].dropna().copy()
t1306.loc[ASOF] = tb["1306.T"]["close"]
nt = (n225 / t1306).dropna()
ntr = nt.pct_change().dropna() * 100
r225 = n225.pct_change() * 100
r1306 = t1306.pct_change() * 100
sd = ntr.iloc[-251:-1].std()
d = ntr.iloc[-1]
cond = (r225 > 0) & (r1306 < 0)
spread = (r225 - r1306)
hist = pd.DataFrame({"r225": r225, "r1306": r1306, "spread": spread}).dropna()
hist = hist[hist.index < ASOF]
similar = hist[(hist.r225 > 0) & (hist.r1306 < 0) & (hist.spread >= 0.6)]
fwd = []
for dt in similar.index:
    i = n225.index.get_loc(dt)
    j = t1306.index.get_loc(dt)
    if i + 5 < len(n225) and j + 5 < len(t1306):
        fwd.append(dict(date=str(dt.date()), spread=round(similar.loc[dt, "spread"], 2),
                        n225_next=round((n225.iloc[i + 1] / n225.iloc[i] - 1) * 100, 2),
                        n225_5d=round((n225.iloc[i + 5] / n225.iloc[i] - 1) * 100, 2),
                        t1306_5d=round((t1306.iloc[j + 5] / t1306.iloc[j] - 1) * 100, 2)))
fd = pd.DataFrame(fwd)
pct_level = float((nt.iloc[-756:] < nt.iloc[-1]).mean() * 100)
out["nt"] = dict(nt_today=round(nt.iloc[-1], 2), nt_chg_pct=round(d, 2), sigma=round(d / sd, 2),
                 spread_today=round(spread.iloc[-1], 2), n225=round(r225.iloc[-1], 2), t1306=round(r1306.iloc[-1], 2),
                 level_pct_3y=round(pct_level, 1), hist_start=str(hist.index[0].date()),
                 n_similar=int(len(similar)), similar_recent=fwd[-8:],
                 similar_n225_5d_mean=round(fd.n225_5d.mean(), 2) if len(fd) else None,
                 similar_t1306_5d_mean=round(fd.t1306_5d.mean(), 2) if len(fd) else None,
                 similar_n225_5d_up=int((fd.n225_5d > 0).sum()) if len(fd) else None,
                 similar_spread5d_pos=int((fd.n225_5d > fd.t1306_5d).sum()) if len(fd) else None,
                 n_fwd=int(len(fd)),
                 nt_20d_chg=round((nt.iloc[-1] / nt.iloc[-21] - 1) * 100, 2),
                 nt_series=[[str(i.date()), round(v, 3)] for i, v in nt.iloc[-60:].items()])

# ---------- 2. Gap-up fade: 1321 open >= +0.8% vs prev close, close <= +0.4%
c1321 = jpc["1321.T"].dropna()
o1321 = jpo["1321.T"].reindex(c1321.index)
g = pd.DataFrame({"gap": (o1321 / c1321.shift(1) - 1) * 100, "day": (c1321 / c1321.shift(1) - 1) * 100,
                  "intra": (c1321 / o1321 - 1) * 100}).dropna()
gu = g[g.gap >= 0.8]
fade = gu[gu.day <= 0.4]
nxt = []
for dt in fade.index:
    i = c1321.index.get_loc(dt)
    if i + 1 < len(c1321):
        nxt.append((c1321.iloc[i + 1] / c1321.iloc[i] - 1) * 100)
out["gap_fade"] = dict(today_gap=tb["1321.T"]["open_pct"], today_close=tb["1321.T"]["close_pct"],
                       today_low=tb["1321.T"]["low_pct"], low_time=tb["1321.T"]["low_time"],
                       n_gapup=int(len(gu)), n_fade=int(len(fade)),
                       fade_share=round(len(fade) / len(gu) * 100, 1),
                       fade_next_mean=round(float(np.mean(nxt)), 2), fade_next_up=int(sum(x > 0 for x in nxt)),
                       n_next=len(nxt), gapup_intra_mean=round(gu.intra.mean(), 2),
                       since=str(g.index[0].date()))
# NKD vs N225
nkd = px["NKD=F"].dropna()
out["nkd"] = dict(nkd_last=float(nkd.iloc[-1]), n225_close=float(n225.iloc[-1]),
                  gap_pct=round((nkd.iloc[-1] / n225.iloc[-1] - 1) * 100, 2),
                  note="NKD=Fの11/18値は取得時点(10:52 UTC)のもの")

# ---------- 3. Asia chip reaction vs prior drop
names = {"6857.T": "アドバンテスト", "8035.T": "東京エレクトロン", "285A.T": "キオクシア", "9984.T": "ソフトバンクG",
         "4062.T": "イビデン", "000660.KS": "SKハイニックス", "005930.KS": "サムスン電子", "2330.TW": "TSMC",
         "^KS11": "KOSPI", "^TWII": "台湾加権", "^N225": "日経平均", "^HSI": "ハンセン", "NQ=F": "ナスダック100先物"}
rows = []
for t, nm in names.items():
    s = px[t].dropna()
    s = s[s.index <= ASOF]
    if s.index[-1] != ASOF:
        continue
    d1, sg = sig(s)
    hi = s.iloc[-21:-1].max()
    prev = s.iloc[-2]
    w5 = (s.iloc[-2] / s.iloc[-7] - 1) * 100  # 5 sessions before today
    drop = prev - s.iloc[-7]
    rec = (s.iloc[-1] - prev) / -drop * 100 if drop < 0 else None
    rows.append(dict(ticker=t, name=nm, d1=round(d1, 2), sigma=round(sg, 2), prior5d=round(w5, 2),
                     recovered_pct_of_prior5d=round(rec, 0) if rec is not None else None,
                     from_20d_high=round((s.iloc[-1] / hi - 1) * 100, 1)))
out["chips"] = rows
# NVDA move (reported after-hours) vs daily sd
nv = px["NVDA"].dropna()
out["nvda_sd"] = round(float(nv.pct_change().iloc[-251:].std() * 100), 2)

# ---------- 4. risk appetite: JP ETFs and growth
etf = {"2516.T": "グロース250ETF", "1489.T": "日経高配当50ETF", "1343.T": "東証REIT ETF", "2510.T": "国内債券ETF",
       "1570.T": "日経レバETF"}
er = []
for t, nm in etf.items():
    s = px[t].dropna()
    d1, sg = sig(s)
    r5 = s.pct_change(5) * 100
    er.append(dict(ticker=t, name=nm, d1=round(d1, 2), sigma=round(sg, 2), r5=round(r5.iloc[-1], 2),
                   r5_pctile=round(float((r5.dropna().iloc[:-1] < r5.iloc[-1]).mean() * 100), 1),
                   r5_hist_start=str(s.index[0].date())))
out["jp_etf"] = er
# yesterday sector ETF (TOPIX-17) 11/17 and breadth 11/17
sec = [c for c in jpc.columns if c.startswith("16") and c not in ("1605.T",)]
s17 = (jpc[sec].iloc[-1] / jpc[sec].iloc[-2] - 1) * 100
out["sector17_1117"] = s17.round(2).sort_values().to_dict()
uni = [c for c in jpc.columns if c[0].isdigit() and not c.startswith(("13", "16")) or c == "1332.T" or c == "1605.T"]
r = (jpc[uni].iloc[-1] / jpc[uni].iloc[-2] - 1)
out["breadth_1117"] = dict(n=int(r.notna().sum()), up_share=round(float((r > 0).mean() * 100), 1),
                           eq_weight=round(float(r.mean() * 100), 2), date=str(jpc.index[-1].date()))

# ---------- 5. ASEAN
ase = {"^STI": "シンガポールSTI", "^KLSE": "マレーシアKLCI", "^JKSE": "インドネシア総合", "^SET.BK": "タイSET",
       "^NSEI": "インドNifty50", "^AXJO": "豪ASX200", "000001.SS": "上海総合"}
ar = []
for t, nm in ase.items():
    s = px[t].dropna()
    s = s[s.index <= ASOF]
    if len(s) < 60:
        ar.append(dict(name=nm, note=f"履歴{len(s)}日のみ", d1=round((s.iloc[-1]/s.iloc[-2]-1)*100, 2) if len(s) > 1 else None))
        continue
    d1, sg = sig(s)
    r3 = (s.iloc[-1] / s.iloc[-4] - 1) * 100
    r3s = (s.pct_change(3) * 100).dropna()
    ar.append(dict(name=nm, last_date=str(s.index[-1].date()), d1=round(d1, 2), sigma=round(sg, 2), r3=round(r3, 2),
                   r3_pctile=round(float((r3s.iloc[-756:-1] < r3).mean() * 100), 1)))
out["asean"] = ar
sti = px["^STI"].dropna()
down = 0
for v in sti.pct_change().iloc[::-1]:
    if v < 0:
        down += 1
    else:
        break
out["sti_down_streak"] = down

# ---------- 6. margin: Kioxia buy shares vs price
m = pd.read_parquet(D + "margin_stock_daily.parquet")
k = m[m.code == "285A0"].set_index("date")[["buy_shs", "sell_shs", "buy_val"]]
kp = px["285A.T"].dropna()
k.index = pd.to_datetime(k.index)
k["close"] = kp.reindex(k.index)
k["avg_cost"] = k.buy_val / k.buy_shs
out["kioxia_margin"] = dict(
    rows=[[str(i.date()), int(r.buy_shs), round(r.close, 0), round(r.avg_cost, 0)] for i, r in k.iterrows()],
    buy_shs_chg_pct=round((k.buy_shs.iloc[-1] / k.buy_shs.iloc[0] - 1) * 100, 1),
    price_chg_pct=round((k.close.iloc[-1] / k.close.iloc[0] - 1) * 100, 1),
    close_1118=float(kp.iloc[-1]))
rep = json.load(open(D + "margin_report.json"))
top = rep["top"]
out["margin_top"] = [dict(name=r["name"], close=r["close"], est_cost=r["est_cost"], pnl=r["est_pnl_pct"],
                          to_cost_pct=round((r["est_cost"] / r["close"] - 1) * 100, 1), buy5d=r["buy_chg_5d_pct"])
                     for r in top]
# weekly: margin buy/sell vs 2002
w = pd.read_parquet(D + "margin_weekly.parquet")
out["weekly_last"] = w.tail(3).astype(str).to_dict("records")

# ---------- 7. commodities in Asia hours
cm = {}
for t in ["HG=F", "GC=F", "SI=F", "PL=F", "CL=F", "BZ=F", "CT=F"]:
    s = px[t].dropna()
    d1, sg = sig(s)
    cm[t] = dict(last=round(float(s.iloc[-1]), 2), d1=round(d1, 2), sigma=round(sg, 2), date=str(s.index[-1].date()))
out["commod"] = cm

out["jpy"] = round(float(px["JPY=X"].dropna().iloc[-1]), 2)
json.dump(out, open("insights/data/analysis/asia_2026-11-18.json", "w"), ensure_ascii=False, indent=1, default=str)
print(json.dumps({k: v for k, v in out.items() if k not in ("nt",)}, ensure_ascii=False, default=str)[:9000])
print(json.dumps({k: v for k, v in out["nt"].items() if k != "nt_series"}, ensure_ascii=False))

# ---------- base rate for gap-fade next day
nr = (c1321.shift(-1) / c1321 - 1) * 100
base = nr.dropna()
gun = nr.reindex(gu.index).dropna()
out["gap_fade"]["base_next_up_share"] = round(float((base > 0).mean() * 100), 1)
out["gap_fade"]["base_next_mean"] = round(float(base.mean()), 2)
out["gap_fade"]["gapup_next_up_share"] = round(float((gun > 0).mean() * 100), 1)
out["gap_fade"]["fade_next_up_share"] = round(out["gap_fade"]["fade_next_up"] / out["gap_fade"]["n_next"] * 100, 1)
json.dump(out, open("insights/data/analysis/asia_2026-11-18.json", "w"), ensure_ascii=False, indent=1, default=str)
print(out["gap_fade"])
