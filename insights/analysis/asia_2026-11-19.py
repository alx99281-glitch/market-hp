"""Japan & Asia edition 2026-11-19: verification analyses.
Data: /tmp/market-data (GitHub Actions 2026-11-19 10:05 UTC, Yahoo Finance / JPX),
daily-review/data/prices_jp.parquet (to 2026-11-18).
"""
import json
import numpy as np
import pandas as pd

D = "/tmp/market-data/"
ASOF = pd.Timestamp("2026-11-19")
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


# ---------- today's 60m bars for 1306/1321
bars = intr[intr.ticker.isin(["1306.T", "1321.T"])].copy()
bars["jst"] = bars.date.dt.tz_convert("Asia/Tokyo")
today = bars[bars.jst.dt.date == ASOF.date()]
tb = {}
for t, g in today.groupby("ticker"):
    g = g.sort_values("jst")
    prev = float(jpc[t].dropna().iloc[-1])
    tb[t] = dict(prev=prev, close=float(g.close.iloc[-1]),
                 path=[(r.jst.strftime("%H:%M"), round((r.open / prev - 1) * 100, 2), round((r.high / prev - 1) * 100, 2),
                        round((r.low / prev - 1) * 100, 2), round((r.close / prev - 1) * 100, 2)) for r in g.itertuples()],
                 high_pct=round((g.high.max() / prev - 1) * 100, 2), low_pct=round((g.low.min() / prev - 1) * 100, 2),
                 high_time=g.loc[g.high.idxmax(), "jst"].strftime("%H:%M"),
                 low_time=g.loc[g.low.idxmin(), "jst"].strftime("%H:%M"),
                 close_pct=round((g.close.iloc[-1] / prev - 1) * 100, 2))
out["etf_today"] = tb

# ---------- 1. Nikkei up / TOPIX(1306) down two days in a row
n225 = px["^N225"].dropna()
t1306 = jpc["1306.T"].dropna().copy()
t1306.loc[ASOF] = tb["1306.T"]["close"]
t1306 = t1306.sort_index()
df = pd.DataFrame({"n": n225.pct_change() * 100, "t": t1306.pct_change() * 100}).dropna()
df["diverge"] = (df.n > 0) & (df.t < 0)
df["two"] = df.diverge & df.diverge.shift(1, fill_value=False)
hist = df[df.index < ASOF]
two = hist[hist.two]
fwd = []
for dt in two.index:
    i = n225.index.get_loc(dt)
    j = t1306.index.get_loc(dt)
    if i + 5 < len(n225) and j + 5 < len(t1306):
        fwd.append(dict(date=str(dt.date()), n_d=round(df.loc[dt, "n"], 2), t_d=round(df.loc[dt, "t"], 2),
                        n_5d=round((n225.iloc[i + 5] / n225.iloc[i] - 1) * 100, 2),
                        t_5d=round((t1306.iloc[j + 5] / t1306.iloc[j] - 1) * 100, 2)))
fd = pd.DataFrame(fwd)
nt = (n225 / t1306).dropna()
out["nt"] = dict(today_n=round(df.n.iloc[-1], 2), today_t1306=round(df.t.iloc[-1], 2),
                 prev_n=round(df.n.iloc[-2], 2), prev_t1306=round(df.t.iloc[-2], 2),
                 diverge_share_all=round(float(hist.diverge.mean() * 100), 1), n_days=int(len(hist)),
                 n_two=int(len(two)), hist_start=str(hist.index[0].date()),
                 two_recent=fwd[-8:], n_fwd=int(len(fd)),
                 two_n5_up=int((fd.n_5d > 0).sum()) if len(fd) else None,
                 two_n_beats_t=int((fd.n_5d > fd.t_5d).sum()) if len(fd) else None,
                 two_n5_mean=round(fd.n_5d.mean(), 2) if len(fd) else None,
                 nt_2d_chg=round((nt.iloc[-1] / nt.iloc[-3] - 1) * 100, 2),
                 nt_20d_chg=round((nt.iloc[-1] / nt.iloc[-21] - 1) * 100, 2),
                 nt_level_pct_3y=round(float((nt.iloc[-756:-1] < nt.iloc[-1]).mean() * 100), 1))

