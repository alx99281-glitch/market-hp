"""Japan & Asia edition 2026-11-20: verification analyses.
Data: /tmp/market-data (GitHub Actions 2026-11-20 10:05 UTC, Yahoo Finance / JPX),
daily-review/data/prices_jp.parquet (to 2026-11-19; 11/20 for 1306/1321 taken from 60m bars).
"""
import json
import numpy as np
import pandas as pd

D = "/tmp/market-data/"
ASOF = pd.Timestamp("2026-11-20")
out = {}

daily = pd.read_parquet(D + "daily.parquet")
px = daily.pivot_table(index="date", columns="ticker", values="close")
intr = pd.read_parquet(D + "intraday_60m.parquet")
jp = pd.read_parquet("daily-review/data/prices_jp.parquet")
jpc = jp.pivot_table(index="date", columns="ticker", values="close")


def clean(df):
    med = df.rolling(11, center=True, min_periods=3).median()
    bad = (df / med > 1.5) | (df / med < 0.67)
    return df.mask(bad)


jpc = clean(jpc)


def ret(s):
    return s.dropna().pct_change() * 100


def sig(s, n=250):
    r = ret(s).dropna()
    return round(float(r.iloc[-1]), 2), round(float(r.iloc[-1] / r.iloc[-n - 1:-1].std()), 2)


def fwd(s, dt, k):
    i = s.index.get_loc(dt)
    return round(float((s.iloc[i + k] / s.iloc[i] - 1) * 100), 2) if i + k < len(s) else None


n225, ks, tw, hs = (px[t].dropna() for t in ["^N225", "^KS11", "^TWII", "^HSI"])
for s in (n225, ks, tw, hs):
    assert s.index[-1] == ASOF

# ---------- 0. today's 60m bars for 1306/1321
bars = intr[intr.ticker.isin(["1306.T", "1321.T"])].copy()
bars["jst"] = bars.date.dt.tz_convert("Asia/Tokyo")
today = bars[bars.jst.dt.date == ASOF.date()]
tb = {}
for t, g in today.groupby("ticker"):
    g = g.sort_values("jst")
    prev = float(jpc[t].dropna().iloc[-1])
    tb[t] = dict(prev=prev, prev_date=str(jpc[t].dropna().index[-1].date()), close=float(g.close.iloc[-1]),
                 open_pct=round((g.open.iloc[0] / prev - 1) * 100, 2),
                 first_bar_close_pct=round((g.close.iloc[0] / prev - 1) * 100, 2),
                 am_close_pct=round((g[g.jst.dt.hour <= 11].close.iloc[-1] / prev - 1) * 100, 2),
                 high_pct=round((g.high.max() / prev - 1) * 100, 2), low_pct=round((g.low.min() / prev - 1) * 100, 2),
                 low_time=g.loc[g.low.idxmin(), "jst"].strftime("%H:%M"),
                 close_pct=round((g.close.iloc[-1] / prev - 1) * 100, 2),
                 path=[(r.jst.strftime("%H:%M"), round((r.close / prev - 1) * 100, 2)) for r in g.itertuples()])
    tb[t]["share_of_drop_at_open"] = round(tb[t]["open_pct"] / tb[t]["close_pct"] * 100, 1)
out["etf_today"] = tb

# ---------- 1. Japan, Korea, Taiwan all down hard on the same day (since 2000)
a = pd.DataFrame({"nk": ret(n225), "ks": ret(ks), "tw": ret(tw), "hs": ret(hs)}).dropna()
a = a[a.index >= "2000-01-01"]
today_r = a.iloc[-1].round(2).to_dict()
h = a[a.index < ASOF]
sigmas = {k: sig(s)[1] for k, s in dict(nk=n225, ks=ks, tw=tw, hs=hs).items()}
cond4 = h[(h.nk <= -4) & (h.ks <= -4) & (h.tw <= -4)]
cond5 = h[(h.nk <= -5) & (h.ks <= -5) & (h.tw <= -5)]
rows = []
for dt, r in cond4.iterrows():
    rows.append([str(dt.date()), round(r.nk, 2), round(r.ks, 2), round(r.tw, 2),
                 fwd(n225, dt, 1), fwd(n225, dt, 5), fwd(n225, dt, 20)])
