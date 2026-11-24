"""Japan & Asia edition 2026-11-24: verification analyses.
Data: /tmp/market-data (GitHub Actions 2026-11-24 10:07 UTC, Yahoo Finance / JPX; manual trigger),
daily-review/data/prices_jp.parquet (to 2026-11-20 only; constituent-level analysis for 11/24 is limited).
"""
import json
import numpy as np
import pandas as pd

D = "/tmp/market-data/"
ASOF = pd.Timestamp("2026-11-24")
out = {}
daily = pd.read_parquet(D + "daily.parquet")
px = daily.pivot_table(index="date", columns="ticker", values="close")
intr = pd.read_parquet(D + "intraday_60m.parquet")
jp = pd.read_parquet("daily-review/data/prices_jp.parquet")
jpc = jp.pivot_table(index="date", columns="ticker", values="close")


def ret(s):
    return s.dropna().pct_change() * 100


def sig(s, n=250):
    r = ret(s).dropna()
    return round(float(r.iloc[-1]), 2), round(float(r.iloc[-1] / r.iloc[-n - 1:-1].std()), 2)


def fwd(s, dt, k):
    s = s.dropna()
    i = s.index.get_loc(dt)
    return round(float((s.iloc[i + k] / s.iloc[i] - 1) * 100), 2) if i + k < len(s) else None


idx = {"^N225": "日経平均", "^KS11": "KOSPI", "^TWII": "台湾加権", "^HSI": "ハンセン", "000001.SS": "上海総合",
       "^STI": "シンガポールSTI", "^JKSE": "インドネシア総合", "^KLSE": "マレーシアKLCI", "^AXJO": "豪ASX200",
       "^NSEI": "インドNifty50"}
snap = {}
for t, nm in idx.items():
    s = px[t].dropna()
    d1, sg = sig(s)
    r = ret(s).dropna()
    r = r[r.index >= "2000-01-01"]
    h = r.iloc[:-1]
    cur = r.iloc[-1]
    ge = h[h >= cur] if cur > 0 else h[h <= cur]
    snap[t] = dict(name=nm, date=str(s.index[-1].date()), close=round(float(s.iloc[-1]), 2), d1=d1, sigma=sg,
                   n_days_since2000=int(len(h)), n_as_big=int(len(ge)),
                   last_as_big=str(ge.index[-1].date()) if len(ge) else None,
                   rank_since2000=int((h >= cur).sum() + 1) if cur > 0 else None,
                   from_1y_high=round(float((s.iloc[-1] / s.iloc[-252:].max() - 1) * 100), 1),
                   high_date=str(s.iloc[-252:].idxmax().date()))
out["indices"] = snap

# ---------- 1. Taiwan: the biggest % days since 2000, and price-limit cap vs ADR / EWT
tw = px["^TWII"].dropna()
rtw = ret(tw).dropna()
rtw = rtw[rtw.index >= "2000-01-01"]
top = rtw.sort_values(ascending=False).head(8)
out["tw_top_days"] = [[str(d.date()), round(float(v), 2), fwd(tw, d, 5), fwd(tw, d, 20)] for d, v in top.items()]
# point gain record check (within data)
pts = tw.diff().dropna()
out["tw_points"] = dict(today=round(float(pts.iloc[-1]), 2), max_prev=round(float(pts.iloc[:-1].max()), 2),
                        max_prev_date=str(pts.iloc[:-1].idxmax().date()))
# 2-day move 11/20 -> 11/24 for Taiwan vs EWT (USD, 11/20->11/23)
two = {}
for t in ["^TWII", "2330.TW", "^KS11", "005930.KS", "000660.KS", "^N225", "^HSI"]:
    s = px[t].dropna()
    base = s.loc[:"2026-11-20"].iloc[-1]
    two[t] = dict(r_since_1120=round(float((s.iloc[-1] / base - 1) * 100), 2),
                  r_1120=round(float(ret(s).loc["2026-11-20"]), 2) if pd.Timestamp("2026-11-20") in s.index else None)
for t in ["EWT", "TSM", "EWY", "EWJ", "SOXX", "^SOX", "NVDA", "FXI", "MCHI", "KWEB"]:
    s = px[t].dropna()
    two[t] = dict(r_1123=round(float(ret(s).loc["2026-11-23"]), 2), r_1120=round(float(ret(s).loc["2026-11-20"]), 2),
                  r_since_1119=round(float((s.loc["2026-11-23"] / s.loc["2026-11-19"] - 1) * 100), 2))
