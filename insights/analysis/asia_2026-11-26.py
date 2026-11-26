"""Japan & Asia edition 2026-11-26: verification analyses.
Data: /tmp/market-data (GitHub Actions 2026-11-26 10:06 UTC, Yahoo Finance / JPX; manually triggered because the
scheduled fetch ran at 03:46 UTC before the Asian close), daily-review/data/prices_jp.parquet (to 2026-11-25 only).
Reported values (TOPIX close, breadth, contributions, Kioxia etc.) are hard-coded with their source noted.
"""
import json
import numpy as np
import pandas as pd

D = "/tmp/market-data/"
ASOF = pd.Timestamp("2026-11-26")
PREV = pd.Timestamp("2026-11-25")
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


# ---------- 0. snapshot with sigma, rank, intraday high/low
idx = {"^N225": "日経平均", "^KS11": "KOSPI", "^TWII": "台湾加権", "^HSI": "ハンセン", "000001.SS": "上海総合",
       "000300.SS": "CSI300", "^STI": "シンガポールSTI", "^JKSE": "インドネシア総合", "^KLSE": "マレーシアKLCI",
       "^AXJO": "豪ASX200", "^NSEI": "インドNifty50", "^BSESN": "SENSEX", "2330.TW": "TSMC", "005930.KS": "サムスン電子",
       "000660.KS": "SKハイニックス", "6857.T": "アドバンテスト", "8035.T": "東京エレクトロン", "9984.T": "ソフトバンクG",
       "285A.T": "キオクシア", "4062.T": "イビデン", "2516.T": "グロース250ETF", "1489.T": "日経高配当50ETF",
       "1343.T": "東証REIT ETF", "1570.T": "日経レバETF", "1545.T": "NASDAQ100ETF(東証)", "GC=F": "金先物"}
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
                   two_day=round(float((s.iloc[-1] / s.iloc[-3] - 1) * 100), 2),
                   vs_1119=round(float((s.iloc[-1] / s.loc[:"2026-11-19"].iloc[-1] - 1) * 100), 2),
                   from_1y_high=round(float((s.iloc[-1] / s.iloc[-252:].max() - 1) * 100), 1))
out["indices"] = snap

# ---------- 1. Intraday fade: Nikkei high vs close, 1306/1321 60m bars
nk = px["^N225"].dropna()
s = snap["^N225"]
out["nk_fade"] = dict(high_pct=s["high_pct"], close_pct=s["d1"], kept_share=round(s["d1"] / s["high_pct"] * 100, 1),
                      high_yen=round(float(hi["^N225"][ASOF]), 2), close=s["close"],
                      giveback_yen=round(float(hi["^N225"][ASOF] - nk.iloc[-1]), 2))
# history: Nikkei intraday high >= +2% but close kept <= 40% of the high (since 2000)
H = pd.DataFrame({"c": ret(nk), "h": (hi["^N225"].reindex(nk.index) / nk.shift(1) - 1) * 100}).dropna()
H = H[(H.index >= "2000-01-01")]
cand = H[(H.h >= 2) & (H.c > 0) & (H.c <= 0.4 * H.h) & (H.index < ASOF)]
out["nk_fade"]["hist"] = dict(n=int(len(cand)), n_hi2=int(((H.h >= 2) & (H.index < ASOF)).sum()),
                              next1_med=round(float(np.nanmedian([fwd(nk, d, 1) for d in cand.index if fwd(nk, d, 1) is not None])), 2),
                              next1_up=int(sum(1 for d in cand.index if (fwd(nk, d, 1) or 0) > 0)),
                              next5_med=round(float(np.nanmedian([fwd(nk, d, 5) for d in cand.index if fwd(nk, d, 5) is not None])), 2),
                              recent=[[str(d.date()), round(float(r.h), 2), round(float(r.c), 2), fwd(nk, d, 1), fwd(nk, d, 5)]
                                      for d, r in cand.tail(6).iterrows()])
