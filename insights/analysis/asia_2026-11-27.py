"""Japan & Asia edition 2026-11-27: verification analyses.
Data: /tmp/market-data (GitHub Actions 2026-11-27 10:06 UTC, Yahoo Finance / JPX; manually triggered because the
scheduled fetch ran at 03:46 UTC before the Asian close), daily-review/data/prices_jp.parquet (to 2026-11-26 only).
Reported values (TOPIX close, breadth, contributions, KOSDAQ, ChiNext etc.) are hard-coded with their source noted.
"""
import json
import numpy as np
import pandas as pd

D = "/tmp/market-data/"
ASOF = pd.Timestamp("2026-11-27")
PREV = pd.Timestamp("2026-11-26")
out = {}
daily = pd.read_parquet(D + "daily.parquet")
px = daily.pivot_table(index="date", columns="ticker", values="close")
lo = daily.pivot_table(index="date", columns="ticker", values="low")
hi = daily.pivot_table(index="date", columns="ticker", values="high")
op = daily.pivot_table(index="date", columns="ticker", values="open")
intr = pd.read_parquet(D + "intraday_60m.parquet")
jp = pd.read_parquet("daily-review/data/prices_jp.parquet")
jpc = jp.pivot_table(index="date", columns="ticker", values="close")


def ret(s):
    return s.dropna().pct_change() * 100


def fwd(s, dt, k):
    s = s.dropna()
    i = s.index.get_loc(dt)
    return round(float((s.iloc[i + k] / s.iloc[i] - 1) * 100), 2) if i + k < len(s) else None


# ---------- 0. snapshot
idx = {"^N225": "日経平均", "^KS11": "KOSPI", "^TWII": "台湾加権", "^HSI": "ハンセン", "000001.SS": "上海総合",
       "^STI": "シンガポールSTI", "^JKSE": "インドネシア総合", "^KLSE": "マレーシアKLCI", "^SET.BK": "タイSET",
       "^AXJO": "豪ASX200", "^NSEI": "インドNifty50", "^BSESN": "SENSEX", "2330.TW": "TSMC", "005930.KS": "サムスン電子",
       "000660.KS": "SKハイニックス", "6857.T": "アドバンテスト", "8035.T": "東京エレクトロン", "9984.T": "ソフトバンクG",
       "285A.T": "キオクシア", "4062.T": "イビデン", "2516.T": "グロース250ETF", "1489.T": "日経高配当50ETF",
       "1343.T": "東証REIT ETF", "1570.T": "日経レバETF", "GC=F": "金先物", "SI=F": "銀先物", "^VIX": "VIX"}
snap = {}
for t, nm in idx.items():
    if t not in px:
        continue
    s = px[t].dropna()
    if len(s) < 30 or s.index[-1] != ASOF:
        print("skip", t)
        continue
    r = ret(s).dropna()
    r = r[r.index >= "2000-01-01"]
    h = r.iloc[:-1]
    cur = float(r.iloc[-1])
    sd = float(h.iloc[-250:].std())
    prev = float(s.iloc[-2])
    low, hig, opn = lo[t].get(ASOF, np.nan), hi[t].get(ASOF, np.nan), op[t].get(ASOF, np.nan)
    snap[t] = dict(name=nm, close=round(float(s.iloc[-1]), 2), d1=round(cur, 2), prev_d1=round(float(r.iloc[-2]), 2),
                   sigma=round(cur / sd, 2), since=str(h.index[0].date()), n_days=int(len(h)),
                   n_as_big=int((h <= cur).sum() if cur < 0 else (h >= cur).sum()),
                   open_pct=round((opn / prev - 1) * 100, 2) if opn == opn else None,
                   low_pct=round((low / prev - 1) * 100, 2) if low == low else None,
                   high_pct=round((hig / prev - 1) * 100, 2) if hig == hig else None,
                   vs_1124=round(float((s.iloc[-1] / s.loc[:"2026-11-24"].iloc[-1] - 1) * 100), 2),
                   d_21=round(float((s.iloc[-1] / s.iloc[-22] - 1) * 100), 2),
                   from_1y_high=round(float((s.iloc[-1] / s.iloc[-252:].max() - 1) * 100), 1))
out["indices"] = snap

