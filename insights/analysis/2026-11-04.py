"""分析の視点 2026-11-04 号の検証スクリプト。
入力: /tmp/market-data/daily.parquet, daily-review/data/prices.parquet, prices_jp.parquet
出力: insights/data/analysis/2026-11-04.json
注意: daily.parquet の 11/4 アジア分は取引時間中の値のため、全系列を 2026-11-03 で打ち切る。
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CUT = pd.Timestamp("2026-11-03")
d = pd.read_parquet("/tmp/market-data/daily.parquet")
W = d.pivot(index="date", columns="ticker", values="close").sort_index().loc[:CUT]
us = pd.read_parquet(ROOT / "daily-review/data/prices.parquet")
U = us.pivot(index="date", columns="ticker", values="adj_close").sort_index().loc[:CUT]
out = {}

def r(s):
    return s.dropna().pct_change() * 100

def fwd(s, dates, n):
    s = s.dropna(); res = []
    for t in dates:
        if t in s.index:
            i = s.index.get_loc(t)
            if i + n < len(s):
                res.append((s.iloc[i + n] / s.iloc[i] - 1) * 100)
    return np.array(res)

def stat(a):
    a = np.asarray(a, float); a = a[~np.isnan(a)]
    if len(a) == 0:
        return {"n": 0}
    t = a.mean() / (a.std(ddof=1) / np.sqrt(len(a))) if len(a) > 2 else None
    return {"n": int(len(a)), "mean": round(float(a.mean()), 2), "median": round(float(np.median(a)), 2),
            "up": round(float((a > 0).mean()), 2), "t": None if t is None else round(float(t), 2)}

def declump(dates, gap=20):
    """同じ局面の重複を避けるため、直前の採用日から gap 営業日以内のイベントを除く"""
    keep = []; idx = W.index
    for t in dates:
        if not keep or idx.get_loc(t) - idx.get_loc(keep[-1]) > gap:
            keep.append(t)
    return keep

# ---- A. 調整局面(NDX 高値から-10%以上)での SOX +2.5%以上の反発日 ----
ndx, sox = W["^NDX"].dropna(), W["^SOX"].dropna()
dd = (ndx / ndx.cummax() - 1) * 100
rs = r(sox)
sdd = (sox / sox.cummax() - 1) * 100
# 定義: SOX が +2.5%以上、かつ前日の SOX が高値から-20%以上下落していた日。
# 局面の重複を避けるため、直前の採用日から60営業日以内の反発日は除く(局面ごとの最初の反発)。
ev_hist = [t for t in rs.index[1:] if rs[t] >= 2.5 and sdd.shift(1).get(t, 0) <= -20 and t < pd.Timestamp("2026-11-03")]
first = declump(ev_hist, gap=60)
a = {"now": {"sox_ret": round(float(rs.iloc[-1]), 2), "ndx_dd": round(float(dd.iloc[-1]), 2),
             "ndx_dd_prevday": round(float(dd.iloc[-2]), 2),
             "sox_dd_prevday": round(float(sdd.iloc[-2]), 2), "sox_dd": round(float(sdd.iloc[-1]), 2)},
     "definition": "SOX>=+2.5% かつ前日SOXが高値比-20%以下。2000年以降",
     "n_events_all": len(ev_hist), "n_first_in_episode": len(first)}
for n in (5, 20, 60):
    a[f"sox_fwd{n}_all"] = stat(fwd(sox, ev_hist, n))
    a[f"sox_fwd{n}_first"] = stat(fwd(sox, first, n))
    a[f"sox_fwd{n}_uncond"] = stat(fwd(sox, list(sox.index[::5]), n))
brk = []
for t in first:
    i = sox.index.get_loc(t)
    if i + 20 < len(sox):
        brk.append(float(sox.iloc[i + 1:i + 21].min() < sox.iloc[i - 1]))
a["first_break_prior_close_within20"] = round(float(np.mean(brk)), 2) if brk else None
a["first_ex_2000_2002_2008"] = {f"fwd{n}": stat(fwd(sox, [t for t in first if not (t.year in (2000, 2001, 2002, 2008))], n)) for n in (20, 60)}
a["first_dates"] = [str(x.date()) for x in first]
# 11/3 の広がり: SOX上昇日に RSP/XLP がどう動いたか
a["nov3"] = {k: round(float(r(W[k]).iloc[-1]), 2) for k in ["^SOX", "SMH", "SNDK", "CRWV", "NBIS", "^NDX", "^GSPC", "RSP", "XLP", "XLB", "XLU", "IWM", "^VIX", "^TNX", "HYG"]}
out["A_sox_rebound"] = a

# ---- B. 東京休場明け: 米国2日分をどう織り込むか ----
n225 = W["^N225"].dropna()
spx, nkd = W["^GSPC"].dropna(), W["NKD=F"].dropna()
rows = []
for k in range(1, len(n225)):
    t0, t1 = n225.index[k - 1], n225.index[k]
    # 東京の前営業日と当日の間に入った米国の引け(前日の米国引けまで)
    usd = spx.loc[(spx.index >= t0) & (spx.index < t1)]
    if len(usd) == 0:
        continue
    s0 = spx.loc[:t0 - pd.Timedelta(days=1)]
    if len(s0) == 0:
        continue
    base = s0.iloc[-1]
    soxb = sox.loc[:t0 - pd.Timedelta(days=1)]
    if len(soxb) == 0:
        continue
    rows.append({"date": t1, "n_us": len(usd), "us_cum": (usd.iloc[-1] / base - 1) * 100,
                 "us_last": (usd.iloc[-1] / spx.loc[:usd.index[-1] - pd.Timedelta(days=1)].iloc[-1] - 1) * 100,
                 "sox_cum": (sox.loc[:usd.index[-1]].iloc[-1] / soxb.iloc[-1] - 1) * 100,
                 "nk": (n225.iloc[k] / n225.iloc[k - 1] - 1) * 100})
B = pd.DataFrame(rows).set_index("date").loc["2010":]
b = {}
for lab, sub in {"normal_1day": B[B.n_us == 1], "after_jp_holiday_2plus_us": B[B.n_us >= 2]}.items():
    X = np.c_[np.ones(len(sub)), sub.us_cum]
    beta = np.linalg.lstsq(X, sub.nk, rcond=None)[0]
    X2 = np.c_[np.ones(len(sub)), sub.us_cum - sub.us_last, sub.us_last]
    beta2 = np.linalg.lstsq(X2, sub.nk, rcond=None)[0]
    b[lab] = {"n": int(len(sub)), "beta_nk_on_spx_cum": round(float(beta[1]), 2),
              "beta_earlier_days": round(float(beta2[1]), 2), "beta_last_day": round(float(beta2[2]), 2),
              "corr_nk_spx_cum": round(float(np.corrcoef(sub.nk, sub.us_cum)[0, 1]), 2),
              "corr_nk_sox_cum": round(float(np.corrcoef(sub.nk, sub.sox_cum)[0, 1]), 2)}
# 今回: 東京 11/2 引け後の米国 11/2・11/3
b["now"] = {"spx_2day": round(float((spx.loc["2026-11-03"] / spx.loc["2026-10-30"] - 1) * 100), 2),
            "sox_2day": round(float((sox.loc["2026-11-03"] / sox.loc["2026-10-30"] - 1) * 100), 2),
            "spx_nov3": round(float(r(spx).loc["2026-11-03"]), 2), "sox_nov3": round(float(rs.loc["2026-11-03"]), 2)}
# 韓国は 11/3 に 11/2 の米国安を先に織り込んだ
b["korea_nov3"] = {k: (round(float(r(W[k]).loc["2026-11-03"]), 2) if pd.Timestamp("2026-11-03") in W[k].dropna().index else "11/3のデータなし")
                   for k in ["000660.KS", "005930.KS", "^KS11", "2330.TW", "^TWII"]}
# 韓国(11/3) -> 日本(11/4)の材料の重なり: SKハイニックス日次と前日SOXの回帰(直近1年)
hx = r(W["000660.KS"]).loc["2025-11":]
prev_sox = rs.shift(0)
pairs = []
for t in hx.index:
    s_ = rs.loc[:t - pd.Timedelta(days=1)]
    if len(s_):
        pairs.append((hx[t], s_.iloc[-1]))
pp = np.array(pairs)
b["hynix_on_prev_sox_1y"] = {"n": len(pp), "beta": round(float(np.polyfit(pp[:, 1], pp[:, 0], 1)[0]), 2),
                            "corr": round(float(np.corrcoef(pp[:, 0], pp[:, 1])[0, 1]), 2)}
# 東エレク・アドバンテストの前日SOX感応度(直近1年)
for tk in ["8035.T", "6857.T", "285A.T"]:
    x = r(W[tk]).loc["2025-11":]; pr = []
    for t in x.index:
        s_ = rs.loc[:t - pd.Timedelta(days=1)]
        if len(s_):
            pr.append((x[t], s_.iloc[-1]))
    pr = np.array(pr)
    b[f"{tk}_on_prev_sox_1y"] = {"n": len(pr), "beta": round(float(np.polyfit(pr[:, 1], pr[:, 0], 1)[0]), 2),
                                 "corr": round(float(np.corrcoef(pr[:, 0], pr[:, 1])[0, 1]), 2)}
out["B_holiday_catchup"] = b

# ---- C. Apple のメモリコスト: 部材の買い手と売り手 ----
mem = ["MU", "SNDK", "WDC", "STX"]
hw = ["AAPL", "DELL", "HPQ"]
Ur = U.pct_change() * 100
c = {"last_us_date_in_sp500_file": str(U["AAPL"].dropna().index[-1].date())}
for per, start in {"ytd": "2025-12-31", "1y": "2025-11-03", "3m": "2026-08-03"}.items():
    seg = U.loc[start:]
    c[per] = {k: round(float((seg[k].dropna().iloc[-1] / seg[k].dropna().iloc[0] - 1) * 100), 1) for k in mem + hw}
mb = Ur[mem].mean(axis=1); hb = Ur[hw].mean(axis=1)
roll = Ur["AAPL"].rolling(60).corr(mb)
c["corr60_aapl_membasket"] = {"latest": round(float(roll.dropna().iloc[-1]), 2),
                              "median_2024_2025": round(float(roll.loc["2024":"2025"].median()), 2)}
# 週次: メモリ株上昇週に AAPL はどうだったか(直近1年)
wk = U[mem + hw].resample("W-FRI").last().pct_change().loc["2025-11":] * 100
wk["mem"] = wk[mem].mean(axis=1)
c["weekly_1y"] = {"n": int(len(wk.dropna())),
                  "aapl_beta_on_mem": round(float(np.polyfit(wk.dropna()["mem"], wk.dropna()["AAPL"], 1)[0]), 2),
                  "aapl_mean_when_mem_up5": round(float(wk[wk.mem >= 5]["AAPL"].mean()), 2),
                  "n_mem_up5": int((wk.mem >= 5).sum()),
                  "aapl_mean_when_mem_dn5": round(float(wk[wk.mem <= -5]["AAPL"].mean()), 2),
                  "n_mem_dn5": int((wk.mem <= -5).sum())}
out["C_apple_memory"] = c

# ---- D. ドル円 160円と米金利 ----
jpy, tnx = W["JPY=X"].dropna(), W["^TNX"].dropna()
both = pd.concat([jpy, tnx], axis=1, keys=["jpy", "tnx"], sort=True).dropna()
chg = pd.DataFrame({"jpy": both.jpy.pct_change() * 100, "tnx": both.tnx.diff() * 100}).dropna()
dd_ = {"now": {"usdjpy": round(float(jpy.iloc[-1]), 2), "to_160_pct": round(float((160 / jpy.iloc[-1] - 1) * 100), 2),
               "tnx": round(float(tnx.iloc[-1]), 3), "tnx_chg_bp_nov3": round(float(chg.tnx.iloc[-1]), 1)}}
for lab, seg in {"1y": chg.loc["2025-11":], "3m": chg.loc["2026-08":]}.items():
    dd_[f"beta_jpy_pct_per_10bp_{lab}"] = round(float(np.polyfit(seg.tnx, seg.jpy, 1)[0] * 10), 3)
    dd_[f"corr_{lab}"] = round(float(np.corrcoef(seg.tnx, seg.jpy)[0, 1]), 2)
    dd_[f"n_{lab}"] = int(len(seg))
# 2026年の ドル円 高値と急落日(-1.5%以下)
j26 = jpy.loc["2026"]
dd_["high_2026"] = {"date": str(j26.idxmax().date()), "level": round(float(j26.max()), 2)}
rj = r(jpy)
drops = rj[(rj <= -1.5)].loc["2022":]
dd_["drop_days_since_2022"] = [{"date": str(t.date()), "usdjpy_ret": round(float(v), 2), "prev_close": round(float(jpy.loc[:t].iloc[-2]), 2)} for t, v in drops.items()]
# 急落日(ドル円 -1.5%以下, 前日 150円超)後の日経: 同じ日付と翌営業日、5日後
big = [t for t in drops.index if jpy.loc[:t].iloc[-2] > 150]
nk = W["^N225"].dropna()
res = []
for t in big:
    nxt = nk.loc[nk.index > t]
    if len(nxt) >= 6:
        base = nk.loc[:t].iloc[-1]
        res.append({"date": str(t.date()), "nk_next": round(float((nxt.iloc[0] / base - 1) * 100), 2),
                    "nk_5d": round(float((nxt.iloc[4] / base - 1) * 100), 2)})
dd_["nikkei_after_drops_prev_gt150"] = res
dd_["nikkei_after_drops_stat_next"] = stat([x["nk_next"] for x in res])
dd_["nikkei_after_drops_stat_5d"] = stat([x["nk_5d"] for x in res])
# 日経と(前日)ドル円の相関、直近1年
nkr = r(nk).loc["2025-11":]
pr = []
for t in nkr.index:
    s_ = rj.loc[:t - pd.Timedelta(days=1)]
    if len(s_):
        pr.append((nkr[t], s_.iloc[-1]))
pr = np.array(pr)
dd_["nk_on_prev_usdjpy_1y"] = {"n": len(pr), "beta": round(float(np.polyfit(pr[:, 1], pr[:, 0], 1)[0]), 2),
                              "corr": round(float(np.corrcoef(pr[:, 0], pr[:, 1])[0, 1]), 2)}
out["D_yen_rates"] = dd_

# ---- E. 金利上昇と株高の同時進行(株・債券の相関) ----
spr = r(spx)
e = {}
x = pd.concat([spr, W["^TNX"].dropna().diff() * 100], axis=1, keys=["spx", "tnx_bp"], sort=True).dropna()
for lab, seg in {"60d": x.iloc[-60:], "250d": x.iloc[-250:], "2010_2019": x.loc["2010":"2019"]}.items():
    e[lab] = {"n": int(len(seg)), "corr": round(float(seg.corr().iloc[0, 1]), 2)}
e["tnx_20d_chg_bp"] = round(float((W["^TNX"].dropna().iloc[-1] - W["^TNX"].dropna().iloc[-21]) * 100), 1)
e["tyx"] = round(float(W["^TYX"].dropna().iloc[-1]), 3)
e["irx"] = round(float(W["^IRX"].dropna().iloc[-1]), 3)
out["E_stock_bond"] = e

# ---- F. ネオクラウド(CRWV, NBIS)の反発は SOX の高ベータで説明できるか ----
f = {}
for tk in ["CRWV", "NBIS", "SNDK"]:
    x = pd.concat([r(W[tk]), rs], axis=1, keys=["y", "sox"]).dropna().iloc[-121:-1]
    beta = np.polyfit(x.sox, x.y, 1)
    resid = x.y - np.polyval(beta, x.sox)
    y3 = float(r(W[tk]).iloc[-1])
    f[tk] = {"n": int(len(x)), "beta_120d": round(float(beta[0]), 2), "nov3": round(y3, 2),
             "implied": round(float(np.polyval(beta, rs.iloc[-1])), 2),
             "excess": round(float(y3 - np.polyval(beta, rs.iloc[-1])), 2),
             "resid_sd": round(float(resid.std()), 2),
             "dd_from_high": round(float((W[tk].dropna().iloc[-1] / W[tk].dropna().max() - 1) * 100), 1),
             "oct_ret": round(float((W[tk].dropna().loc[:"2026-10-31"].iloc[-1] / W[tk].dropna().loc[:"2026-09-30"].iloc[-1] - 1) * 100), 1)}
f["HYG_LQD_nov3"] = {k: round(float(r(W[k]).iloc[-1]), 2) for k in ["HYG", "LQD"]}
out["F_neocloud"] = f

p = ROOT / "insights/data/analysis/2026-11-04.json"
p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