bars = intr[intr.ticker.isin(["1306.T", "1321.T"])].copy()
bars["jst"] = bars.date.dt.tz_convert("Asia/Tokyo")
tb = {}
for t, gg in bars[bars.jst.dt.date == ASOF.date()].groupby("ticker"):
    gg = gg.sort_values("jst")
    prev = float(jpc[t].dropna().loc[PREV])
    tb[t] = dict(prev=prev, open_pct=round((gg.open.iloc[0] / prev - 1) * 100, 2),
                 high_pct=round((gg.high.max() / prev - 1) * 100, 2), high_time=gg.loc[gg.high.idxmax(), "jst"].strftime("%H:%M"),
                 low_pct=round((gg.low.min() / prev - 1) * 100, 2), low_time=gg.loc[gg.low.idxmin(), "jst"].strftime("%H:%M"),
                 last_pct=round((gg.close.iloc[-1] / prev - 1) * 100, 2),
                 path=[(r.jst.strftime("%H:%M"), round((r.close / prev - 1) * 100, 2)) for r in gg.itertuples()])
out["etf_today"] = tb

# ---------- 2. Index-led rise: NT ratio, mirror of 11/25 (reported TOPIX)
topix = {"2026-11-25": 3746.20, "2026-11-26": 3750.40}          # reported (Nikkei / Reuters via search)
tp_d = (topix["2026-11-26"] / topix["2026-11-25"] - 1) * 100
nt = float(nk.iloc[-1]) / topix["2026-11-26"]
nt_prev = float(nk.iloc[-2]) / topix["2026-11-25"]
out["nt"] = dict(topix_d=round(tp_d, 2), nt=round(nt, 3), nt_prev=round(nt_prev, 3), nt_chg_pct=round((nt / nt_prev - 1) * 100, 2),
                 gap_pt=round(snap["^N225"]["d1"] - tp_d, 2))
t1306 = jpc["1306.T"].dropna()
g = pd.DataFrame({"nk": ret(nk), "tp": ret(t1306)}).dropna()
g = g[g.tp.abs() < 15]
g["gap"] = g.nk - g.tp
# 11/25 gap from previous edition used reported TOPIX (-0.50%) -> -2.29pt
g.loc[PREV, "gap"] = -2.29
gp = g.gap
nxt = gp.shift(-1)
big_neg = gp[(gp <= -1.5) & (gp.index < PREV)]
out["nt"]["after_big_neg_gap"] = dict(rule="日経平均-TOPIX代用(1306)の差が-1.5pt以下の翌日", n=int(len(big_neg)),
                                      next_gap_pos=int((nxt.loc[big_neg.index] > 0).sum()),
                                      next_gap_med=round(float(nxt.loc[big_neg.index].median()), 2),
                                      next_gap_ge_075=int((nxt.loc[big_neg.index] >= 0.75).sum()),
                                      rows=[[str(d.date()), round(float(v), 2), round(float(nxt.loc[d]), 2)] for d, v in big_neg.items()])
out["nt"]["two_day"] = dict(nikkei=snap["^N225"]["two_day"],
                            topix=round((topix["2026-11-26"] / (3746.20 + 18.68) - 1) * 100, 2))
# reported breadth / contributions (kabutan, nikkei): prime adv 749 / dec 751 / unch 52; 17 of 33 sectors up;
# top5 positive contributors (Advantest, SBG, Kioxia, TDK, TEL) ~ +512 yen; Advantest ~326 yen; Advantest+SBG ~393 yen;
# top5 negative ~ -107 yen, Fast Retailing ~ -54 yen
out["breadth_reported"] = dict(adv=749, dec=751, unch=52, adv_share=round(749 / (749 + 751 + 52) * 100, 1),
                               top5_plus=512, total=487.54, rest=round(487.54 - 512, 1), advantest=326, adv_sbg=393,
                               top5_minus=-107, fast_retailing=-54, sectors_up=17,
                               prev_day=dict(adv=993, dec=537, top5_drag=-1905, total=-1633.01, rest=272))
etf = {}
for t in ["2516.T", "1489.T", "1343.T", "1570.T"]:
    s2 = px[t].dropna()
    etf[t] = [round(float(ret(s2).loc[PREV]), 2), round(float(ret(s2).iloc[-1]), 2)]