# ---------- 1. Futures-led, broad rally: NT, breadth (reported), 60m bars, close vs high
nk = px["^N225"].dropna()
topix = {"2026-11-25": 3746.20, "2026-11-26": 3750.40, "2026-11-27": 3815.20}   # reported (Nikkei/kabutan)
tp_d = (topix["2026-11-27"] / topix["2026-11-26"] - 1) * 100
nt = float(nk.iloc[-1]) / topix["2026-11-27"]
nt_prev = float(nk.iloc[-2]) / topix["2026-11-26"]
s0 = snap["^N225"]
out["nt"] = dict(topix_d=round(tp_d, 2), nt=round(nt, 3), nt_prev=round(nt_prev, 3), gap_pt=round(s0["d1"] - tp_d, 2),
                 nk_2d=round(float((nk.iloc[-1] / nk.iloc[-3] - 1) * 100), 2),
                 tp_2d=round((topix["2026-11-27"] / topix["2026-11-25"] - 1) * 100, 2))
# reported breadth: Nikkei225 adv 160 / dec 64 / unch 1 (vs 11/26 prime adv 749 dec 751); Advantest +378.64 yen,
# Advantest+TEL ~555 yen; top5 Advantest, TEL, SBG, Ibiden, TDK; Recruit -55.12 yen (kabutan/zaikei FISCO)
out["breadth_reported"] = dict(adv225=160, dec225=64, unch225=1, adv_share=round(160 / 225 * 100, 1), advantest=378.64,
                               adv_tel=555, total=1211.95, rest_ex_adv_tel=round(1211.95 - 555, 1), recruit=-55.12,
                               prime_value_trn=7.7872, prev_prime_adv_share=48.3)
gain_after_open = (s0["d1"] - s0["open_pct"]) / s0["d1"] * 100
out["intraday_nk"] = dict(open=s0["open_pct"], low=s0["low_pct"], high=s0["high_pct"], close=s0["d1"],
                          share_after_open=round(gain_after_open, 1),
                          close_vs_high_pt=round(s0["high_pct"] - s0["d1"], 2))
bars = {}
for t in ["1321.T", "1306.T"]:
    b = intr[intr.ticker == t].set_index("date").sort_index()
    pc = float(jpc[t].dropna().loc[PREV])
    bd = b[b.index.tz_convert("Asia/Tokyo").normalize().tz_localize(None) == ASOF]
    bars[t] = [[str(i.tz_convert("Asia/Tokyo").strftime("%H:%M")), round((float(r.close) / pc - 1) * 100, 2),
                int(r.volume)] for i, r in bd.iterrows()]
out["bars_60m"] = bars
# history: open within +/-0.5%, close >= +2%, close within 0.3pt of high (trend day up) and next day
r = ret(nk)
o = (op["^N225"] / nk.shift(1) - 1) * 100
hh = (hi["^N225"] / nk.shift(1) - 1) * 100
df = pd.DataFrame({"r": r, "o": o, "h": hh}).dropna()
df = df[df.index >= "2000-01-01"]
ev = df[(df.o.abs() <= 0.5) & (df.r >= 2) & (df.h - df.r <= 0.3) & (df.index < ASOF)]
nx1 = [fwd(nk, d, 1) for d in ev.index]
nx5 = [fwd(nk, d, 5) for d in ev.index]
v1 = [x for x in nx1 if x is not None]
v5 = [x for x in nx5 if x is not None]
out["trend_day_hist"] = dict(rule="寄り付き±0.5%以内、終値+2%以上、高値との差0.3pt以内(2000年以降)", n=int(len(ev)),
                             next_med=round(float(np.median(v1)), 2), next_up=int(sum(x > 0 for x in v1)),
                             d5_med=round(float(np.median(v5)), 2), d5_up=int(sum(x > 0 for x in v5)),
                             rows=[[str(d.date()), round(float(x.o), 2), round(float(x.r), 2), fwd(nk, d, 1), fwd(nk, d, 5)]
                                   for d, x in ev.iloc[-8:].iterrows()])
nkd = px["NKD=F"].dropna()
out["nkd"] = dict(last=float(nkd.iloc[-1]), vs_close=round(float(nkd.iloc[-1] / nk.iloc[-1] - 1) * 100, 2))
for t in ["NQ=F", "ES=F"]:
    s2 = px[t].dropna()
    out.setdefault("us_fut", {})[t] = dict(last=float(s2.iloc[-1]), d1=round(float(ret(s2).iloc[-1]), 2),
                                           sigma=round(float(ret(s2).iloc[-1] / ret(s2).iloc[-251:-1].std()), 2))

# ---------- 2. alternation streak ended; recovery of 11/25 drop
alt = {}
for t in ["^N225", "^KS11", "^TWII", "^HSI"]:
    rr = ret(px[t]).dropna().iloc[-8:]
    alt[t] = [[str(d.date()), round(float(v), 2)] for d, v in rr.items()]