f = pd.DataFrame(rows, columns=["date", "nk", "ks", "tw", "nk1", "nk5", "nk20"])
out["triple"] = dict(today=today_r, sigmas=sigmas, hist_start=str(h.index[0].date()), n_days=int(len(h)),
                     n_cond4=int(len(cond4)), n_cond5=int(len(cond5)), table=rows,
                     nk1_up=int((f.nk1 > 0).sum()), nk5_up=int((f.nk5.dropna() > 0).sum()),
                     nk20_up=int((f.nk20.dropna() > 0).sum()), n_with20=int(f.nk20.notna().sum()),
                     nk5_med=round(float(f.nk5.median()), 2) if len(f) else None,
                     nk20_med=round(float(f.nk20.median()), 2) if len(f) else None)
# Nikkei <= -5% days count
nk_h = a.nk[a.index < ASOF]
out["nk5"] = dict(n_le_5=int((nk_h <= -5).sum()), since=str(nk_h.index[0].date()),
                  recent=[str(d.date()) for d in nk_h[nk_h <= -5].index][-6:],
                  n_le_5_2026=int((nk_h[nk_h.index >= "2026-01-01"] <= -5).sum()))

# ---------- 2. Weekly moves (11/13 -> 11/20) and rank since 2000
wk = {}
names = {"^N225": "日経平均", "^KS11": "KOSPI", "^TWII": "台湾加権", "^HSI": "ハンセン", "000001.SS": "上海総合",
         "^NSEI": "インドNifty50", "^STI": "シンガポールSTI", "^JKSE": "インドネシア総合", "^KLSE": "マレーシアKLCI",
         "^AXJO": "豪ASX200"}
for t, nm in names.items():
    s = px[t].dropna()
    w = s.resample("W-FRI").last().dropna()
    wr = (w.pct_change() * 100).dropna()
    wr = wr[wr.index >= "2000-01-01"]
    cur = float(wr.iloc[-1])
    prev = wr.iloc[:-1]
    worse = prev[prev <= cur]
    d1, sg = sig(s)
    wk[t] = dict(name=nm, d1=d1, sigma=sg, week=round(cur, 2), n_weeks=int(len(prev)),
                 n_worse_or_eq=int(len(worse)), last_worse=str(worse.index[-1].date()) if len(worse) else None,
                 r21=round(float((s.iloc[-1] / s.iloc[-22] - 1) * 100), 2),
                 from_1y_high=round(float((s.iloc[-1] / s.iloc[-252:].max() - 1) * 100), 1),
                 high_date=str(s.iloc[-252:].idxmax().date()), close=round(float(s.iloc[-1]), 2))
out["weekly"] = wk

# ---------- 3. Index-led vs broad: NT ratio with ETF proxies; reported breadth
t1306 = jpc["1306.T"].dropna().copy()
t1306.loc[ASOF] = tb["1306.T"]["close"]
t1306 = t1306.sort_index()
nt = (n225 / t1306).dropna()
nt = nt[nt.index >= "2023-09-01"]
ntr = (nt.pct_change() * 100).dropna()
out["nt"] = dict(n225_d=today_r["nk"], etf1306_d=round(float((t1306.iloc[-1] / t1306.iloc[-2] - 1) * 100), 2),
                 nt_d=round(float(ntr.iloc[-1]), 2), nt_d_sigma=round(float(ntr.iloc[-1] / ntr.iloc[-251:-1].std()), 2),
                 n_nt_le=int((ntr.iloc[:-1] <= ntr.iloc[-1]).sum()), nt_days=int(len(ntr) - 1),
                 nt_5d=round(float((nt.iloc[-1] / nt.iloc[-6] - 1) * 100), 2),
                 reported_topix_d=round(-148.25 / (3674.22 + 148.25) * 100, 2),
                 reported_nt=round(56436.65 / 3674.22, 2), reported_nt_prev=round(59444.21 / 3822.47, 2))
