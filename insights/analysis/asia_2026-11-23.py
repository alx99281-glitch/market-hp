"""Japan & Asia edition 2026-11-23 (Tokyo closed: Labor Thanksgiving Day).
Data: /tmp/market-data (GitHub Actions 2026-11-23 10:05 UTC, Yahoo Finance / JPX),
daily-review/data/prices_jp.parquet (to 2026-11-20).
Asian index closes are 11/23; futures, FX, commodities and VIX are snapshots at fetch time.
"""
import json
import numpy as np
import pandas as pd

D = "/tmp/market-data/"
ASOF = pd.Timestamp("2026-11-23")
FRI = pd.Timestamp("2026-11-20")
out = {}

daily = pd.read_parquet(D + "daily.parquet")
px = daily.pivot_table(index="date", columns="ticker", values="close")
op = daily.pivot_table(index="date", columns="ticker", values="open")


def S(t):
    return px[t].dropna()


def r2(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 2)


def last_move(t, n=250):
    s = S(t)
    r = s.pct_change().dropna() * 100
    return dict(date=str(s.index[-1].date()), prev_date=str(s.index[-2].date()), close=r2(s.iloc[-1]),
                prev=r2(s.iloc[-2]), chg_pct=r2(r.iloc[-1]), sigma=r2(r.iloc[-1] / r.iloc[-n - 1:-1].std()))


# ---------- 0. today's moves
tick = ["^KS11", "^TWII", "^HSI", "000001.SS", "^NSEI", "^BSESN", "^STI", "^AXJO", "^JKSE", "^KLSE",
        "005930.KS", "000660.KS", "2330.TW", "KRW=X", "TWD=X", "JPY=X", "CNY=X", "NKD=F", "ES=F", "NQ=F",
        "GC=F", "BZ=F", "CL=F", "^VIX", "ZN=F"]
out["moves_1123"] = {t: last_move(t) for t in tick}
fri = ["^N225", "^GSPC", "^SOX", "NVDA", "TSM", "EWJ", "DXJ", "EWY", "EWT", "SMH", "9984.T", "^TNX", "^VIX"]
out["moves_fri"] = {t: last_move(t) if S(t).index[-1] == FRI else
                    {**last_move(t), "note": "has 11/23 value"} for t in fri}

# ---------- 1. Korea down >=3% and Taiwan up >=2% on the same day
ks, tw = S("^KS11"), S("^TWII")
both = pd.concat([ks, tw], axis=1, keys=["ks", "tw"]).dropna()
both = both[both.index >= "2000-01-01"]
rr = both.pct_change() * 100
spread = (rr.tw - rr.ks).dropna()
today_spread = float(spread.iloc[-1])
cond = rr[(rr.ks <= -3) & (rr.tw >= 2)]
rows = []
for dt in cond.index:
    i = both.index.get_loc(dt)
    f5 = lambda c: r2((both[c].iloc[i + 5] / both[c].iloc[i] - 1) * 100) if i + 5 < len(both) else None
    rows.append([str(dt.date()), r2(rr.ks[dt]), r2(rr.tw[dt]), f5("ks"), f5("tw")])
big = spread[spread.abs() >= abs(today_spread)]
out["kr_tw_divergence"] = dict(
    n_days=int(len(spread)), today_spread_pt=r2(today_spread),
    n_spread_ge_today=int(len(big)), n_tw_beats_ks_ge_today=int((spread >= today_spread).sum()),
    recent_ge=[[str(d.date()), r2(v)] for d, v in big.tail(8).items()],
    ks_down3_tw_up2=rows,
    corr_60d=r2(rr.ks.tail(60).corr(rr.tw.tail(60))), corr_250d=r2(rr.ks.tail(250).corr(rr.tw.tail(250))),
    ks_1m=r2((ks.iloc[-1] / ks.iloc[-22] - 1) * 100), tw_1m=r2((tw.iloc[-1] / tw.iloc[-22] - 1) * 100),
    ks_from_high=r2((ks.iloc[-1] / ks.tail(250).max() - 1) * 100), ks_high_date=str(ks.tail(250).idxmax().date()),
    tw_from_high=r2((tw.iloc[-1] / tw.tail(250).max() - 1) * 100), tw_high_date=str(tw.tail(250).idxmax().date()),
    ks_low_since=str(ks[ks <= ks.iloc[-1]].index[-2].date()) if (ks[:-1] <= ks.iloc[-1]).any() else None,
)
# Samsung / Hynix vs TSMC since Friday and 1m
out["chips"] = {t: dict(d1=last_move(t)["chg_pct"], m1=r2((S(t).iloc[-1] / S(t).iloc[-22] - 1) * 100))
                for t in ["005930.KS", "000660.KS", "2330.TW"]}

# ---------- 2. Asia after a US S&P500 drop of -3.5% or worse
sp = S("^GSPC")
spr = sp.pct_change() * 100
dd = spr[(spr <= -3.5) & (spr.index >= "2000-01-01")]
asia = ["^N225", "^KS11", "^TWII", "^HSI", "^NSEI"]
rows = []
for dt in dd.index:
    row = [str(dt.date()), r2(spr[dt])]
    for t in asia:
        s = S(t)
        nxt = s.index[s.index > dt]
        if len(nxt) == 0 or (nxt[0] - dt).days > 5:
            row.append(None)
            continue
        i = s.index.get_loc(nxt[0])
        row.append(r2((s.iloc[i] / s.iloc[i - 1] - 1) * 100))
    rows.append(row)