# ---------- 2. Taiwan down big while Korea / Japan up
tw, ks = px["^TWII"].dropna(), px["^KS11"].dropna()
a = pd.DataFrame({"tw": ret(tw), "ks": ret(ks), "nk": ret(n225)}).dropna()
a = a[a.index >= "2000-01-01"]
h = a[a.index < ASOF]
big_tw = h[h.tw <= -3.5]
both = big_tw[(big_tw.ks > 0) & (big_tw.nk > 0)]
ks_up = big_tw[big_tw.ks > 0]
gap = a.ks - a.tw
gap_today = float(gap.iloc[-1])
n_gap = int((gap[gap.index < ASOF] >= gap_today).sum())
last_gap = gap[(gap.index < ASOF) & (gap >= gap_today)]
corr60 = float(a.tw.iloc[-61:-1].corr(a.ks.iloc[-61:-1]))
tw_sig = sig(tw)
r21 = (tw / tw.shift(21) - 1) * 100
out["tw"] = dict(today=dict(tw=round(a.tw.iloc[-1], 2), ks=round(a.ks.iloc[-1], 2), nk=round(a.nk.iloc[-1], 2)),
                 tw_sigma=tw_sig[1], hist_start=str(h.index[0].date()),
                 n_tw_le_3_5=int(len(big_tw)), n_ks_up=int(len(ks_up)), n_ks_nk_up=int(len(both)),
                 both_dates=[str(d.date()) for d in both.index][-8:],
                 ks_up_dates=[str(d.date()) for d in ks_up.index][-8:],
                 ks_minus_tw_today=round(gap_today, 2), n_gap_ge=n_gap,
                 last_gap_ge=[str(d.date()) for d in last_gap.index][-5:],
                 corr60_tw_ks=round(corr60, 2),
                 tw_21d=round(float(r21.iloc[-1]), 2),
                 tw_21d_pctile=round(float((r21.dropna().iloc[:-1] < r21.iloc[-1]).mean() * 100), 2),
                 tw_21d_rank_worse_n=int((r21.dropna().iloc[:-1] <= r21.iloc[-1]).sum()),
                 tw_from_high=round(float((tw.iloc[-1] / tw.iloc[-252:].max() - 1) * 100), 1),
                 tw_high_date=str(tw.iloc[-252:].idxmax().date()),
                 tw_5d=round(float((tw.iloc[-1] / tw.iloc[-6] - 1) * 100), 2))
out["tw"]["ks_up_table"] = [[str(i.date()), round(r.tw, 2), round(r.ks, 2), round(r.nk, 2)] for i, r in ks_up.iterrows()]
# aftermath of TW <= -4% days
f = []
for dt in h[h.tw <= -4].index:
    i = tw.index.get_loc(dt)
    if i + 5 < len(tw):
        f.append(dict(date=str(dt.date()), d=round(a.loc[dt, "tw"], 2),
                      n1=round((tw.iloc[i + 1] / tw.iloc[i] - 1) * 100, 2),
                      n5=round((tw.iloc[i + 5] / tw.iloc[i] - 1) * 100, 2)))
ff = pd.DataFrame(f)
out["tw_after4"] = dict(n=int(len(ff)), n1_up=int((ff.n1 > 0).sum()), n5_up=int((ff.n5 > 0).sum()),
                        n5_med=round(ff.n5.median(), 2), recent=f[-6:])
# chips today
chips = {"2330.TW": "TSMC", "005930.KS": "サムスン電子", "000660.KS": "SKハイニックス", "8035.T": "東京エレクトロン",
         "6857.T": "アドバンテスト", "285A.T": "キオクシア", "9984.T": "ソフトバンクG", "4062.T": "イビデン"}
cr = []
for t, nm in chips.items():
    s = px[t].dropna()
    if s.index[-1] != ASOF:
        continue
    d1, sg = sig(s)
    cr.append(dict(name=nm, d1=d1, sigma=sg, r5=round(float((s.iloc[-1] / s.iloc[-6] - 1) * 100), 2),
                   from_20d_high=round(float((s.iloc[-1] / s.iloc[-21:].max() - 1) * 100), 1)))
out["chips"] = cr

# ---------- 3. Hong Kong vs Shanghai
hs, sh = px["^HSI"].dropna(), px["000001.SS"].dropna()
b = pd.DataFrame({"hs": ret(hs), "sh": ret(sh)}).dropna()
hb = b[b.index < ASOF]
cond = hb[(hb.hs <= -1.9) & (hb.sh > -0.5)]
out["hk"] = dict(hs=round(b.hs.iloc[-1], 2), sh=round(b.sh.iloc[-1], 2), hs_sigma=sig(hs)[1],
                 hs_last=round(float(hs.iloc[-1]), 2),
                 low_since=str(hs[(hs.index < ASOF) & (hs <= hs.iloc[-1])].index[-1].date()) if (hs[hs.index < ASOF] <= hs.iloc[-1]).any() else None,
                 hs_from_high=round(float((hs.iloc[-1] / hs.iloc[-252:].max() - 1) * 100), 1),
                 hs_high_date=str(hs.iloc[-252:].idxmax().date()),
                 hs_21d=round(float((hs.iloc[-1] / hs.iloc[-22] - 1) * 100), 2),
                 n_cond=int(len(cond)), hist_start=str(hb.index[0].date()), share_cond=round(len(cond) / len(hb) * 100, 1),
                 down_streak=int((lambda r: next((k for k, v in enumerate(r[::-1]) if v >= 0), len(r)))(b.hs.values)))

# ---------- 4. intraday + CME
nkd = px["NKD=F"].dropna()
out["cme"] = dict(nkd=float(nkd.iloc[-1]), n225=float(n225.iloc[-1]),
                  gap_pct=round((nkd.iloc[-1] / n225.iloc[-1] - 1) * 100, 2),
                  nq=sig(px["NQ=F"]), es=sig(px["ES=F"]),
                  note="NKD=F・NQ=F・ES=Fの11/19値は取得時点(10:05 UTC=19:05 JST)のもの")