out["last8"] = alt
rec = {}
for t in ["^N225", "^KS11", "^TWII", "^HSI", "000001.SS", "^NSEI", "6857.T", "8035.T", "285A.T", "9984.T", "2330.TW", "005930.KS"]:
    s2 = px[t].dropna()
    d25 = float(ret(s2).get(pd.Timestamp("2026-11-25"), np.nan))
    two = float((s2.iloc[-1] / s2.loc[:"2026-11-25"].iloc[-1] - 1) * 100)
    rec[t] = dict(d1125=round(d25, 2), since_1125=round(two, 2), vs_1124=round(float((s2.iloc[-1] / s2.loc[:"2026-11-24"].iloc[-1] - 1) * 100), 2))
out["recovery"] = rec

# ---------- 3. KOSPI +4.34%
ks = px["^KS11"].dropna()
rk = ret(ks).dropna()
rk = rk[rk.index >= "2000-01-01"]
ev = rk[(rk >= 4) & (rk.index < ASOF)]
n1 = [fwd(ks, d, 1) for d in ev.index]
n1 = [x for x in n1 if x is not None]
n5 = [x for x in [fwd(ks, d, 5) for d in ev.index] if x is not None]
out["kospi_up4"] = dict(n=int(len(ev)), n_2026=int((ev.index >= "2026-01-01").sum()), next_med=round(float(np.median(n1)), 2),
                        next_up=int(sum(x > 0 for x in n1)), d5_med=round(float(np.median(n5)), 2),
                        recent=[[str(d.date()), round(float(v), 2)] for d, v in ev.iloc[-6:].items()])
out["kospi_absmean"] = dict(last10=round(float(rk.iloc[-10:].abs().mean()), 2), y250=round(float(rk.iloc[-250:].abs().mean()), 2))
# reported: KOSDAQ +8.13% to 708.99; foreigners +1.1256tn KRW, inst +238.9bn, indiv -1.7751tn; Samsung +4.55% 179,100;
# SK hynix +5.41% 1,110,000 (ex-dividend day; Yahoo prior close appears dividend-adjusted -> +7.45% in data)

# ---------- 4. China A-shares: Shanghai +3.73%
ss = px["000001.SS"].dropna()
rs = ret(ss).dropna()
rs = rs[rs.index >= "2000-01-01"]
ev = rs[(rs >= rs.iloc[-1]) & (rs.index < ASOF)]
n5 = [fwd(ss, d, 5) for d in ev.index]
n5 = [x for x in n5 if x is not None]
n1 = [x for x in [fwd(ss, d, 1) for d in ev.index] if x is not None]
out["sse"] = dict(d1=round(float(rs.iloc[-1]), 2), sigma=snap["000001.SS"]["sigma"], n_as_big=int(len(ev)),
                  since_2016=int((ev.index >= "2016-01-01").sum()), next_med=round(float(np.median(n1)), 2),
                  next_up=int(sum(x > 0 for x in n1)), d5_med=round(float(np.median(n5)), 2), d5_up=int(sum(x > 0 for x in n5)),
                  recent=[[str(d.date()), round(float(v), 2), fwd(ss, d, 1), fwd(ss, d, 5)] for d, v in ev.iloc[-8:].items()])
hs = px["^HSI"].dropna()
out["hsi"] = dict(d1=snap["^HSI"]["d1"], sigma=snap["^HSI"]["sigma"], d_21=snap["^HSI"]["d_21"])
# same-day >=3% in SSE and >=2% in Nikkei
both = pd.DataFrame({"ss": rs, "nk": ret(nk), "ks": ret(ks)}).dropna()
c = both[(both.ss >= 3) & (both.nk >= 2) & (both.ks >= 3)]
out["sse_nk_ks_same_day"] = [[str(d.date()), round(float(x.ss), 2), round(float(x.nk), 2), round(float(x.ks), 2)] for d, x in c.iterrows()]
# reported: Shenzhen comp +7.24% 10,814.02; ChiNext +11.61% 2,443.96; >5,300 stocks up; turnover >2tn CNY (+600bn);
# semis +~15%, SMIC A +15.38%, Cambricon +18.68%; HS Tech +6.45%, SMIC HK +16% (21jingji / FX168 / Standard)

