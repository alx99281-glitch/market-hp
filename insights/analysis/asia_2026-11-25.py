"""Japan & Asia edition 2026-11-25: verification analyses.
Data: /tmp/market-data (GitHub Actions 2026-11-25 10:07 UTC, Yahoo Finance / JPX; manual trigger),
daily-review/data/prices_jp.parquet (to 2026-11-24 only; 11/25 constituent data not available).
Reported values (TOPIX close, contributions, sector moves) are hard-coded with their source noted.
"""
import json
import numpy as np
import pandas as pd

D = "/tmp/market-data/"
ASOF = pd.Timestamp("2026-11-25")
PREV = pd.Timestamp("2026-11-24")
out = {}
daily = pd.read_parquet(D + "daily.parquet")
px = daily.pivot_table(index="date", columns="ticker", values="close")
lo = daily.pivot_table(index="date", columns="ticker", values="low")
hi = daily.pivot_table(index="date", columns="ticker", values="high")
intr = pd.read_parquet(D + "intraday_60m.parquet")
jp = pd.read_parquet("daily-review/data/prices_jp.parquet")
jpc = jp.pivot_table(index="date", columns="ticker", values="close")


def ret(s):
    return s.dropna().pct_change() * 100


def fwd(s, dt, k):
    s = s.dropna()
    i = s.index.get_loc(dt)
    return round(float((s.iloc[i + k] / s.iloc[i] - 1) * 100), 2) if i + k < len(s) else None


# ---------- 0. index snapshot with sigma, rank, intraday low
idx = {"^N225": "日経平均", "^KS11": "KOSPI", "^TWII": "台湾加権", "^HSI": "ハンセン", "000001.SS": "上海総合",
       "^STI": "シンガポールSTI", "^JKSE": "インドネシア総合", "^KLSE": "マレーシアKLCI", "^AXJO": "豪ASX200",
       "^NSEI": "インドNifty50", "^SET.BK": "タイSET", "2330.TW": "TSMC", "005930.KS": "サムスン電子",
       "000660.KS": "SKハイニックス", "6857.T": "アドバンテスト", "8035.T": "東京エレクトロン", "9984.T": "ソフトバンクG",
       "285A.T": "キオクシア", "4062.T": "イビデン"}
snap = {}
for t, nm in idx.items():
    s = px[t].dropna()
    r = ret(s).dropna()
    r = r[r.index >= "2000-01-01"]
    if len(r) < 3:
        print("skip", t, len(r))
        continue
    h = r.iloc[:-1]
    cur = float(r.iloc[-1])
    sd = float(h.iloc[-250:].std())
    prev = float(s.iloc[-2])
    low = lo[t].get(s.index[-1], np.nan)
    hig = hi[t].get(s.index[-1], np.nan)
    snap[t] = dict(name=nm, date=str(s.index[-1].date()), close=round(float(s.iloc[-1]), 2), d1=round(cur, 2),
                   prev_d1=round(float(r.iloc[-2]), 2), sigma=round(cur / sd, 2),
                   n_days=int(len(h)), n_as_big=int((h <= cur).sum() if cur < 0 else (h >= cur).sum()),
                   low_pct=round((low / prev - 1) * 100, 2) if low == low else None,
                   high_pct=round((hig / prev - 1) * 100, 2) if hig == hig else None,
                   vs_1119=round(float((s.iloc[-1] / s.loc[:"2026-11-19"].iloc[-1] - 1) * 100), 2),
                   two_day=round(float((s.iloc[-1] / s.iloc[-3] - 1) * 100), 2),
                   from_1y_high=round(float((s.iloc[-1] / s.iloc[-252:].max() - 1) * 100), 1))
out["indices"] = snap