out["two_day"] = two
# TSMC ADR premium: 1 ADR = 5 ordinary shares
adr = px["TSM"].dropna()
loc = px["2330.TW"].dropna()
fx = px["TWD=X"].dropna()
df = pd.DataFrame({"adr": adr, "loc": loc, "fx": fx}).ffill().dropna()
df = df[df.index.isin(loc.index)]
df["prem"] = (df.adr / (df["loc"] * 5 / df.fx) - 1) * 100
# ADR on US date t is compared to Taiwan close on t (TW closes earlier). Use ADR of previous US day vs today's TW close
adr_prev = adr.shift(0)
df2 = pd.DataFrame({"loc": loc, "fx": fx.reindex(loc.index).ffill()})
df2["adr_prev_us"] = adr.reindex(loc.index, method="ffill").shift(0)
# for 11/24: latest ADR is 11/23 US close (after TW 11/23 close, before TW 11/24 open)
p_today = float(adr.loc["2026-11-23"] / (loc.loc["2026-11-24"] * 5 / fx.iloc[-1]) - 1) * 100
pr = df["prem"]
pr = pr[pr.index >= "2023-01-01"]
recent = {}
for d in ["2026-11-18", "2026-11-19", "2026-11-20", "2026-11-23"]:
    recent[d] = round(float(pr.loc[d]), 1) if pd.Timestamp(d) in pr.index else None
out["tsm_premium_recent"] = recent
out["tsm_premium"] = dict(adr_1123=round(float(adr.loc["2026-11-23"]), 2), tw_1124=float(loc.loc["2026-11-24"]),
                          twd=round(float(fx.iloc[-1]), 3), prem_vs_1124_close=round(p_today, 1),
                          prem_med_since2023=round(float(pr.median()), 1), prem_p95=round(float(pr.quantile(.95)), 1),
                          prem_max=round(float(pr.max()), 1), prem_max_date=str(pr.idxmax().date()),
                          n_days=int(len(pr)), n_ge_today=int((pr >= p_today).sum()))
# historic TSMC limit-up (>=9.5%) days and next-day returns
rl = ret(loc).dropna()
lim = rl[rl >= 9.5]
out["tsmc_limit_days"] = [[str(d.date()), round(float(v), 2), fwd(loc, d, 1), fwd(loc, d, 5)] for d, v in lim.items()]

# ---------- 2. North Asia sync: Nikkei>=+3.5, KOSPI>=+5, Taiwan>=+5 same day
a = pd.DataFrame({"nk": ret(px["^N225"]), "ks": ret(px["^KS11"]), "tw": ret(px["^TWII"]),
                  "hs": ret(px["^HSI"])}).dropna()
a = a[a.index >= "2000-01-01"]
h = a[a.index < ASOF]
c = h[(h.nk >= 3.5) & (h.ks >= 5) & (h.tw >= 5)]
rows = [[str(d.date()), round(r.nk, 2), round(r.ks, 2), round(r.tw, 2), round(r.hs, 2),
         fwd(px["^N225"], d, 5), fwd(px["^N225"], d, 20)] for d, r in c.iterrows()]
out["triple_up"] = dict(n=int(len(c)), rows=rows, n_days=int(len(h)))
# Taiwan >= +5 and HSI < 0 same day
c2 = h[(h.tw >= 5) & (h.hs < 0)]
out["tw_up_hs_down"] = dict(n=int(len(c2)), rows=[[str(d.date()), round(r.tw, 2), round(r.hs, 2)] for d, r in c2.iterrows()],
                            n_tw_ge5=int((h.tw >= 5).sum()))
# 60d correlation HSI with TWII / N225
rr = a.tail(250)
out["corr"] = dict(hs_tw_60=round(float(a.tail(60).hs.corr(a.tail(60).tw)), 2), hs_tw_250=round(float(rr.hs.corr(rr.tw)), 2),
                   hs_nk_60=round(float(a.tail(60).hs.corr(a.tail(60).nk)), 2), hs_nk_250=round(float(rr.hs.corr(rr.nk)), 2))
hs = px["^HSI"].dropna()
ytd = hs[hs.index >= "2026-01-01"]
out["hsi"] = dict(close=round(float(hs.iloc[-1]), 2), ytd_high=round(float(ytd.max()), 2), ytd_high_date=str(ytd.idxmax().date()),
                  from_ytd_high=round(float((hs.iloc[-1] / ytd.max() - 1) * 100), 2),
                  down_streak=int((ret(hs).iloc[::-1] < 0).cumprod().sum()),
                  r21=round(float((hs.iloc[-1] / hs.iloc[-22] - 1) * 100), 2))

