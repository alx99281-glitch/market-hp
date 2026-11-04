"""分析の視点 2026-11-05 号の検証スクリプト。
入力: /tmp/market-data/daily.parquet, daily-review/data/prices_jp.parquet
出力: insights/data/analysis/2026-11-05.json
注意: ^N225 は Yahoo 側で 11/3以降が未取得(11/2まで)。11/4 の東京は 1321.T / 1306.T(prices_jp)と個別銘柄で見る。
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CUT = pd.Timestamp("2026-11-04")
d = pd.read_parquet("/tmp/market-data/daily.parquet")
d["date"] = pd.to_datetime(d["date"])
W = d.pivot(index="date", columns="ticker", values="close").sort_index().loc[:CUT]
jp = pd.read_parquet(ROOT / "daily-review/data/prices_jp.parquet")
J = jp.pivot(index="date", columns="ticker", values="adj_close").sort_index()
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


def declump(dates, idx, gap=20):
    keep = []
    for t in dates:
        if not keep or idx.get_loc(t) - idx.get_loc(keep[-1]) > gap:
            keep.append(t)
    return keep


def nextday(series_jp, us_dates):
    """米国の日付 t の翌東京営業日のリターン"""
    s = r(series_jp); res = {}
    for t in us_dates:
        nx = s.loc[s.index > t]
        if len(nx):
            res[t] = nx.iloc[0]
    return pd.Series(res)


spx, sox, ndx = W["^GSPC"].dropna(), W["^SOX"].dropna(), W["^NDX"].dropna()
rspx, rsox = r(spx), r(sox)

# ---- A. 指数高・半導体安: S&P +1.5%以上かつ SOX -2%以下 ----
both = pd.concat([rspx, rsox], axis=1, keys=["spx", "sox"]).dropna()
spread = both.sox - both.spx
ev = both[(both.spx >= 1.5) & (both.sox <= -2)].index
a = {"nov4": {k: round(float(r(W[k]).iloc[-1]), 2) for k in
              ["^GSPC", "^DJI", "^NDX", "^SOX", "SMH", "NVDA", "MU", "SNDK", "CRWV", "NBIS", "ARM", "ASML", "TSM", "AMD", "AAPL",
               "RSP", "XLK", "XLC", "XLY", "XLF", "XLP", "XLV", "XLE", "XLI", "XLU", "IGV", "IWM"]},
     "definition": "S&P500 +1.5%以上 かつ SOX -2%以下(2000年以降)",
     "events": [str(t.date()) for t in ev],
     "spread_now": round(float(spread.iloc[-1]), 2),
     "spread_rank_pct_since2000": round(float((spread < spread.iloc[-1]).mean() * 100), 2)}
# SOX−S&P の乖離が -4pt以下の日(下側)で、S&P がプラスの日
ev2 = both[(spread <= -4) & (both.spx > 0)].index
ev2 = [t for t in ev2 if t < CUT]
ev2d = declump(ev2, both.index, 20)
rel = (sox / spx)
a["spread_le_-4_spx_up"] = {"n_all": len(ev2), "n_declumped": len(ev2d), "dates_declumped": [str(t.date()) for t in ev2d],
                             "sox_rel_fwd5": stat(fwd(rel, ev2d, 5)), "sox_rel_fwd20": stat(fwd(rel, ev2d, 20)),
                             "sox_fwd20": stat(fwd(sox, ev2d, 20)), "spx_fwd20": stat(fwd(spx, ev2d, 20)),
                             "uncond_sox_rel_fwd20": stat(fwd(rel, list(rel.dropna().index[::5]), 20))}
# 「買い手」と「売り手」: AAPL−MU の1日差の分位(MU上場来 2000年以降)
am = (r(W["AAPL"]) - r(W["MU"])).dropna()
a["aapl_minus_mu"] = {"now": round(float(am.iloc[-1]), 2), "pct_rank": round(float((am < am.iloc[-1]).mean() * 100), 2), "n": int(len(am))}
# 直近の SOX と NDX 構成: NDX が SOX下落日に上がった回数(直近60日)
last60 = both.iloc[-60:]
a["last60_sox_down2_spx_up"] = int(((last60.sox <= -2) & (last60.spx > 0)).sum())
out["A_spenders_vs_suppliers"] = a

# ---- B. 東京: 米国で SOX が S&P を大きく下回った翌日、日経(1321)はTOPIX(1306)を下回るか ----
nt = J["1321.T"].dropna() / J["1306.T"].dropna()
nt = nt.dropna()
rnt = r(nt)
# 分割・データ欠損による異常値(1日±8%超)を除外
rnt = rnt[rnt.abs() < 8]
us_days = both.loc["2023-11":].index
nx = {}
for t in us_days:
    s = rnt.loc[rnt.index > t]
    if len(s) and (s.index[0] - t).days <= 4:
        nx[t] = s.iloc[0]
nx = pd.Series(nx)
dfb = pd.concat([spread.reindex(nx.index), nx], axis=1, keys=["spread", "nt_next"]).dropna()
dfb = dfb.loc[:pd.Timestamp("2026-11-03")]
X = np.c_[np.ones(len(dfb)), dfb.spread]
beta = np.linalg.lstsq(X, dfb.nt_next, rcond=None)[0]
big = dfb[dfb.spread <= -3]
b = {"n_days": int(len(dfb)), "period": f"{dfb.index[0].date()}〜{dfb.index[-1].date()}",
     "beta_nt_next_on_sox_minus_spx": round(float(beta[1]), 3),
     "corr": round(float(np.corrcoef(dfb.spread, dfb.nt_next)[0, 1]), 2),
     "spread_le_-3": stat(big.nt_next), "all": stat(dfb.nt_next),
     "implied_now": round(float(beta[0] + beta[1] * spread.iloc[-1]), 2)}
# 11/4 の東京(米国11/4の前に終わっている)
b["tokyo_nov4"] = {"1321.T": round(float(r(J["1321.T"]).iloc[-1]), 2), "1306.T": round(float(r(J["1306.T"]).iloc[-1]), 2),
                   "nt_ratio_chg": round(float(rnt.iloc[-1]), 2)}
for tk in ["8035.T", "6857.T", "285A.T", "9984.T", "4062.T", "1570.T", "000660.KS", "005930.KS"]:
    b["tokyo_nov4"][tk] = round(float(r(W[tk]).iloc[-1]), 2)
for tk in ["1618.T", "1625.T", "1631.T"]:
    if tk in J and pd.Timestamp("2026-11-04") in J[tk].dropna().index:
        b["tokyo_nov4"][tk] = round(float(r(J[tk]).iloc[-1]), 2)
# 東京の半導体の、前日SOX と 前日NDX への感応度(直近1年、2変数回帰)
rndx = r(ndx)
for tk in ["8035.T", "6857.T", "285A.T", "9984.T"]:
    x = r(W[tk]).loc["2025-11":"2026-11-04"]
    rows = []
    for t in x.index:
        ps = rsox.loc[:t - pd.Timedelta(days=1)]; pn = rndx.loc[:t - pd.Timedelta(days=1)]
        if len(ps) and len(pn):
            rows.append((x[t], ps.iloc[-1], pn.iloc[-1]))
    A_ = np.array(rows)
    bb = np.linalg.lstsq(np.c_[np.ones(len(A_)), A_[:, 1], A_[:, 2]], A_[:, 0], rcond=None)[0]
    b[f"{tk}_beta_prev_sox_ndx_1y"] = {"n": len(A_), "b_sox": round(float(bb[1]), 2), "b_ndx": round(float(bb[2]), 2),
                                       "implied_nov5": round(float(bb[0] + bb[1] * rsox.iloc[-1] + bb[2] * rndx.iloc[-1]), 2)}
# 夜間: CME日経先物(NKD=F)11/4
b["nkd_nov4"] = {"close": round(float(W["NKD=F"].dropna().iloc[-1]), 0), "chg": round(float(r(W["NKD=F"]).iloc[-1]), 2)}
# 米国11/4の下げのうち、東京の取引時間を含む夜間(11/3引け→11/4寄り)に進んだ分(60分足)
it = pd.read_parquet("/tmp/market-data/intraday_60m.parquet"); it["date"] = pd.to_datetime(it["date"], utc=True)
gap = {}
for tk in ["SPY", "QQQ", "SMH"]:
    x = it[it.ticker == tk].set_index("date").sort_index()
    c3 = x.loc["2026-11-03"].close.iloc[-1]; d4 = x.loc["2026-11-04"]
    o4, c4 = d4.open.iloc[0], d4.close.iloc[-1]
    gap[tk] = {"overnight_gap": round(float((o4 / c3 - 1) * 100), 2), "open_to_close": round(float((c4 / o4 - 1) * 100), 2),
               "total": round(float((c4 / c3 - 1) * 100), 2)}
b["us_nov4_gap_vs_session"] = gap
b["note_1306_nov4"] = "1306.T の11/4値は報道のTOPIX(-0.89%)と整合しないため使わない"
out["B_tokyo_nt"] = b

# ---- C. VIX -20%以上の1日 ----
vix = W["^VIX"].dropna(); rv = r(vix)
c = {"nov4": {"vix": round(float(vix.iloc[-1]), 2), "vix_chg": round(float(rv.iloc[-1]), 2),
              "vix_prev": round(float(vix.iloc[-2]), 2)}}
evc = [t for t in rv.index if rv[t] <= -20 and t < CUT]
evcd = declump(evc, vix.index, 20)
c["events_n"] = len(evc); c["events_declumped"] = [str(t.date()) for t in evcd]
for n in (5, 20, 60):
    c[f"spx_fwd{n}"] = stat(fwd(spx, evcd, n))
    c[f"spx_fwd{n}_uncond"] = stat(fwd(spx, list(spx.index[::5]), n))
vx20 = []
for t in evcd:
    i = vix.index.get_loc(t)
    if i + 20 < len(vix):
        vx20.append(vix.iloc[i + 1:i + 21].max() / vix.iloc[i] - 1)
c["vix_max_next20_vs_event"] = stat(np.array(vx20) * 100)
c["share_vix_back_above_prev_level_20d"] = round(float(np.mean([
    vix.iloc[vix.index.get_loc(t) + 1:vix.index.get_loc(t) + 21].max() >= vix.iloc[vix.index.get_loc(t) - 1]
    for t in evcd if vix.index.get_loc(t) + 20 < len(vix)])), 2)
# 中間選挙翌日(水曜)の S&P
mid = ["2002-11-06", "2006-11-08", "2010-11-03", "2014-11-05", "2018-11-07", "2022-11-09", "2026-11-04"]
c["midterm_next_day_spx"] = {m: round(float(rspx.loc[m]), 2) for m in mid}
c["midterm_next_day_vix_chg"] = {m: round(float(rv.loc[m]), 2) for m in mid}
out["C_vix_crush"] = c

# ---- D. 原油急落: 供給要因(株高)か需要要因(株安)か ----
cl = W["CL=F"].dropna(); rcl = r(cl)
n225 = W["^N225"].dropna()
dd_ = {"cl_nov4": round(float(rcl.iloc[-1]), 2), "cl_2day": round(float((cl.iloc[-1] / cl.loc[:"2026-10-30"].iloc[-1] - 1) * 100), 2),
       "cl_close": round(float(cl.iloc[-1]), 2), "brent_nov4": round(float(r(W["BZ=F"]).iloc[-1]), 2),
       "cl_from_20d_high": round(float((cl.iloc[-1] / cl.iloc[-21:].max() - 1) * 100), 2),
       "hg_nov4": round(float(r(W["HG=F"]).iloc[-1]), 2), "tnx_bp": round(float((W["^TNX"].dropna().iloc[-1] - W["^TNX"].dropna().iloc[-2]) * 100), 1)}
pair = pd.concat([rcl, rspx], axis=1, keys=["cl", "spx"]).dropna()
pair = pair[(pair.index < CUT) & (pair.cl.abs() < 50)]
nk_next = nextday(n225, pair.index)
pair["nk_next"] = nk_next
sup = pair[(pair.cl <= -5) & (pair.spx >= 0.5)]
dem = pair[(pair.cl <= -5) & (pair.spx <= -0.5)]
dd_["oil_down5_spx_up"] = {"n": len(sup), "nk_next": stat(sup.nk_next), "cl_fwd20": stat(fwd(cl, list(sup.index), 20))}
dd_["oil_down5_spx_down"] = {"n": len(dem), "nk_next": stat(dem.nk_next), "cl_fwd20": stat(fwd(cl, list(dem.index), 20))}
dd_["nk_next_uncond"] = stat(pair.nk_next)
# 対照: S&P +0.5%以上で原油の大幅安がない日(原油 > -2%)
ctl = pair[(pair.spx >= 0.5) & (pair.cl > -2)]
dd_["control_spx_up_no_oil_drop"] = {"n": len(ctl), "nk_next": stat(ctl.nk_next), "spx_mean": round(float(ctl.spx.mean()), 2)}
dd_["oil_down5_spx_up"]["spx_mean"] = round(float(sup.spx.mean()), 2)
# 回帰: 翌日日経 = a + b*S&P + c*原油
pp = pair.dropna()
co = np.linalg.lstsq(np.c_[np.ones(len(pp)), pp.spx, pp.cl], pp.nk_next, rcond=None)[0]
dd_["reg_nk_next_on_spx_cl_2000on"] = {"n": len(pp), "b_spx": round(float(co[1]), 3), "b_cl": round(float(co[2]), 3)}
pp2 = pp.loc["2025-11":]
co2 = np.linalg.lstsq(np.c_[np.ones(len(pp2)), pp2.spx, pp2.cl], pp2.nk_next, rcond=None)[0]
dd_["reg_nk_next_on_spx_cl_1y"] = {"n": len(pp2), "b_spx": round(float(co2[1]), 3), "b_cl": round(float(co2[2]), 3)}
dd_["oil_down5_spx_up_dates_recent"] = [str(t.date()) for t in sup.index[-8:]]
# 2日で -10%以上(11/2, 11/4 の連続急落の類似)
cl2 = (cl / cl.shift(2) - 1) * 100
e2 = declump([t for t in cl2.index if cl2[t] <= -12 and t < CUT], cl.index, 20)
dd_["oil_2day_le_-12"] = {"n": len(e2), "dates": [str(t.date()) for t in e2], "cl_fwd20": stat(fwd(cl, e2, 20)),
                          "nk_fwd20": stat([((n225.loc[n225.index > t].iloc[min(19, len(n225.loc[n225.index > t]) - 1)] /
                                              n225.loc[:t].iloc[-1]) - 1) * 100 for t in e2 if len(n225.loc[n225.index > t]) >= 20])}
out["D_oil"] = dd_

# ---- E. ドル安とドル円 ----
jpy, dxy, eur = W["JPY=X"].dropna(), W["DX-Y.NYB"].dropna(), W["EURUSD=X"].dropna()
e = {"jpy_nov4": round(float(jpy.iloc[-1]), 2), "jpy_chg": round(float(r(jpy).iloc[-1]), 2),
     "dxy_chg": round(float(r(dxy).iloc[-1]), 2), "eur_chg": round(float(r(eur).iloc[-1]), 2),
     "gold_chg": round(float(r(W["GC=F"]).iloc[-1]), 2), "btc_chg": round(float(r(W["BTC-USD"]).iloc[-1]), 2)}
out["E_fx"] = e

(ROOT / "insights/data/analysis").mkdir(parents=True, exist_ok=True)
(ROOT / "insights/data/analysis/2026-11-05.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
