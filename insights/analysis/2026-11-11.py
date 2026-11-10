"""分析の視点 2026-11-11 号の検証スクリプト。

データ: /tmp/market-data (GitHub Actions が Yahoo Finance から取得), daily-review/data。
結果: insights/data/analysis/2026-11-11.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MD = Path("/tmp/market-data")
OUT = ROOT / "insights/data/analysis/2026-11-11.json"

d = pd.read_parquet(MD / "daily.parquet")
d["date"] = pd.to_datetime(d["date"])
px = d.pivot(index="date", columns="ticker", values="close").sort_index()
T = pd.Timestamp("2026-11-10")
res = {}


def r(x, n=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def lag(jp_s, us_s):
    """東京の各営業日に、それより前の最後の米国営業日の値を対応させる。"""
    jp_s = jp_s.dropna(); us_s = us_s.dropna()
    pos = us_s.index.searchsorted(jp_s.index, side="left") - 1
    ok = pos >= 0
    return pd.DataFrame({"jp": jp_s.values[ok], "us": us_s.values[pos[ok]]}, index=jp_s.index[ok])


def dedup(dates, idx, gap=20):
    out, last = [], None
    for dt in dates:
        i = idx.get_loc(dt)
        if last is None or i - last > gap:
            out.append(dt)
            last = i
    return out


# ---------- 1. CPIで5年金利+15bp。株が崩れなかった日は何を示すか ----------
us = px[["^GSPC", "^FVX", "^TNX", "^IRX", "^VIX", "JPY=X", "GC=F", "^NDX"]].dropna(subset=["^GSPC", "^FVX"])
dy = us["^FVX"].diff() * 100  # bp
spx = us["^GSPC"]
sret = spx.pct_change() * 100
res["t_fvx_bp"] = r(dy.loc[T], 1)
res["t_tnx_bp"] = r(us["^TNX"].diff().loc[T] * 100, 1)
res["t_irx_bp"] = r(us["^IRX"].diff().loc[T] * 100, 1)
res["t_spx"] = r(sret.loc[T])
res["fvx_rank_pctile_since2000"] = r((dy.dropna() < dy.loc[T]).mean() * 100, 1)
res["n_days_fvx_ge"] = int((dy >= dy.loc[T] - 1e-9).sum())
shock = dy[dy >= 12].index
shock = [x for x in shock if x != T]
rows = []
for dt in shock:
    i = spx.index.get_loc(dt)
    f5 = spx.iloc[i + 5] / spx.iloc[i] * 100 - 100 if i + 5 < len(spx) else np.nan
    f20 = spx.iloc[i + 20] / spx.iloc[i] * 100 - 100 if i + 20 < len(spx) else np.nan
    rows.append({"date": dt, "bp": dy.loc[dt], "d0": sret.loc[dt], "f5": f5, "f20": f20})
sh = pd.DataFrame(rows).dropna()
res["shock_n"] = len(sh)
res["shock_d0_median"] = r(sh.d0.median())
res["shock_d0_down_pct"] = r((sh.d0 < 0).mean() * 100, 0)
for grp, m in [("calm", sh.d0 > -0.75), ("hit", sh.d0 <= -0.75)]:
    g = sh[m]
    res[f"shock_{grp}_n"] = len(g)
    res[f"shock_{grp}_f5_median"] = r(g.f5.median())
    res[f"shock_{grp}_f20_median"] = r(g.f20.median())
    res[f"shock_{grp}_f20_up_pct"] = r((g.f20 > 0).mean() * 100, 0)
base20 = (spx.shift(-20) / spx * 100 - 100).dropna()
res["base_f20_median"] = r(base20.median())
res["base_f20_up_pct"] = r((base20 > 0).mean() * 100, 0)
# 2022年以降の利上げ局面に限定
sh22 = sh[sh.date >= "2022-01-01"]
res["shock22_n"] = len(sh22)
res["shock22_f20_median"] = r(sh22.f20.median())
res["shock22_calm_n"] = int((sh22.d0 > -0.75).sum())
res["shock22_calm_f20_median"] = r(sh22[sh22.d0 > -0.75].f20.median())
recent = sh.sort_values("date").tail(8)
res["shock_recent"] = [
    [x.date.strftime("%Y-%m-%d"), f"+{x.bp:.1f}", f"{x.d0:+.2f}", f"{x.f5:+.2f}", f"{x.f20:+.2f}"] for x in recent.itertuples()
]
# 同日のクロスアセット
for t in ["JPY=X", "GC=F", "^VIX", "^NDX"]:
    res[f"t_{t}"] = r(us[t].pct_change().loc[T] * 100)
# ドル円の5年金利感応度(直近250日 vs 2023-2024)
fx = px["JPY=X"].pct_change() * 100
both = pd.concat([dy, fx], axis=1, keys=["dy", "fx"]).dropna()
for lab, a, b in [("recent250", both.index[-250], T), ("y2023_24", pd.Timestamp("2023-01-01"), pd.Timestamp("2024-12-31"))]:
    s = both.loc[a:b]
    beta = np.polyfit(s.dy, s.fx, 1)[0]
    res[f"usdjpy_beta_per10bp_{lab}"] = r(beta * 10, 3)
    res[f"usdjpy_corr_{lab}"] = r(s.dy.corr(s.fx), 2)
res["usdjpy_t_pred_recent"] = r(res["usdjpy_beta_per10bp_recent250"] * dy.loc[T] / 10, 2)
# 金の5年金利感応度
gd = px["GC=F"].pct_change() * 100
bg = pd.concat([dy, gd], axis=1, keys=["dy", "g"]).dropna().iloc[-250:]
res["gold_beta_per10bp_recent250"] = r(np.polyfit(bg.dy, bg.g, 1)[0] * 10, 2)
res["gold_corr_recent250"] = r(bg.dy.corr(bg.g), 2)

# ---------- 2. NVDAだけが売られた2日間 ----------
nv = px["NVDA"].dropna()
sox = px["^SOX"].reindex(nv.index)
rel = (nv.pct_change() - sox.pct_change()) * 100
rel2 = (nv / nv.shift(2) - sox / sox.shift(2)) * 100
res["nvda_2d"] = r((nv.loc[T] / nv.shift(2).loc[T] - 1) * 100)
res["sox_2d"] = r((sox.loc[T] / sox.shift(2).loc[T] - 1) * 100)
res["nvda_rel_2d"] = r(rel2.loc[T])
for t in ["AMD", "TSM", "MU", "SMH"]:
    s = px[t].dropna()
    res[f"{t}_2d"] = r((s.loc[T] / s.shift(2).loc[T] - 1) * 100)
res["nvda_d1"] = r(nv.pct_change().loc[pd.Timestamp('2026-11-09')] * 100)
res["nvda_d2"] = r(nv.pct_change().loc[T] * 100)
res["sox_d1"] = r(sox.pct_change().loc[pd.Timestamp('2026-11-09')] * 100)
res["sox_d2"] = r(sox.pct_change().loc[T] * 100)
rr = rel2.dropna()
res["nvda_rel2_rank_lowest"] = int((rr < rel2.loc[T]).sum() + 1)
res["nvda_rel2_n"] = len(rr)
res["nvda_rel2_rank_since2015"] = int((rr.loc["2015":] < rel2.loc[T]).sum() + 1)
res["nvda_rel2_n_since2015"] = len(rr.loc["2015":])
ev = dedup(rr[rr <= -8].index.drop(T, errors="ignore"), rr.index, 20)
ev = [x for x in ev if x >= pd.Timestamp("2010-01-01")]
erows = []
for dt in ev:
    i = nv.index.get_loc(dt)
    if i + 20 >= len(nv):
        continue
    erows.append({
        "date": dt, "rel2": rel2.loc[dt],
        "rel20": (nv.iloc[i + 20] / nv.iloc[i] - sox.iloc[i + 20] / sox.iloc[i]) * 100,
        "nv20": (nv.iloc[i + 20] / nv.iloc[i] - 1) * 100,
    })
er = pd.DataFrame(erows)
res["nvda_ev_n"] = len(er)
res["nvda_ev_rel20_median"] = r(er.rel20.median())
res["nvda_ev_rel20_pos_pct"] = r((er.rel20 > 0).mean() * 100, 0)
res["nvda_ev_nv20_median"] = r(er.nv20.median())
res["nvda_ev_rows"] = [[x.date.strftime("%Y-%m-%d"), f"{x.rel2:+.2f}", f"{x.nv20:+.2f}", f"{x.rel20:+.2f}"] for x in er.sort_values("date").tail(8).itertuples()]
# NVDA の SMH 内の連動(60日相関)
ch = px[["NVDA", "AMD", "AVGO" if "AVGO" in px else "TSM", "^SOX"]].pct_change()
res["nvda_sox_corr60_prev"] = r(ch["NVDA"].loc[:pd.Timestamp('2026-11-06')].tail(60).corr(ch["^SOX"].loc[:pd.Timestamp('2026-11-06')].tail(60)), 2)
# 日本の Nvidia サプライヤー: アドバンテストは NVDA と AMD/SOX のどちらに連動してきたか(米国の当日→東京の翌営業日)
jp_lag = {}
for j in ["6857.T", "8035.T", "9984.T", "285A.T"]:
    js = px[j].dropna().pct_change() * 100
    out = {}
    for u in ["NVDA", "AMD", "^SOX"]:
        us_r = px[u].dropna().pct_change() * 100
        m = lag(js, us_r)
        m = m[m.index >= pd.Timestamp("2025-11-10")]
        out[u] = r(m.jp.corr(m.us), 2)
    out["n"] = int(len(m))
    jp_lag[j] = out
res["jp_lag_corr_1y"] = jp_lag
# NVDAのSOXに対する残差(SOXで説明されない部分)が東京に効くか: アドバンテスト ~ SOX + (NVDA-SOX)
js = px["6857.T"].dropna().pct_change() * 100
uu = (px[["NVDA", "^SOX"]].dropna().pct_change() * 100)
uu["res"] = uu["NVDA"] - uu["^SOX"]
m = pd.concat([lag(js, uu["^SOX"]).rename(columns={"us": "^SOX"}), lag(js, uu["res"])["us"].rename("res")], axis=1).dropna()
m = m[m.index >= pd.Timestamp("2024-11-10")]
X = np.column_stack([np.ones(len(m)), m["^SOX"], m["res"]])
b = np.linalg.lstsq(X, m.jp, rcond=None)[0]
res["advantest_reg_2y"] = {"n": int(len(m)), "beta_sox": r(b[1], 2), "beta_nvda_minus_sox": r(b[2], 2)}
res["advantest_pred_from_us_1110"] = r(b[0] + b[1] * res["sox_d2"] + b[2] * (res["nvda_d2"] - res["sox_d2"]), 2)
for j in ["6857.T", "8035.T", "9984.T", "285A.T"]:
    res[f"{j}_1110"] = r(px[j].pct_change().loc[T] * 100)

# ---------- 3. 東京11/10の+2.87%と CME 先物 ----------
res["nkd_1110"] = r(px["NKD=F"].loc[T], 0)
res["nikkei_1110_reported"] = 60459.58
res["nkd_gap_vs_reported"] = r((px["NKD=F"].loc[T] / 60459.58 - 1) * 100)
nkd = px["NKD=F"]
nik = px["^N225"]
# 日経が+2.5%以上で引けた日の後、NKDがマイナス乖離だったとき翌日は?
n = nik.dropna()
nk = nkd.reindex(n.index)
gap = (nk / n - 1) * 100
nr = n.pct_change() * 100
nxt = nr.shift(-1)
df = pd.DataFrame({"nr": nr, "gap": gap, "nxt": nxt}).dropna().loc["2010":]
g = df[(df.nr >= 2.5) & (df.gap < 0)]
res["bigup_neg_gap_n"] = len(g)
res["bigup_neg_gap_next_median"] = r(g.nxt.median())
res["bigup_neg_gap_next_down_pct"] = r((g.nxt < 0).mean() * 100, 0)
res["bigup_neg_gap_corr"] = r(g.gap.corr(g.nxt), 2)
res["bigup_neg_gap_next_minus_gap_median"] = r((g.nxt - g.gap).median())
res["bigup_neg_gap_recent"] = [[i.strftime("%Y-%m-%d"), f"{x.nr:+.2f}", f"{x.gap:+.2f}", f"{x.nxt:+.2f}"] for i, x in g.tail(8).iterrows()]
g2 = df[(df.nr >= 2.5)]
res["bigup_n"] = len(g2)
res["bigup_next_median"] = r(g2.nxt.median())
res["bigup_next_down_pct"] = r((g2.nxt < 0).mean() * 100, 0)

# ---------- 4. CoreWeave 決算とクレジット ----------
c = px["CRWV"].dropna()
res["crwv_1110"] = r(c.loc[T])
res["crwv_peak"] = r(c.loc["2026-06":].max())
res["crwv_peak_date"] = c.loc["2026-06":].idxmax().strftime("%Y-%m-%d")
res["crwv_from_peak"] = r((c.loc[T] / c.loc["2026-06":].max() - 1) * 100, 1)
res["crwv_since_1009"] = r((c.loc[T] / c.loc[:"2026-10-09"].iloc[-1] - 1) * 100, 1)
res["crwv_since_1009_base"] = c.loc[:"2026-10-09"].index[-1].strftime("%Y-%m-%d")
cr = c.pct_change() * 100
hy = (px["HYG"] / px["IEF"]).pct_change() * 100  # 金利要因をおおまかに除いた信用の代理
lq = (px["LQD"] / px["IEF"]).pct_change() * 100
k = pd.concat([cr, hy, lq, px["NVDA"].pct_change() * 100], axis=1, keys=["crwv", "hy", "lq", "nvda"]).dropna()
for lab, a in [("60d", k.index[-60]), ("prev60d", k.index[-120])]:
    s = k.loc[a:] if lab == "60d" else k.iloc[-120:-60]
    res[f"crwv_hy_corr_{lab}"] = r(s.crwv.corr(s.hy), 2)
    res[f"crwv_nvda_corr_{lab}"] = r(s.crwv.corr(s.nvda), 2)
res["hyg_ief_since_1009"] = r(((px["HYG"] / px["IEF"]).loc[T] / (px["HYG"] / px["IEF"]).loc[:"2026-10-09"].iloc[-1] - 1) * 100, 2)
res["hyg_ief_t"] = r(hy.loc[T], 2)
res["lqd_ief_since_1009"] = r(((px["LQD"] / px["IEF"]).loc[T] / (px["LQD"] / px["IEF"]).loc[:"2026-10-09"].iloc[-1] - 1) * 100, 2)
res["sbg_since_1009"] = r((px["9984.T"].loc[T] / px["9984.T"].loc[:"2026-10-09"].iloc[-1] - 1) * 100, 1)
sb = px["9984.T"].dropna().pct_change() * 100
mm = lag(sb, cr).tail(120)
res["sbg_next_vs_crwv_corr_120"] = r(mm.jp.corr(mm.us), 2)
mm2 = lag(sb, px["NVDA"].pct_change() * 100).tail(120)
res["sbg_next_vs_nvda_corr_120"] = r(mm2.jp.corr(mm2.us), 2)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