# ---------- 1. Index-led drop: NT ratio, reported breadth and contributions
nk = px["^N225"].dropna()
topix_c, topix_chg = 3746.20, -18.68          # reported (Nikkei / media-ir)
topix_prev = topix_c - topix_chg              # 3764.88 (matches 11/24 reported close)
nt_today, nt_prev = float(nk.iloc[-1]) / topix_c, float(nk.iloc[-2]) / topix_prev
out["nt"] = dict(topix_d=round(topix_chg / topix_prev * 100, 2), nt=round(nt_today, 3), nt_prev=round(nt_prev, 3),
                 nt_chg_pct=round((nt_today / nt_prev - 1) * 100, 2),
                 gap_pt=round(float(ret(nk).iloc[-1]) - topix_chg / topix_prev * 100, 2))
# history of the daily gap (Nikkei % - TOPIX %) using 1306.T as TOPIX proxy (prices_jp, ~3y)
t1306 = jpc["1306.T"].dropna()
g = pd.DataFrame({"nk": ret(nk), "tp": ret(t1306)}).dropna()
g = g[(g.tp.abs() < 15)]
g["gap"] = g.nk - g.tp
gap_today = out["nt"]["gap_pt"]
out["nt"]["gap_hist"] = dict(since=str(g.index[0].date()), n=int(len(g)), n_le_today=int((g.gap <= gap_today).sum()),
                             min=round(float(g.gap.min()), 2), min_date=str(g.gap.idxmin().date()),
                             sd=round(float(g.gap.std()), 2), sigma_today=round(gap_today / float(g.gap.std()), 2),
                             worst=[[str(d.date()), round(float(r.nk), 2), round(float(r.tp), 2), round(float(r.gap), 2)]
                                    for d, r in g.sort_values("gap").head(6).iterrows()])
# days with Nikkei <= -2.5% but TOPIX proxy >= -0.75% (past 3y)
c = g[(g.nk <= -2.5) & (g.tp >= -0.75)]
out["nt"]["similar"] = [[str(d.date()), round(float(r.nk), 2), round(float(r.tp), 2), fwd(nk, d, 1), fwd(nk, d, 5)]
                        for d, r in c.iterrows()]
# reported: prime adv/dec 993/537; kabutan contribution: top5 drag ~1,905 yen; Advantest ~761; Fast Retailing +172
out["breadth_reported"] = dict(adv=993, dec=537, adv_share=round(993 / (993 + 537) * 100, 1),
                               top5_drag=1905, total=-1633.01, rest=round(-1633.01 + 1905, 0),
                               advantest=761, fast_retailing_plus=172, two_drag=1328)

# ---------- 2. Full giveback: +5% then -5% next day (since 2000)
rev = {}
for t in ["^KS11", "^TWII", "^N225", "^HSI"]:
    r = ret(px[t]).dropna()
    r = r[r.index >= "2000-01-01"]
    prev = r.shift(1)
    thr_up, thr_dn = {"^KS11": (5, -5), "^TWII": (5, -4), "^N225": (3.5, -2.5), "^HSI": (3, -3)}[t]
    m = r[(prev >= thr_up) & (r <= thr_dn)]
    rev[t] = dict(rule=f"前日{thr_up}%以上上昇→当日{thr_dn}%以下", n=int(len(m)),
                  rows=[[str(d.date()), round(float(prev.loc[d]), 2), round(float(v), 2), fwd(px[t], d, 5), fwd(px[t], d, 20)]
                        for d, v in m.items()])
    # share of previous day's gain given back
    s = px[t].dropna()
    rev[t]["giveback_pct"] = round(float((s.iloc[-2] - s.iloc[-1]) / (s.iloc[-2] - s.iloc[-3]) * 100), 1)
out["reversal"] = rev
# correlation of consecutive-day returns across N. Asia (rolling 60d) for context
a = pd.DataFrame({k: ret(px[k]) for k in ["^N225", "^KS11", "^TWII", "^HSI", "^NSEI"]}).dropna()
out["corr60"] = a.tail(60).corr().round(2).to_dict()

