"""分析の視点 2026-11-03 号の検証スクリプト。
入力: /tmp/market-data/daily.parquet, daily-review/data/prices_jp.parquet
出力: insights/data/analysis/2026-11-03.json
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
d = pd.read_parquet("/tmp/market-data/daily.parquet")
W = d.pivot(index="date", columns="ticker", values="close").sort_index()
jp = pd.read_parquet(ROOT / "daily-review/data/prices_jp.parquet")
J = jp.pivot(index="date", columns="ticker", values="close").sort_index()
out = {}

def ret(x):
    """各銘柄の自市場の営業日ベースで日次リターン(%)を計算する"""
    if isinstance(x, pd.DataFrame):
        return pd.concat({c: ret(x[c]) for c in x.columns}, axis=1)
    return x.dropna().pct_change() * 100

def fwd(s, dates, n):
    """dates の終値から n 営業日後までのリターン(%)"""
    s = s.dropna(); res = []
    for t in dates:
        if t not in s.index:
            continue
        i = s.index.get_loc(t)
        if i + n < len(s):
            res.append((s.iloc[i + n] / s.iloc[i] - 1) * 100)
    return np.array(res)

def stat(a):
    a = np.asarray(a); a = a[~np.isnan(a)]
    if len(a) == 0:
        return {"n": 0}
    t = a.mean() / (a.std(ddof=1) / np.sqrt(len(a))) if len(a) > 2 else None
    return {"n": int(len(a)), "mean": round(float(a.mean()), 2), "median": round(float(np.median(a)), 2),
            "up": round(float((a > 0).mean()), 2), "t": None if t is None else round(float(t), 2)}

LAST = pd.Timestamp("2026-11-02")

# ---- A. キオクシア決算ショックとメモリ/装置の分断 ----
names = ["285A.T", "8035.T", "6857.T", "4062.T", "9984.T", "000660.KS", "005930.KS", "SNDK", "^SOX"]
R = ret(W[names])
a = {"nov2": {k: round(float(R.loc[LAST, k]), 2) for k in names}}
k, te = R["285A.T"].dropna(), R["8035.T"].dropna()
kt = pd.concat([k, te], axis=1).dropna()
rc = kt.iloc[:, 0].rolling(60).corr(kt.iloc[:, 1])
a["corr60_kioxia_tel"] = {"now_2026-10-30": round(float(rc.loc[:"2026-10-30"].dropna().iloc[-1]), 2),
                          "median_since_2025-06": round(float(rc.loc["2025-06":].median()), 2)}
# キオクシア当日(東京) -> 同じ日付の SNDK(米国、時間的に後)の連動
pair = pd.concat([k, R["SNDK"], R["^SOX"]], axis=1).dropna()
pair.columns = ["kx", "sndk", "sox"]
big = pair[pair.kx <= -8]
a["kioxia_le_-8"] = {"n": int(len(big)), "dates": [str(x.date()) for x in big.index],
                     "sndk_sameday_mean": round(float(big.sndk.mean()), 2) if len(big) else None,
                     "sndk_sameday_all_mean": round(float(pair.sndk.mean()), 2)}
X = np.c_[np.ones(len(pair)), pair.kx, pair.sox]
b = np.linalg.lstsq(X, pair.sndk, rcond=None)[0]
a["sndk_on_kioxia_and_sox_beta"] = {"kioxia": round(float(b[1]), 2), "sox": round(float(b[2]), 2), "n": int(len(pair))}
# 大幅安の後のキオクシア5日・20日
kd = k[k <= -8].index
a["kioxia_after_le_-8"] = {"5d": stat(fwd(W["285A.T"], kd, 5)), "20d": stat(fwd(W["285A.T"], kd, 20))}
kx = W["285A.T"].dropna()
a["kioxia_from_high"] = round(float((kx.iloc[-1] / kx.max() - 1) * 100), 1)
a["kioxia_high_date"] = str(kx.idxmax().date())
dv = (kt.iloc[:, 1] - kt.iloc[:, 0])
a["tel_minus_kioxia_ge_15"] = {"n": int((dv >= 15).sum()), "of": int(len(kt)),
                               "dates": [str(x.date()) for x in dv[dv >= 15].index]}
out["kioxia"] = a

# ---- B. 原油急落と日本株 ----
cl = W["CL=F"].dropna(); clr = ret(cl)
ev = clr[(clr <= -5)].dropna()
ev = ev[ev.index >= "2000-01-01"]
# 東京は翌営業日に反応(米国日付 t の翌日の N225)
n225 = W["^N225"].dropna()
def next_jp(t, s):
    after = s.index[s.index > t]
    return after[0] if len(after) else None
nk_next = []
for t in ev.index:
    t1 = next_jp(t, n225)
    if t1 is not None:
        i = n225.index.get_loc(t1)
        nk_next.append((n225.iloc[i] / n225.iloc[i - 1] - 1) * 100)
nk_all = ret(n225).dropna()
jpy = W["JPY=X"]
b = {"cl_nov2": round(float(clr.loc[LAST]), 2), "cl_level": round(float(cl.loc[LAST]), 2),
     "cl_20d_before": round(float((cl.loc[:"2026-10-30"].iloc[-1] / cl.loc[:"2026-10-30"].iloc[-21] - 1) * 100), 1),
     "events_le_-5": int(len(ev)),
     "n225_next": stat(nk_next), "n225_all": stat(nk_all.values),
     "cl_fwd5": stat(fwd(cl, ev.index, 5)), "cl_fwd20": stat(fwd(cl, ev.index, 20)),
     "cl_fwd20_all": stat(cl.pct_change(20).shift(-20).dropna().values * 100)}
# 2020年3-4月(マイナス価格前後)を除いた版
ev2 = ev[~((ev.index >= "2020-03-01") & (ev.index <= "2020-05-31"))]
b["cl_fwd20_ex2020"] = stat(fwd(cl, ev2.index, 20))
b["events_ex2020"] = int(len(ev2))
# TOPIX-17業種ETFの原油感応度(直近250日、東京t日 vs 前日の米国原油)
sec = {"1617.T": "食品", "1618.T": "エネルギー資源", "1619.T": "建設・資材", "1620.T": "素材・化学",
       "1621.T": "医薬品", "1622.T": "自動車・輸送機", "1623.T": "鉄鋼・非鉄", "1624.T": "機械",
       "1625.T": "電機・精密", "1626.T": "情報通信・サービス", "1627.T": "電力・ガス", "1628.T": "運輸・物流",
       "1630.T": "小売", "1631.T": "銀行", "1632.T": "金融(除く銀行)", "1633.T": "不動産"}
JR = ret(J[list(sec)])
clp = clr.copy()
rows = []
for t, name in sec.items():
    s = JR[t].dropna()
    s = s[s.index >= s.index[-1] - pd.Timedelta(days=365)]
    x = [clp[clp.index < dt].dropna().iloc[-1] if len(clp[clp.index < dt].dropna()) else np.nan for dt in s.index]
    df = pd.DataFrame({"y": s.values, "x": x}, index=s.index).dropna()
    beta = np.polyfit(df.x, df.y, 1)[0]
    rows.append({"etf": t, "name": name, "beta_per_10pct_oil": round(float(beta * 10), 2),
                 "corr": round(float(df.corr().iloc[0, 1]), 2), "n": int(len(df)),
                 "nov2": round(float(JR.loc[LAST, t]), 2) if LAST in JR.index else None})
b["tse17_note"] = "1629.T(商社・卸売)は2026-04-01に価格系列が不連続(約525倍)のため除外"
nk_r = ret(n225)
xs = [clr[clr.index < t].iloc[-1] if len(clr[clr.index < t]) else np.nan for t in nk_r.index]
rg = pd.DataFrame({"nk": nk_r.values, "cl": xs}, index=nk_r.index).dropna()
b["n225_vs_prev_us_oil"] = {"corr_last250": round(float(rg.iloc[-250:].corr().iloc[0, 1]), 2),
                            "corr_2000_2025": round(float(rg.loc[:"2025"].corr().iloc[0, 1]), 2),
                            "beta_per_10pct_last250": round(float(np.polyfit(rg.cl.iloc[-250:], rg.nk.iloc[-250:], 1)[0] * 10), 2)}
b["tse17_oil_beta"] = sorted(rows, key=lambda r: r["beta_per_10pct_oil"])
out["oil"] = b

# ---- C. 米中間選挙の季節性 ----
elec = {"2002": "2002-11-05", "2006": "2006-11-07", "2010": "2010-11-02", "2014": "2014-11-04",
        "2018": "2018-11-06", "2022": "2022-11-08"}
pres = {"2004": "2004-11-02", "2008": "2008-11-04", "2012": "2012-11-06", "2016": "2016-11-08",
        "2020": "2020-11-03", "2024": "2024-11-05"}
spx = W["^GSPC"].dropna(); vix = W["^VIX"].dropna(); nk = W["^N225"].dropna()
def before(s, t):
    return s.index[s.index < pd.Timestamp(t)][-1]
c = {"midterm": [], "president": []}
for lab, grp in (("midterm", elec), ("president", pres)):
    for y, t in grp.items():
        t0 = before(spx, t)  # 投票日前日の終値を起点
        i = spx.index.get_loc(t0)
        r = {"year": y}
        for n in (5, 20, 60, 250):
            r[f"spx_{n}d"] = round(float((spx.iloc[i + n] / spx.iloc[i] - 1) * 100), 2) if i + n < len(spx) else None
        v0 = vix.loc[t0]; vi = vix.index.get_loc(t0)
        r["vix_pre"] = round(float(v0), 1)
        r["vix_chg_5d"] = round(float(vix.iloc[vi + 5] - v0), 1)
        j0 = before(nk, t); ji = nk.index.get_loc(j0)
        r["n225_20d"] = round(float((nk.iloc[ji + 20] / nk.iloc[ji] - 1) * 100), 2)
        c[lab].append(r)
base = {}
for n in (20, 60, 250):
    base[f"spx_{n}d_all"] = stat(spx.pct_change(n).shift(-n).dropna().values * 100)
c["baseline_since_2000"] = base
# 選挙年の11月初旬起点に限定した比較: 2000年以降の毎年11月第1営業日前後(選挙年以外)
non = []
for y in range(2000, 2026):
    if str(y) in elec or str(y) in pres:
        continue
    t0 = before(spx, f"{y}-11-05")
    i = spx.index.get_loc(t0)
    non.append({"year": y, "spx_20d": round(float((spx.iloc[i + 20] / spx.iloc[i] - 1) * 100), 2),
                "spx_60d": round(float((spx.iloc[i + 60] / spx.iloc[i] - 1) * 100), 2)})
c["non_election_nov_start"] = non
c["summary"] = {
    "midterm_20d": stat([r["spx_20d"] for r in c["midterm"]]),
    "midterm_60d": stat([r["spx_60d"] for r in c["midterm"]]),
    "midterm_250d": stat([r["spx_250d"] for r in c["midterm"] if r["spx_250d"] is not None]),
    "president_20d": stat([r["spx_20d"] for r in c["president"]]),
    "non_election_20d": stat([r["spx_20d"] for r in non]),
    "non_election_60d": stat([r["spx_60d"] for r in non]),
    "vix_chg_5d_all12": stat([r["vix_chg_5d"] for r in c["midterm"] + c["president"]]),
}
c["vix_now"] = round(float(vix.loc[LAST]), 2)
c["vix_chg_nov2"] = round(float(vix.loc[LAST] - vix.iloc[-2]), 2)
c["spx_nov2"] = round(float((spx.loc[LAST] / spx.iloc[-2] - 1) * 100), 2)
c["note"] = "2026年の投票日は11/3。11/3は東証休場(文化の日)。"
out["midterm"] = c

# ---- D. 時価総額加重と均等加重の乖離 ----
rel = (ret(W["RSP"]) - ret(W["SPY"])).dropna()
spy = ret(W["SPY"])
dd = {"rsp_minus_spy_nov2": round(float(rel.loc[LAST]), 2),
      "rsp_minus_spy_2d": round(float(rel.iloc[-2:].sum()), 2),
      "rsp_minus_spy_10d": round(float(rel.iloc[-10:].sum()), 2)}
rel10 = rel.rolling(10).sum()
dd["rel10_pctile_since_2004"] = round(float((rel10.dropna() < rel10.iloc[-1]).mean() * 100), 1)
# 条件: 10日で RSP が SPY を +3pt以上上回り、かつ SPY の10日リターンがマイナス
spy10 = W["SPY"].dropna().pct_change(10) * 100
cond = (rel10 >= 3) & (spy10 < 0)
# 重複を避け20日間隔で間引き
dates = []; last = None
for t in cond[cond].index:
    if last is None or (t - last).days > 30:
        dates.append(t); last = t
dd["events"] = [str(x.date()) for x in dates]
dd["spy_fwd20"] = stat(fwd(W["SPY"], dates, 20)); dd["spy_fwd60"] = stat(fwd(W["SPY"], dates, 60))
dd["rel_fwd20"] = stat([(fwd(W["RSP"], [t], 20)[0] - fwd(W["SPY"], [t], 20)[0]) for t in dates if len(fwd(W["SPY"], [t], 20))])
dd["spy_fwd20_all"] = stat(W["SPY"].dropna().pct_change(20).shift(-20).dropna().values * 100)
dd["spy10_now"] = round(float(spy10.iloc[-1]), 2)
# 日本側: TOPIX ETF(1306) と 日経ETF(1321) の 11/2
dd["jp_nov2"] = {"1306.T": round(float(ret(J["1306.T"]).loc[LAST]), 2), "1321.T": round(float(ret(J["1321.T"]).loc[LAST]), 2)}
out["equal_weight"] = dd

# ---- E. クレジットへの波及 ----
hy = (ret(W["HYG"]) - ret(W["IEF"]) * 0.45).dropna()   # 金利部分(デュレーション約半分)を粗く控除
e = {"hyg_nov2": round(float(ret(W["HYG"]).loc[LAST]), 2), "ief_nov2": round(float(ret(W["IEF"]).loc[LAST]), 2),
     "lqd_nov2": round(float(ret(W["LQD"]).loc[LAST]), 2)}
hyg = W["HYG"].dropna()
e["hyg_from_high_250d"] = round(float((hyg.iloc[-1] / hyg.iloc[-250:].max() - 1) * 100), 2)
e["hyg_ex_rates_20d"] = round(float(hy.iloc[-20:].sum()), 2)
s = pd.concat([hy, ret(W["^SOX"]), ret(W["CRWV"])], axis=1).dropna(); s.columns = ["hy", "sox", "crwv"]
def beta(df, x):
    return round(float(np.polyfit(df[x], df.hy, 1)[0] * 10), 3)
e["hy_beta_to_sox_per10"] = {"last60": beta(s.iloc[-60:], "sox"), "prev250": beta(s.iloc[-310:-60], "sox")}
e["hy_corr_sox"] = {"last60": round(float(s.iloc[-60:].corr().loc["hy", "sox"]), 2),
                    "prev250": round(float(s.iloc[-310:-60].corr().loc["hy", "sox"]), 2)}
e["hy_corr_crwv"] = {"last60": round(float(s.iloc[-60:].corr().loc["hy", "crwv"]), 2),
                     "prev250": round(float(s.iloc[-310:-60].corr().loc["hy", "crwv"]), 2)}
e["crwv_2d"] = round(float((W["CRWV"].dropna().iloc[-1] / W["CRWV"].dropna().iloc[-3] - 1) * 100), 1)
e["nbis_2d"] = round(float((W["NBIS"].dropna().iloc[-1] / W["NBIS"].dropna().iloc[-3] - 1) * 100), 1)
e["vix_nov2"] = round(float(W["^VIX"].dropna().iloc[-1]), 2)
# 月初(分配落ちの可能性がある日)の影響を回帰で確認: 2015年以降
m = pd.concat([ret(W["IEF"]), ret(W["HYG"]), W["^TNX"].dropna().diff()], axis=1).dropna().loc["2015":]
m.columns = ["ief", "hyg", "dy"]
first = m.groupby(m.index.to_period("M")).head(1).index
X = np.c_[np.ones(len(m)), m.dy, m.index.isin(first)]
e["first_day_of_month_dummy"] = {c: round(float(np.linalg.lstsq(X, m[c], rcond=None)[0][2]), 3) for c in ("ief", "hyg")}
e["tnx_chg_nov2"] = round(float(m.dy.iloc[-1]), 3)
out["credit"] = e

(ROOT / "insights/data/analysis").mkdir(parents=True, exist_ok=True)
(ROOT / "insights/data/analysis/2026-11-03.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