# Advantest + SBG contributions (reported 1016 yen) as share of the 3007.56 decline
out["contrib"] = dict(reported_two=1016, drop=3007.56, share=round(1016 / 3007.56 * 100, 1),
                      reported_prime_up=90, reported_prime_down=1443,
                      prime_down_share=round(1443 / (90 + 1443) * 100, 1))
# Days since 2023-09 where Nikkei <= -4% : 1306 vs Nikkei gap
df = pd.DataFrame({"n": n225.pct_change() * 100, "t": t1306.pct_change() * 100}).dropna()
df = df[df.index >= "2023-09-01"]
big = df[df.n <= -4]
out["nt"]["big_down_days"] = [[str(i.date()), round(r.n, 2), round(r.t, 2), round(r.n - r.t, 2)] for i, r in big.iterrows()]

# ---------- 4. AI names: SoftBank vs Anthropic debut; chips across Asia
chips = {"9984.T": "ソフトバンクG", "285A.T": "キオクシア", "6857.T": "アドバンテスト", "8035.T": "東京エレクトロン",
         "4062.T": "イビデン", "005930.KS": "サムスン電子", "000660.KS": "SKハイニックス", "2330.TW": "TSMC"}
cr = []
for t, nm in chips.items():
    s = px[t].dropna()
    if s.index[-1] != ASOF:
        continue
    d1, sg = sig(s)
    r = ret(s).dropna()
    r = r[r.index < ASOF]
    cr.append(dict(name=nm, d1=d1, sigma=sg, r5=round(float((s.iloc[-1] / s.iloc[-6] - 1) * 100), 2),
                   from_1y_high=round(float((s.iloc[-1] / s.iloc[-252:].max() - 1) * 100), 1),
                   n_le_today=int((r <= d1).sum()), hist_from=str(r.index[0].date())))
out["chips"] = cr
sbg = ret(px["9984.T"]).dropna()
sbg_h = sbg[(sbg.index < ASOF) & (sbg.index >= "2000-01-01")]
big_sbg = sbg_h[sbg_h <= -14]
out["sbg"] = dict(n_le_14=int(len(big_sbg)), dates=[str(d.date()) for d in big_sbg.index][-6:],
                  since=str(sbg_h.index[0].date()))
ant = px["ANT"].dropna() if "ANT" in px else pd.Series(dtype=float)
out["ant"] = dict(rows=[[str(i.date()), round(float(v), 2)] for i, v in ant.items()],
                  vs_ipo_83=round((float(ant.iloc[-1]) / 83 - 1) * 100, 2) if len(ant) else None)
# US overnight
out["us"] = {t: sig(px[t]) for t in ["^GSPC", "^IXIC", "^SOX", "NVDA", "AMD", "MU", "SNDK"] if t in px}
out["us_last_date"] = str(px["^GSPC"].dropna().index[-1].date())

# ---------- 5. Cross-asset: yen, gold, oil, defensive ETFs
jpy = px["JPY=X"].dropna()
out["cross"] = dict(jpy=sig(jpy), jpy_last=round(float(jpy.iloc[-1]), 2),
                    gold=sig(px["GC=F"]), oil=sig(px["CL=F"]), silver=sig(px["SI=F"]),
                    nkd=round(float(px["NKD=F"].dropna().iloc[-1]), 0),
                    nkd_vs_close=round((float(px["NKD=F"].dropna().iloc[-1]) / float(n225.iloc[-1]) - 1) * 100, 2),
                    nq=sig(px["NQ=F"]), es=sig(px["ES=F"]), vix=round(float(px["^VIX"].dropna().iloc[-1]), 2),
                    vxeem=round(float(px["^VXEEM"].dropna().iloc[-1]), 2) if "^VXEEM" in px else None)