# ---------- 3. Japan: rebound vs prior drop; past similar (<= -4.5% then >= +3.5% within 3 days)
nk = px["^N225"].dropna()
rn = ret(nk).dropna()
out["nk"] = dict(close=round(float(nk.iloc[-1]), 2), d1=round(float(rn.iloc[-1]), 2), prev_d1=round(float(rn.iloc[-2]), 2),
                 prev_pts=round(float(nk.iloc[-2] - nk.iloc[-3]), 2), pts=round(float(nk.iloc[-1] - nk.iloc[-2]), 2),
                 recovered_pct=round(float((nk.iloc[-1] - nk.iloc[-2]) / (nk.iloc[-3] - nk.iloc[-2]) * 100), 1),
                 vs_1119=round(float((nk.iloc[-1] / nk.iloc[-3] - 1) * 100), 2),
                 from_1y_high=round(float((nk.iloc[-1] / nk.iloc[-252:].max() - 1) * 100), 1),
                 high_date=str(nk.iloc[-252:].idxmax().date()))
rn2 = rn[rn.index >= "1990-01-01"]
ev = []
for i in range(3, len(rn2) - 1):
    d = rn2.index[i]
    if d >= ASOF:
        break
    if rn2.iloc[i] >= 3.5 and (rn2.iloc[i - 3:i] <= -4.5).any():
        if ev and (d - pd.Timestamp(ev[-1][0])).days < 10:
            continue
        ev.append([str(d.date()), round(float(rn2.iloc[i]), 2), round(float(rn2.iloc[i - 3:i].min()), 2),
                   fwd(nk, d, 1), fwd(nk, d, 5), fwd(nk, d, 20)])
f = pd.DataFrame(ev, columns=["date", "d", "drop", "f1", "f5", "f20"])
out["nk_rebound_events"] = dict(since="1990", n=int(len(f)), rows=ev,
                                f1_up=int((f.f1 > 0).sum()), f5_up=int((f.f5.dropna() > 0).sum()),
                                f20_up=int((f.f20.dropna() > 0).sum()), n20=int(f.f20.notna().sum()),
                                f5_med=round(float(f.f5.median()), 2), f20_med=round(float(f.f20.median()), 2),
                                f1_med=round(float(f.f1.median()), 2))
# Japan beta to SOX: Nikkei 11/24 vs SOX 11/23, compare with Nikkei 11/20 vs SOX 11/19
sox = px["^SOX"].dropna()
out["beta_sox"] = dict(sox_1119=round(float(ret(sox).loc["2026-11-19"]), 2), sox_1120=round(float(ret(sox).loc["2026-11-20"]), 2),
                       sox_1123=round(float(ret(sox).loc["2026-11-23"]), 2),
                       sox_since_1119=round(float((sox.loc["2026-11-23"] / sox.loc["2026-11-19"] - 1) * 100), 2))
# local index vs pre-crash close (11/19)
out["vs_1119"] = {t: round(float((px[t].dropna().iloc[-1] / px[t].dropna().loc["2026-11-19"] - 1) * 100), 2)
                  for t in ["^N225", "^KS11", "^TWII", "^HSI", "2330.TW", "005930.KS", "000660.KS", "JPY=X", "KRW=X", "TWD=X"]}

# ---------- 4. Intraday: 1306 / 1321 60m bars
bars = intr[intr.ticker.isin(["1306.T", "1321.T"])].copy()
bars["jst"] = bars.date.dt.tz_convert("Asia/Tokyo")
tb = {}
for t, g in bars[bars.jst.dt.date == ASOF.date()].groupby("ticker"):
    g = g.sort_values("jst")
    prev = float(jpc[t].dropna().iloc[-1])
    tb[t] = dict(prev=prev, prev_date=str(jpc[t].dropna().index[-1].date()),
                 open_pct=round((g.open.iloc[0] / prev - 1) * 100, 2),
                 high_pct=round((g.high.max() / prev - 1) * 100, 2),
                 high_time=g.loc[g.high.idxmax(), "jst"].strftime("%H:%M"),
                 last_bar_close_pct=round((g.close.iloc[-1] / prev - 1) * 100, 2),
                 path=[(r.jst.strftime("%H:%M"), round((r.close / prev - 1) * 100, 2)) for r in g.itertuples()])
    tb[t]["open_share_of_close"] = round(tb[t]["open_pct"] / tb[t]["last_bar_close_pct"] * 100, 1)
out["etf_today"] = tb
# NT ratio with reported TOPIX close (3764.88, +90.66; Kabutan/Kyodo)
topix_c, topix_chg = 3764.88, 90.66
topix_prev = topix_c - topix_chg
out["nt"] = dict(topix_d=round(topix_chg / topix_prev * 100, 2), nt=round(float(nk.iloc[-1]) / topix_c, 2),
                 nt_prev=round(float(nk.iloc[-2]) / topix_prev, 2))