out["style_flip"] = etf

# ---------- 3. North Asia whipsaw: consecutive sign alternations
alt = {}
for t in ["^N225", "^KS11", "^TWII", "^HSI"]:
    r = ret(px[t]).dropna()
    r = r[r.index >= "2000-01-01"]
    sg = np.sign(r)
    flips = (sg != sg.shift(1)).astype(int)
    # current streak of alternating signs
    k = 0
    for v in flips.iloc[::-1]:
        if v:
            k += 1
        else:
            break
    streak = k + 1  # number of days in the alternating run
    # historical distribution of alternating-run length
    runs, cur = [], 1
    for v in flips.iloc[1:]:
        if v:
            cur += 1
        else:
            runs.append(cur)
            cur = 1
    runs = np.array(runs)
    absmean = float(r.iloc[-streak:].abs().mean())
    alt[t] = dict(streak_days=int(streak), share_runs_ge=round(float((runs >= streak).mean() * 100), 2),
                  n_runs_ge=int((runs >= streak).sum()), n_runs=int(len(runs)),
                  last_days=[[str(d.date()), round(float(v), 2)] for d, v in r.iloc[-max(streak, 6):].items()],
                  mean_abs_in_run=round(absmean, 2), mean_abs_250=round(float(r.iloc[-250:].abs().mean()), 2))
out["alternation"] = alt
# sum of |moves| vs net since 11/19 (churn ratio)
ch = {}
for t in ["^N225", "^KS11", "^TWII", "^HSI", "^NSEI"]:
    s2 = px[t].dropna().loc["2026-11-19":]
    r = ret(s2).dropna()
    ch[t] = dict(days=int(len(r)), sum_abs=round(float(r.abs().sum()), 2), net=round(float((s2.iloc[-1] / s2.iloc[0] - 1) * 100), 2))
out["churn_since_1119"] = ch

# ---------- 4. Taiwan: index up, TSMC down
tw = pd.DataFrame({"tw": ret(px["^TWII"]), "tsmc": ret(px["2330.TW"])}).dropna()
tw = tw[tw.index >= "2000-01-01"]
c = tw[(tw.tw >= 2) & (tw.tsmc <= 0) & (tw.index < ASOF)]
out["tw_ex_tsmc"] = dict(n_tw_ge2=int(((tw.tw >= 2) & (tw.index < ASOF)).sum()), n_with_tsmc_le0=int(len(c)),
                         rows=[[str(d.date()), round(float(r.tw), 2), round(float(r.tsmc), 2)] for d, r in c.iterrows()],
                         spread_today=round(float(tw.tw.iloc[-1] - tw.tsmc.iloc[-1]), 2),
                         spread_sd=round(float((tw.tw - tw.tsmc).iloc[-251:-1].std()), 2))
out["tw_ex_tsmc"]["spread_sigma"] = round(out["tw_ex_tsmc"]["spread_today"] / out["tw_ex_tsmc"]["spread_sd"], 2)
# reported (UDN / Yahoo TW): TAIEX +956.38 to 39,151.81, turnover ~817.5bn TWD, OTC index +4%+, TSMC 2,145 (-0.23%)
# Korea vs Taiwan rebound after 11/25
out["rebound_vs_1125"] = {t: dict(d1125=snap[t]["prev_d1"], d1126=snap[t]["d1"],
                                  recovered=round(-snap[t]["d1"] / snap[t]["prev_d1"] * 100, 1) if snap[t]["prev_d1"] < 0 else None)
                          for t in ["^N225", "^KS11", "^TWII", "^HSI", "000001.SS", "2330.TW", "005930.KS", "000660.KS", "6857.T", "8035.T", "9984.T", "285A.T"]}