# ---------- 3. Intraday: 1306 / 1321 60m bars (TOPIX vs Nikkei ETFs)
bars = intr[intr.ticker.isin(["1306.T", "1321.T"])].copy()
bars["jst"] = bars.date.dt.tz_convert("Asia/Tokyo")
tb = {}
for t, gg in bars[bars.jst.dt.date == ASOF.date()].groupby("ticker"):
    gg = gg.sort_values("jst")
    prev = float(jpc[t].dropna().loc[PREV])
    tb[t] = dict(prev=prev, open_pct=round((gg.open.iloc[0] / prev - 1) * 100, 2),
                 low_pct=round((gg.low.min() / prev - 1) * 100, 2), low_time=gg.loc[gg.low.idxmin(), "jst"].strftime("%H:%M"),
                 high_pct=round((gg.high.max() / prev - 1) * 100, 2),
                 last_pct=round((gg.close.iloc[-1] / prev - 1) * 100, 2),
                 path=[(r.jst.strftime("%H:%M"), round((r.close / prev - 1) * 100, 2)) for r in gg.itertuples()])
out["etf_today"] = tb
# Nikkei intraday low vs close: share of drawdown recovered
s = out["indices"]["^N225"]
out["nk_recovery"] = dict(low_pct=s["low_pct"], close_pct=s["d1"],
                          recovered_share=round((1 - s["d1"] / s["low_pct"]) * 100, 1) if s["low_pct"] else None)
# Taiwan / TSMC / Korea low-vs-close
out["lower_shadow"] = {t: dict(low=snap[t]["low_pct"], close=snap[t]["d1"],
                               recovered=round((1 - snap[t]["d1"] / snap[t]["low_pct"]) * 100, 1) if snap[t]["low_pct"] else None)
                       for t in ["^TWII", "2330.TW", "^KS11", "005930.KS", "000660.KS", "^N225", "^HSI"]}
# Taiwan: past days with intraday low <= -7% (since 2000): close and next 5d
tw = px["^TWII"].dropna()
twl = (lo["^TWII"].reindex(tw.index) / tw.shift(1) - 1) * 100
ev = twl[(twl <= -7) & (twl.index >= "2000-01-01") & (twl.index < ASOF)]
out["tw_deep_intraday"] = [[str(d.date()), round(float(v), 2), round(float(ret(tw).loc[d]), 2), fwd(tw, d, 1), fwd(tw, d, 5)]
                           for d, v in ev.items()]

# ---------- 4. India: catch-up after the 11/24 holiday vs North Asia 2-day
two = {}
for t in ["^NSEI", "^BSESN", "^KS11", "^TWII", "^N225", "^HSI", "000001.SS", "^STI", "^JKSE", "^AXJO"]:
    s = px[t].dropna()
    base = s.loc[:"2026-11-23"].iloc[-1]
    two[t] = dict(since_1123=round(float((s.iloc[-1] / base - 1) * 100), 2), base_date=str(s.loc[:"2026-11-23"].index[-1].date()))
out["two_day_since_1123"] = two
for t in ["INDA", "EWY", "EWT", "EWJ"]:
    if t in px:
        s = px[t].dropna()
        out.setdefault("us_etf_1124", {})[t] = round(float(ret(s).loc["2026-11-24"]), 2)
# history: KOSPI <= -4% and Nifty >= +1% same day
b = pd.DataFrame({"ks": ret(px["^KS11"]), "ni": ret(px["^NSEI"]), "tw": ret(px["^TWII"])}).dropna()
hb = b[(b.index < ASOF) & (b.ks <= -4)]
out["india_vs_kospi"] = dict(n_kospi_le4=int(len(hb)), n_nifty_ge1=int((hb.ni >= 1).sum()),
                             nifty_med_on_those=round(float(hb.ni.median()), 2),
                             rows=[[str(d.date()), round(float(r.ks), 2), round(float(r.ni), 2)] for d, r in hb[hb.ni >= 1].iterrows()],
                             corr60=round(float(b.tail(60).ks.corr(b.tail(60).ni)), 2),
                             corr250=round(float(b.tail(250).ks.corr(b.tail(250).ni)), 2))
inr = px["INR=X"].dropna()
out["inr"] = dict(last=round(float(inr.iloc[-1]), 3), d1=round(float(ret(inr).iloc[-1]), 2))