# NT history with 1306 proxy (index level ratio ~ scale); percentile of today's NT change using 1306 to 11/20
t1306 = jpc["1306.T"].dropna().copy()
t1306.loc[ASOF] = float(bars[(bars.ticker == "1306.T") & (bars.jst.dt.date == ASOF.date())].close.iloc[-1])
nt = (nk / t1306.sort_index()).dropna()
ntr = (nt.pct_change() * 100).dropna()
ntr = ntr[ntr.abs() < 10]  # drop jumps from ETF unit changes / data errors
out["nt"]["nt_proxy_d"] = round(float(ntr.iloc[-1]), 2)
out["nt"]["nt_proxy_sigma"] = round(float(ntr.iloc[-1] / ntr.iloc[-251:-1].std()), 2)
out["nt"]["nt_proxy_n_bigger"] = int((ntr.iloc[:-1] >= ntr.iloc[-1]).sum())
out["nt"]["nt_proxy_since"] = str(ntr.index[0].date())
# contribution (reported): Advantest ~651, TEL ~322 of 2207.98
out["contrib_reported"] = dict(advantest=651, tel=322, total=2207.98,
                               share_two=round((651 + 322) / 2207.98 * 100, 1))
# Japanese stocks in daily.parquet
jst = {}
for t, nm in {"6857.T": "アドバンテスト", "8035.T": "東京エレクトロン", "285A.T": "キオクシア", "4062.T": "イビデン",
              "9984.T": "ソフトバンクG", "1570.T": "日経レバ", "1357.T": "日経ダブルインバース", "1489.T": "日経高配当50",
              "1343.T": "東証REIT", "2516.T": "グロース250ETF", "1545.T": "NASDAQ100 ETF", "2510.T": "国内債券ETF",
              "2558.T": "S&P500 ETF"}.items():
    s = px[t].dropna()
    base = s.loc[:"2026-11-19"].iloc[-1]
    jst[t] = dict(name=nm, close=round(float(s.iloc[-1]), 2), d1=round(float(ret(s).iloc[-1]), 2),
                  vs_1119=round(float((s.iloc[-1] / base - 1) * 100), 2), d_1120=round(float(ret(s).loc["2026-11-20"]), 2))
out["jp_stocks"] = jst
# 11/20 breadth from prices_jp (cleaned) for context
r20 = (jpc.loc["2026-11-20"] / jpc.loc[:"2026-11-19"].ffill().iloc[-1] - 1) * 100
out["breadth_1120"] = dict(n=int(r20.notna().sum()), down=int((r20 < 0).sum()))

# ---------- 5. Currencies / rates / commodities
fxo = {}
for t in ["JPY=X", "KRW=X", "TWD=X", "CNY=X", "IDR=X", "INR=X", "AUDUSD=X", "NKD=F", "ES=F", "NQ=F", "GC=F", "BZ=F", "NG=F", "^VIX"]:
    s = px[t].dropna()
    fxo[t] = dict(last=round(float(s.iloc[-1]), 4), date=str(s.index[-1].date()), d1=round(float(ret(s).iloc[-1]), 2),
                  sigma=sig(s)[1])
out["cross"] = fxo
out["nkd_vs_close"] = round(float(px["NKD=F"].dropna().iloc[-1] / nk.iloc[-1] - 1) * 100, 2)
# KRW: did won strengthen on a +6% KOSPI day? compare typical
kr = pd.DataFrame({"ks": ret(px["^KS11"]), "krw": ret(px["KRW=X"])}).dropna()
big = kr[(kr.ks >= 5) & (kr.index < ASOF) & (kr.index >= "2000-01-01")]
out["krw_on_big_kospi_days"] = dict(n=int(len(big)), med_krw=round(float(big.krw.median()), 2),
                                    today_krw=round(float(kr.krw.iloc[-1]), 2))

# ---------- 6. Margin top10: est P&L now vs. at 11/20 close (prior edition)
m = json.load(open(D + "margin_report.json"))
prev = {"285A": -48.0, "9984": -40.0, "8035": -30.5, "5803": -45.0}
out["margin_top"] = [[x["code"], x["name"], x["close"], x["est_cost"], x["est_pnl_pct"]] for x in m["top"]]
out["margin_agg"] = m["top_agg"]

json.dump(out, open("insights/data/analysis/asia_2026-11-24.json", "w"), ensure_ascii=False, indent=1, default=float)
print(json.dumps(out, ensure_ascii=False, default=float)[:12000])