# yen on big Nikkei down days (<= -4%) since 2000: median USDJPY change same day
j = pd.DataFrame({"nk": ret(n225), "jpy": ret(jpy)}).dropna()
j = j[j.index >= "2000-01-01"]
jb = j[(j.nk <= -4) & (j.index < ASOF)]
out["cross"]["yen_on_nk_le4"] = dict(n=int(len(jb)), med_jpy=round(float(jb.jpy.median()), 2),
                                     share_yen_stronger_than_today=round(float((jb.jpy < j.jpy.iloc[-1]).mean() * 100), 1),
                                     today_jpy=round(float(j.jpy.iloc[-1]), 2))
gj = pd.DataFrame({"nk": ret(n225), "g": ret(px["GC=F"])}).dropna()
gb = gj[(gj.nk <= -4) & (gj.index < ASOF) & (gj.index >= "2005-01-01")]
out["cross"]["gold_on_nk_le4"] = dict(n=int(len(gb)), n_gold_down=int((gb.g < 0).sum()),
                                      n_gold_le_3=int((gb.g <= -3).sum()))
etf = {"1343.T": "東証REIT ETF", "1489.T": "日経高配当50ETF", "2516.T": "グロース250ETF", "1570.T": "日経レバETF",
       "2510.T": "国内債券ETF"}
out["jp_etf"] = []
for t, nm in etf.items():
    s = px[t].dropna()
    if s.index[-1] == ASOF:
        d1, sg = sig(s)
        out["jp_etf"].append(dict(name=nm, d1=d1, sigma=sg))
# Asian FX
fx = {}
for t in ["KRW=X", "TWD=X", "CNY=X", "INR=X", "IDR=X"]:
    s = px[t].dropna()
    r = ret(s)
    fx[t] = dict(last=round(float(s.iloc[-1]), 3), d1=round(float(r.iloc[-1]), 2),
                 sigma=round(float(r.iloc[-1] / r.iloc[-251:-1].std()), 2), date=str(s.index[-1].date()))
out["fx"] = fx

# ---------- 6. India decoupling
ni = px["^NSEI"].dropna()
dr = pd.DataFrame({"in": ret(ni), "tw": ret(tw), "ks": ret(ks), "nk": ret(n225)}).dropna()
h6 = dr[dr.index < ASOF]
c = h6[(h6.tw <= -4) & (h6.ks <= -4)]
out["india"] = dict(today=round(float(dr["in"].iloc[-1]), 2), n_tw_ks_le4=int(len(c)), n_india_up=int((c["in"] > 0).sum()),
                    india_up_dates=[str(d.date()) for d in c[c["in"] > 0].index][-6:], since=str(h6.index[0].date()),
                    week=wk["^NSEI"]["week"], tw_week=wk["^TWII"]["week"], corr60_in_tw=round(float(dr["in"].iloc[-61:-1].corr(dr.tw.iloc[-61:-1])), 2))
inda, acwi = px["INDA"].dropna(), px["ACWI"].dropna()
rel = (inda / acwi).dropna()
ewt = (px["EWT"].dropna() / acwi).dropna()
out["india"]["inda_vs_acwi_21d"] = round(float((rel.iloc[-1] / rel.iloc[-22] - 1) * 100), 2)
out["india"]["ewt_vs_acwi_21d"] = round(float((ewt.iloc[-1] / ewt.iloc[-22] - 1) * 100), 2)
out["india"]["etf_last_date"] = str(rel.index[-1].date())

json.dump(out, open("insights/data/analysis/asia_2026-11-20.json", "w"), ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, default=str, indent=0))