df = pd.DataFrame(rows, columns=["us_date", "sp"] + asia)
hist = df[df.us_date < "2026-11-20"]
summ = {t: dict(n=int(hist[t].notna().sum()), up=int((hist[t] > 0).sum()), median=r2(hist[t].median()))
        for t in asia}
out["asia_after_sp_drop"] = dict(n_events=int(len(hist)), summary=summ, latest=rows[-6:],
                                 today=rows[-1] if rows[-1][0] == "2026-11-20" else None)

# ---------- 3. CME Nikkei futures vs Tokyo open (gap prediction)
n225 = S("^N225")
nko = op["^N225"].dropna()
nkd = S("NKD=F")
g = []
for i in range(1, len(n225)):
    t, p = n225.index[i], n225.index[i - 1]
    if t < pd.Timestamp("2010-01-01") or t not in nko.index:
        continue
    f = nkd[(nkd.index > p) & (nkd.index < t)]
    if len(f) == 0:
        f = nkd[nkd.index == p]
        if len(f) == 0:
            continue
    implied = (f.iloc[-1] / n225.iloc[i - 1] - 1) * 100
    actual = (nko[t] / n225.iloc[i - 1] - 1) * 100
    g.append((t, (t - p).days, implied, actual))
gd = pd.DataFrame(g, columns=["date", "gap_days", "implied", "actual"]).set_index("date")
gd["err"] = gd.actual - gd.implied
multi = gd[gd.gap_days >= 3]
nkd_fri = float(nkd[nkd.index == FRI].iloc[0]) if FRI in nkd.index else None
out["nkd_gap"] = dict(
    n=int(len(gd)), corr=r2(gd.implied.corr(gd.actual)), mae=r2(gd.err.abs().median()),
    n_multi=int(len(multi)), corr_multi=r2(multi.implied.corr(multi.actual)), mae_multi=r2(multi.err.abs().median()),
    big_implied_n=int((gd.implied.abs() >= 2).sum()),
    big_implied_mae=r2(gd[gd.implied.abs() >= 2].err.abs().median()),
    n225_fri=r2(n225.iloc[-1]), nkd_fri=nkd_fri, nkd_fri_vs_cash=r2((nkd_fri / n225.iloc[-1] - 1) * 100),
    nkd_now=r2(nkd.iloc[-1]), nkd_now_vs_cash=r2((nkd.iloc[-1] / n225.iloc[-1] - 1) * 100),
)

# ---------- 4. Friday's Nikkei 225 breadth (prices_jp now has 11/20)
jp = pd.read_parquet("daily-review/data/prices_jp.parquet")
jpc = jp.pivot_table(index="date", columns="ticker", values="close")
names = [c for c in jpc.columns if c not in ("1306.T", "1321.T") and not c.startswith("16")]
rj = jpc[names].pct_change(fill_method=None) * 100
f = rj.loc[FRI].dropna()
f = f[f.abs() < 40]
etf = jpc[["1306.T", "1321.T"]].pct_change(fill_method=None).loc[FRI] * 100
hist_ew = rj.mean(axis=1).dropna()
sec_cols = [c for c in jpc.columns if c.startswith("16")]
sec = (jpc[sec_cols].pct_change(fill_method=None).loc[FRI] * 100).dropna().sort_values()
out["fri_breadth"] = dict(
    n=int(len(f)), down=int((f < 0).sum()), up=int((f > 0).sum()), ew_mean=r2(f.mean()), median=r2(f.median()),
    n225=r2(last_move("^N225")["chg_pct"] if S("^N225").index[-1] == FRI else None),
    etf_1306=r2(etf["1306.T"]), etf_1321=r2(etf["1321.T"]),
    ew_rank_since_2023=int((hist_ew <= hist_ew.loc[FRI]).sum()), ew_days=int(len(hist_ew)),
    worst=[[c, r2(v)] for c, v in f.sort_values().head(6).items()],
    best=[[c, r2(v)] for c, v in f.sort_values().tail(4).items()],
    sectors_low=[[c, r2(v)] for c, v in sec.head(4).items()],
    sectors_high=[[c, r2(v)] for c, v in sec.tail(4).items()],
)

# ---------- 5. gold and US equity futures both up >=2% on a day
gc, es = S("GC=F"), S("ES=F")
ge = pd.concat([gc, es], axis=1, keys=["gc", "es"]).dropna().pct_change() * 100
ge = ge[ge.index >= "2008-01-01"]
bothup = ge[(ge.gc >= 2) & (ge.es >= 2)]
out["gold_es"] = dict(n_days=int(len(ge)), n_both_up2=int(len(bothup)),
                      dates=[[str(d.date()), r2(a), r2(b)] for d, (a, b) in bothup.tail(10).iterrows()],
                      gold_fri=last_move("GC=F") if False else None,
                      gold_1m=r2((gc.iloc[-1] / gc.iloc[-22] - 1) * 100))

# ---------- 6. India: today's drop vs one-month outperformance
ni = S("^NSEI")
nr = ni.pct_change() * 100
acwi = S("ACWI")
out["india"] = dict(
    move=last_move("^NSEI"), sensex=last_move("^BSESN"),
    m1=r2((ni.iloc[-1] / ni.iloc[-22] - 1) * 100),
    m1_prev=r2((ni.iloc[-2] / ni.iloc[-23] - 1) * 100),
    acwi_m1_to_fri=r2((acwi.iloc[-1] / acwi.iloc[-22] - 1) * 100), acwi_last=str(acwi.index[-1].date()),
    n_down_175_250d=int((nr.tail(251).iloc[:-1] <= nr.iloc[-1]).sum()),
    inda_fri=last_move("INDA"),
)

json.dump(out, open("insights/data/analysis/asia_2026-11-23.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