# ---------- 5. India and Taiwan lag
asia = pd.DataFrame({t: ret(px[t]) for t in ["^N225", "^KS11", "^HSI", "000001.SS", "^NSEI", "^TWII"]}).dropna()
asia = asia[asia.index >= "2005-01-01"]
others = asia[["^N225", "^KS11", "^HSI", "000001.SS"]].mean(axis=1)
c = asia[(asia["^NSEI"] <= -1) & (others >= 2)]
out["india_lag"] = dict(nifty=snap["^NSEI"]["d1"], others_mean=round(float(others.iloc[-1]), 2), n=int(len(c)),
                        rows=[[str(d.date()), round(float(x["^NSEI"]), 2), round(float(others.loc[d]), 2)] for d, x in c.iterrows()],
                        nifty_21=snap["^NSEI"]["d_21"], nk_21=snap["^N225"]["d_21"], ks_21=snap["^KS11"]["d_21"],
                        tw_21=snap["^TWII"]["d_21"])
sp = (asia["^KS11"] - asia["^TWII"])
out["kr_tw_spread"] = dict(today=round(float(sp.iloc[-1]), 2), sd=round(float(sp.iloc[-251:-1].std()), 2),
                           n_ge=int((sp.iloc[:-1] >= sp.iloc[-1]).sum()), n=int(len(sp) - 1))
out["kr_tw_spread"]["sigma"] = round(out["kr_tw_spread"]["today"] / out["kr_tw_spread"]["sd"], 2)
# reported: TAIEX +156.27 to 39,308.08, last trading day before local elections (11/28); TSMC 2,180 (+1.63%) on a late
# 11,300-lot block; foreigners net sellers 10 straight days in Nov (>500bn TWD)

# ---------- 6. risk-on style & cross-asset
sty = {}
for t in ["2516.T", "1489.T", "1343.T", "1570.T", "2558.T", "2510.T", "1357.T"]:
    if t in px:
        s2 = px[t].dropna()
        rr = ret(s2).dropna()
        sty[t] = dict(d1=round(float(rr.iloc[-1]), 2), sigma=round(float(rr.iloc[-1] / rr.iloc[-251:-1].std()), 2),
                      d1126=round(float(rr.iloc[-2]), 2))
out["style"] = sty
fxo = {}
for t in ["JPY=X", "KRW=X", "TWD=X", "CNY=X", "INR=X", "IDR=X", "AUDUSD=X", "GC=F", "SI=F", "HG=F", "BZ=F", "CL=F", "^VIX", "BTC-USD", "ZN=F"]:
    s2 = px[t].dropna()
    rr = ret(s2).dropna()
    fxo[t] = dict(last=round(float(s2.iloc[-1]), 4), date=str(s2.index[-1].date()), d1=round(float(rr.iloc[-1]), 2),
                  sigma=round(float(rr.iloc[-1] / rr.iloc[-251:-1].std()), 2),
                  hi_252=bool(s2.iloc[-1] >= s2.iloc[-252:].max()), lo_252=bool(s2.iloc[-1] <= s2.iloc[-252:].min()))
out["cross"] = fxo
inr = px["INR=X"].dropna()
out["inr_max_since"] = str(inr[inr >= inr.iloc[-1]].index[0].date())
gc = px["GC=F"].dropna()
rg = ret(gc).dropna()
out["gold"] = dict(d1=round(float(rg.iloc[-1]), 2), n_ge_since2000=int((rg[(rg.index >= "2000-01-01")].iloc[:-1] >= rg.iloc[-1]).sum()),
                   from_1y_high=round(float((gc.iloc[-1] / gc.iloc[-252:].max() - 1) * 100), 1),
                   two_day=round(float((gc.iloc[-1] / gc.iloc[-3] - 1) * 100), 2))

# ---------- 7. Margin: top holders (11/26 application data) re-marked at 11/27 close
m = json.load(open(D + "margin_report.json"))
out["margin_top"] = [[x["code"], x["name"], x["close"], x["est_cost"], x["est_pnl_pct"], x["buy_chg_1d_pct"], x["buy_chg_5d_pct"]]
                     for x in m["top"]]
out["margin_agg"] = m["top_agg"]
out["margin_agg_prev"] = {"edition 11/25 (11/24 data, 11/25 close)": -28.8, "edition 11/26 (11/25 data, 11/26 close)": -25.1}
out["margin_top_buy_down_on_1126"] = [x["code"] for x in m["top"] if x["buy_chg_1d_pct"] < 0]
out["to_cost"] = {x["code"]: round((x["est_cost"] / x["close"] - 1) * 100, 1) for x in m["top"]}
out["margin_total"] = {k: v for k, v in m["total"].items() if not k.startswith("series")}
out["individuals"] = m["individuals"]["weeks"][:2]

json.dump(out, open("insights/data/analysis/asia_2026-11-27.json", "w"), ensure_ascii=False, indent=1, default=float)
print(json.dumps(out, ensure_ascii=False, default=float))