# ---------- 5. Defensive rotation: pharma sector ETF history (TOPIX-17 医薬品 1621.T, ~3y)
ph = ret(jpc["1621.T"]).dropna()
ph = ph[ph.abs() < 15]
out["pharma_hist"] = dict(since=str(ph.index[0].date()), n=int(len(ph)), n_ge_5=int((ph >= 5).sum()),
                          max=round(float(ph.max()), 2), max_date=str(ph.idxmax().date()),
                          sd=round(float(ph.std()), 2), reported_today=5.48,
                          sigma_today=round(5.48 / float(ph.iloc[-250:].std()), 2))
# other defensive proxies in daily.parquet
dfn = {}
for t, nm in {"1489.T": "日経高配当50", "1343.T": "東証REIT", "2516.T": "グロース250ETF", "1570.T": "日経レバ",
              "2510.T": "国内債券ETF"}.items():
    s = px[t].dropna()
    dfn[t] = dict(name=nm, d1=round(float(ret(s).iloc[-1]), 2), date=str(s.index[-1].date()))
out["jp_etfs"] = dfn

# ---------- 6. FX / futures: did the yen act as a haven?
fxo = {}
for t in ["JPY=X", "KRW=X", "TWD=X", "CNY=X", "INR=X", "IDR=X", "AUDUSD=X", "NKD=F", "ES=F", "NQ=F", "GC=F", "BZ=F", "^VIX", "^TNX"]:
    s = px[t].dropna()
    r = ret(s).dropna()
    fxo[t] = dict(last=round(float(s.iloc[-1]), 4), date=str(s.index[-1].date()), d1=round(float(r.iloc[-1]), 2),
                  sigma=round(float(r.iloc[-1] / r.iloc[-251:-1].std()), 2))
out["cross"] = fxo
out["nkd_vs_close"] = round(float(px["NKD=F"].dropna().iloc[-1] / nk.iloc[-1] - 1) * 100, 2)
jy = pd.DataFrame({"nk": ret(nk), "jpy": ret(px["JPY=X"])}).dropna()
big = jy[(jy.nk <= -2.5) & (jy.index < ASOF) & (jy.index >= "2010-01-01")]
out["yen_on_big_down"] = dict(n=int(len(big)), med_usdjpy=round(float(big.jpy.median()), 2),
                              share_yen_weaker=round(float((big.jpy > 0).mean() * 100), 1),
                              today=round(float(jy.jpy.iloc[-1]), 2))
kr = pd.DataFrame({"ks": ret(px["^KS11"]), "krw": ret(px["KRW=X"])}).dropna()
bk = kr[(kr.ks <= -5) & (kr.index < ASOF) & (kr.index >= "2000-01-01")]
out["krw_on_big_down"] = dict(n=int(len(bk)), med_usdkrw=round(float(bk.krw.median()), 2), today=round(float(kr.krw.iloc[-1]), 2))

# ---------- 7. Margin: top holders re-marked; compare with previous editions
m = json.load(open(D + "margin_report.json"))
out["margin_top"] = [[x["code"], x["name"], x["close"], x["est_cost"], x["est_pnl_pct"], x["buy_chg_1d_pct"], x["buy_chg_5d_pct"]]
                     for x in m["top"]]
out["margin_agg"] = m["top_agg"]
out["margin_agg_prev"] = {"2026-11-20 close (11/19 data, edition 11/20)": -28.5,
                          "2026-11-24 close (11/20 data, edition 11/24)": -23.1}
# daily moves of top margin names on 11/25 where available
mv = {}
for code in [x["code"] for x in m["top"]]:
    t = code + ".T"
    if t in px:
        mv[code] = round(float(ret(px[t]).iloc[-1]), 2)
    elif t in jpc:
        mv[code] = None
out["margin_top_d1"] = mv
out["margin_total"] = {k: v for k, v in m["total"].items() if not k.startswith("series")}
out["individuals"] = m["individuals"]["weeks"][:2]

json.dump(out, open("insights/data/analysis/asia_2026-11-25.json", "w"), ensure_ascii=False, indent=1, default=float)
print(json.dumps(out, ensure_ascii=False, default=float))