# ---------- 5. KOSPI: day after a <= -5% drop
ks = px["^KS11"].dropna()
rk = ret(ks).dropna()
rk = rk[rk.index >= "2000-01-01"]
ev = rk[(rk <= -5) & (rk.index < PREV)]
nx = [fwd(ks, d, 1) for d in ev.index]
nx = [x for x in nx if x is not None]
out["kospi_after_crash"] = dict(n=len(nx), next_med=round(float(np.median(nx)), 2), next_up=int(sum(x > 0 for x in nx)),
                                today=snap["^KS11"]["d1"], rank_le_today=int(sum(x <= snap["^KS11"]["d1"] for x in nx)),
                                intraday_high=snap["^KS11"]["high_pct"])
krw = px["KRW=X"].dropna()
out["krw"] = dict(last=round(float(krw.iloc[-1]), 2), d1=round(float(ret(krw).iloc[-1]), 2),
                  d_1119=round(float((krw.iloc[-1] / krw.loc[:"2026-11-19"].iloc[-1] - 1) * 100), 2))
# reported: BOK raised base rate 3.00 -> 3.25% (5-2 vote), 2026 GDP forecast 3.3 -> 3.9%; KOSPI intraday 4,817.77,
# foreigners net sold 109.6bn KRW, individuals -1,043.8bn, institutions +750.8bn (Yonhap via etoday/shinailbo)

# ---------- 6. Cross-asset: yen, futures, gold
fxo = {}
for t in ["JPY=X", "KRW=X", "TWD=X", "CNY=X", "INR=X", "IDR=X", "AUDUSD=X", "NKD=F", "ES=F", "GC=F", "SI=F", "BZ=F", "^VIX", "BTC-USD"]:
    s2 = px[t].dropna()
    r = ret(s2).dropna()
    fxo[t] = dict(last=round(float(s2.iloc[-1]), 4), date=str(s2.index[-1].date()), d1=round(float(r.iloc[-1]), 2),
                  sigma=round(float(r.iloc[-1] / r.iloc[-251:-1].std()), 2))
out["cross"] = fxo
out["nkd_vs_close"] = round(float(px["NKD=F"].dropna().iloc[-1] / nk.iloc[-1] - 1) * 100, 2)
gc = px["GC=F"].dropna()
out["gold"] = dict(last=round(float(gc.iloc[-1]), 1), d1=round(float(ret(gc).iloc[-1]), 2),
                   from_1y_high=round(float((gc.iloc[-1] / gc.iloc[-252:].max() - 1) * 100), 1),
                   d_21=round(float((gc.iloc[-1] / gc.iloc[-22] - 1) * 100), 2))
for t in ["NVDA", "^SOX", "SMH", "DELL", "MU"]:
    s2 = px[t].dropna()
    out.setdefault("us_1125", {})[t] = dict(date=str(s2.index[-1].date()), d1=round(float(ret(s2).iloc[-1]), 2),
                                            prev=round(float(ret(s2).iloc[-2]), 2))

# ---------- 7. Margin: top holders (11/25 application data) re-marked at 11/26 close
m = json.load(open(D + "margin_report.json"))
out["margin_top"] = [[x["code"], x["name"], x["close"], x["est_cost"], x["est_pnl_pct"], x["buy_chg_1d_pct"], x["buy_chg_5d_pct"]]
                     for x in m["top"]]
out["margin_agg"] = m["top_agg"]
out["margin_agg_prev"] = {"edition 11/24 (11/20 data, 11/24 close)": -23.1, "edition 11/25 (11/24 data, 11/25 close)": -28.8}
out["margin_top_buy_up_on_1125"] = [x["code"] for x in m["top"] if x["buy_chg_1d_pct"] > 0]
# price move needed for top names to reach estimated cost
out["to_cost"] = {x["code"]: round((x["est_cost"] / x["close"] - 1) * 100, 1) for x in m["top"]}
out["margin_total"] = {k: v for k, v in m["total"].items() if not k.startswith("series")}
out["individuals"] = m["individuals"]["weeks"][:2]
# reported: Matsui in-house margin buy valuation -22.7% (11/20) -> -19.7% (11/24) (Bloomberg 2026-11-24)

json.dump(out, open("insights/data/analysis/asia_2026-11-26.json", "w"), ensure_ascii=False, indent=1, default=float)
print(json.dumps(out, ensure_ascii=False, default=float))