# US intraday (SPY/QQQ/SMH) not needed; 1321 range vs typical
c1321 = jpc["1321.T"].dropna()
hl = jp[jp.ticker == "1321.T"].set_index("date")
rng = ((hl.high - hl.low) / hl.close.shift(1) * 100).dropna()
rng = rng[(rng < 15)]
today_rng = tb["1321.T"]["high_pct"] - tb["1321.T"]["low_pct"]
out["range"] = dict(today_range_1321=round(today_rng, 2), median_250=round(float(rng.iloc[-250:].median()), 2),
                    pctile_250=round(float((rng.iloc[-250:] < today_rng).mean() * 100), 1))

# ---------- 5. Korea vs Taiwan / India rotation (1-month)
rows = []
for t, nm in {"^N225": "日経平均", "^KS11": "KOSPI", "^TWII": "台湾加権", "^HSI": "ハンセン", "000001.SS": "上海総合",
              "^NSEI": "インドNifty50", "^BSESN": "インドSENSEX", "^STI": "シンガポールSTI", "^JKSE": "インドネシア総合",
              "^KLSE": "マレーシアKLCI", "^AXJO": "豪ASX200", "^SET.BK": "タイSET"}.items():
    s = px[t].dropna()
    if len(s) < 30:
        rows.append(dict(name=nm, note=f"履歴{len(s)}日"))
        continue
    d1, sg = sig(s) if len(s) > 260 else (round(float(ret(s).iloc[-1]), 2), None)
    rows.append(dict(name=nm, last_date=str(s.index[-1].date()), close=round(float(s.iloc[-1]), 2), d1=d1, sigma=sg,
                     r5=round(float((s.iloc[-1] / s.iloc[-6] - 1) * 100), 2),
                     r21=round(float((s.iloc[-1] / s.iloc[-22] - 1) * 100), 2)))
out["asia"] = rows
ni, twr = px["^NSEI"].dropna(), tw
c = pd.DataFrame({"in": ni.pct_change(21) * 100, "tw": twr.pct_change(21) * 100}).dropna()
c["gap"] = c["in"] - c["tw"]
out["india_tw"] = dict(gap21=round(float(c.gap.iloc[-1]), 2), n=int(len(c)), hist_start=str(c.index[0].date()),
                       pctile=round(float((c.gap.iloc[:-1] < c.gap.iloc[-1]).mean() * 100), 2),
                       last_ge=str(c[(c.index < ASOF) & (c.gap >= c.gap.iloc[-1])].index[-1].date()) if (c.gap.iloc[:-1] >= c.gap.iloc[-1]).any() else None)
dr = pd.DataFrame({"in": ret(ni), "tw": ret(twr)}).dropna()
out["india_tw"]["corr60"] = round(float(dr["in"].iloc[-61:-1].corr(dr.tw.iloc[-61:-1])), 2)
out["india_tw"]["corr_prev250"] = round(float(dr["in"].iloc[-311:-61].corr(dr.tw.iloc[-311:-61])), 2)

# ---------- 6. yen near 160
jpy = px["JPY=X"].dropna()
out["jpy"] = dict(last=round(float(jpy.iloc[-1]), 2), d1=sig(jpy),
                  max_1y=round(float(jpy.iloc[-252:].max()), 2), max_1y_date=str(jpy.iloc[-252:].idxmax().date()),
                  days_ge_159_5_in_1y=int((jpy.iloc[-252:] >= 159.5).sum()),
                  r21=round(float((jpy.iloc[-1] / jpy.iloc[-22] - 1) * 100), 2),
                  last_ge_160=str(jpy[jpy >= 160].index[-1].date()) if (jpy >= 160).any() else None)
# Asian FX today
fx = {}
for t in ["KRW=X", "TWD=X", "CNY=X", "INR=X", "IDR=X"]:
    s = px[t].dropna()
    r = ret(s)
    fx[t] = dict(last=round(float(s.iloc[-1]), 3), d1=round(float(r.iloc[-1]), 2), prev=round(float(r.iloc[-2]), 2),
                 sigma=round(float(r.iloc[-1] / r.iloc[-251:-1].std()), 2), date=str(s.index[-1].date()))
out["fx"] = fx

# ---------- 7. JP style ETFs today
etf = {"2516.T": "グロース250ETF", "1489.T": "日経高配当50ETF", "1343.T": "東証REIT ETF", "1570.T": "日経レバETF",
       "1545.T": "NASDAQ100 ETF(東証)", "2558.T": "S&P500 ETF(東証)", "1357.T": "日経ダブルインバース"}
out["jp_etf"] = [dict(name=nm, d1=sig(px[t])[0], sigma=sig(px[t])[1]) for t, nm in etf.items()]

json.dump(out, open("insights/data/analysis/asia_2026-11-19.json", "w"), ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, default=str, indent=0)[:12000])
