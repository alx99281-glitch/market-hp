"""分析の視点 2026-11-06 号の検証スクリプト。
入力: /tmp/market-data/daily.parquet, /tmp/market-data/intraday_60m.parquet
出力: insights/data/analysis/2026-11-06.json
注意: ^N225 は 11/5 が未取得。11/5 東京は 1321.T / 1306.T の60分足の最終足で見る。
SOXX は 11/5 に株式分割とみられる不連続があるため使わない(SOX指数と SMH を使う)。
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CUT = pd.Timestamp("2026-11-05")
d = pd.read_parquet("/tmp/market-data/daily.parquet")
d["date"] = pd.to_datetime(d["date"])
W = d.pivot(index="date", columns="ticker", values="close").sort_index().loc[:CUT]
V = d.pivot(index="date", columns="ticker", values="volume").sort_index().loc[:CUT]
I = pd.read_parquet("/tmp/market-data/intraday_60m.parquet")
I["date"] = pd.to_datetime(I["date"], utc=True)
out = {}


def r(s):
    return s.dropna().pct_change() * 100


def stat(a):
    a = np.asarray(a, float); a = a[~np.isnan(a)]
    if len(a) == 0:
        return {"n": 0}
    return {"n": int(len(a)), "mean": round(float(a.mean()), 2), "median": round(float(np.median(a)), 2),
            "up": round(float((a > 0).mean()), 2)}


def fwd(s, dates, n):
    s = s.dropna(); res = []
    for t in dates:
        if t in s.index:
            i = s.index.get_loc(t)
            if i + n < len(s):
                res.append((s.iloc[i + n] / s.iloc[i] - 1) * 100)
    return np.array(res)


def declump(dates, idx, gap=20):
    keep = []
    for t in dates:
        if not keep or idx.get_loc(t) - idx.get_loc(keep[-1]) > gap:
            keep.append(t)
    return keep


# ---- A. SOX -12% の日 ----
sox = W["^SOX"].dropna(); rs = r(sox); spx = W["^GSPC"].dropna(); rspx = r(spx)
today = rs.loc[CUT]
rank = int((rs <= today).sum())
big = [t for t in rs.index[rs <= -9] if t < CUT]
bigd = declump(big, sox.index)
peak = sox.loc["2026-01-01":].max(); peak_d = sox.loc["2026-01-01":].idxmax()
A = {"sox_ret": round(today, 2), "rank_since2000": rank, "n_days": int(rs.loc["2000":].notna().sum()),
     "days_le_minus9": [str(t.date()) for t in big], "declumped": [str(t.date()) for t in bigd],
     "sox_close": round(float(sox.loc[CUT]), 2), "peak_2026": round(float(peak), 2), "peak_date": str(peak_d.date()),
     "dd_from_peak": round(float(sox.loc[CUT] / peak - 1) * 100, 2)}
for n in (5, 20, 60):
    A[f"fwd{n}_sox"] = stat(fwd(sox, bigd, n))
    A[f"fwd{n}_sox_all"] = stat(fwd(sox, list(sox.index[sox.index >= "2000-01-01"][:-n]), n))
A["episodes"] = []
for t in bigd:
    row = {"date": str(t.date()), "ret": round(float(rs.loc[t]), 2)}
    for n in (5, 20, 60):
        f = fwd(sox, [t], n); row[f"f{n}"] = round(float(f[0]), 2) if len(f) else None
    i = sox.index.get_loc(t); pk = sox.iloc[max(0, i - 250):i + 1].max()
    row["dd_at"] = round(float(sox.loc[t] / pk - 1) * 100, 1)
    A["episodes"].append(row)
# SMH 出来高
smhv = V["SMH"].dropna()
A["smh_vol"] = int(smhv.loc[CUT]); A["smh_vol_x20"] = round(float(smhv.loc[CUT] / smhv.iloc[-21:-1].mean()), 2)
# 作る側 vs 使う側
names = ["MU", "SNDK", "AMD", "NBIS", "ARM", "TSM", "CRWV", "ASML", "NVDA", "ORCL", "META", "MSFT", "AMZN", "GOOGL", "AAPL", "RSP", "XLP", "XLU"]
A["moves"] = {k: round(float(r(W[k]).loc[CUT]), 2) for k in names}
A["moves_2d"] = {k: round(float((W[k].dropna().loc[CUT] / W[k].dropna().loc[:"2026-11-03"].iloc[-1] - 1) * 100), 2) for k in names + ["^SOX", "^GSPC", "^NDX"]}
# メモリのベータ: MU vs SOX 60日
mu = r(W["MU"]); j = pd.concat([mu, rs], axis=1).dropna(); j.columns = ["mu", "sox"]
def beta(x):
    return float(np.cov(x.mu, x.sox)[0, 1] / x.sox.var())
A["mu_beta_60d"] = round(beta(j.iloc[-61:-1]), 2)
A["mu_beta_hist_median_60d"] = round(float(pd.Series([beta(j.iloc[k - 60:k]) for k in range(60, len(j) - 1, 20)]).median()), 2)
out["A_sox"] = A

# ---- B. VIX -20% の翌日に +70% ----
vix = W["^VIX"].dropna(); rv = r(vix)
B = {"vix": round(float(vix.loc[CUT]), 2), "vix_ret": round(float(rv.loc[CUT]), 2), "vix_prev_ret": round(float(rv.iloc[-2]), 2),
     "rank_1d_up": int((rv >= rv.loc[CUT]).sum()), "n": int(rv.notna().sum())}
up50 = [t for t in rv.index[rv >= 50] if t < CUT]
B["days_ge50"] = [str(t.date()) for t in up50]
for n in (5, 20, 60):
    B[f"fwd{n}_spx_after_vix50"] = stat(fwd(spx, up50, n))
    B[f"fwd{n}_spx_all"] = stat(fwd(spx, list(spx.index[spx.index >= "1990-01-01"][:-n]), n))
# 2日で -15%以下 → +40%以上の反転
rev = [t for t in rv.index[1:] if rv.loc[t] >= 40 and rv.shift(1).loc[t] <= -15]
B["reversal_days"] = [str(t.date()) for t in rev]
B["epis"] = [{"date": str(t.date()), "vix": round(float(vix.loc[t]), 1), "ret": round(float(rv.loc[t]), 1),
              "f20": (lambda f: round(float(f[0]), 2) if len(f) else None)(fwd(spx, [t], 20))} for t in up50]
out["B_vix"] = B

# ---- C. 債券・クレジット・円はヘッジになったか ----
tnx = W["^TNX"].dropna(); dy = tnx.diff() * 100  # bp
hyg = r(W["HYG"]); tlt = r(W["TLT"]); jpy = r(W["JPY=X"]); gld = r(W["GC=F"])
C = {"spx": round(float(rspx.loc[CUT]), 2), "tnx_bp": round(float(dy.loc[CUT]), 1), "tnx": round(float(tnx.loc[CUT]), 3),
     "hyg": round(float(hyg.loc[CUT]), 2), "tlt": round(float(tlt.loc[CUT]), 2), "usdjpy": round(float(jpy.loc[CUT]), 2),
     "gold": round(float(gld.loc[CUT]), 2), "lqd": round(float(r(W["LQD"]).loc[CUT]), 2)}
crash = [t for t in rspx.index[rspx <= -3] if t < CUT and t >= pd.Timestamp("2000-01-01")]
def sub(ser, ds):
    return stat([ser.get(t, np.nan) for t in ds])
for lab, ds in {"2000_2021": [t for t in crash if t.year <= 2021], "2022_": [t for t in crash if t.year >= 2022]}.items():
    C[lab] = {"n_days": len(ds), "tnx_bp": sub(dy, ds), "hyg": sub(hyg, [t for t in ds if t.year >= 2008]),
              "usdjpy": sub(jpy, ds), "tlt": sub(tlt, [t for t in ds if t.year >= 2003])}
# HYG / S&P 比(ベータ)の今日と過去
C["hyg_over_spx_today"] = round(float(hyg.loc[CUT] / rspx.loc[CUT]), 3)
hs = [hyg.get(t) / rspx.get(t) for t in crash if t.year >= 2008 and t in hyg.index]
C["hyg_over_spx_hist"] = stat(hs)
C["hyg_over_spx_pct_rank"] = round(float((np.array(hs) <= C["hyg_over_spx_today"]).mean()), 3)
C["tnx_bp_pct_rank"] = round(float((np.array([dy.get(t) for t in crash]) >= dy.loc[CUT]).mean()), 3)
out["C_hedge"] = C

# ---- D. 引け前の売り(レバレッジETFのリバランス) ----
D = {}
def last_half(tk):
    x = I[I.ticker == tk].copy(); x["d"] = x.date.dt.date
    res = {}
    for day, g in x.groupby("d"):
        g = g.sort_values("date")
        if len(g) < 7 or g.date.iloc[-1].strftime("%H:%M") != "20:30":
            continue
        prev_close = g.close.iloc[-2]; c = g.close.iloc[-1]; o = g.open.iloc[0]
        res[pd.Timestamp(day)] = {"last30": (c / prev_close - 1) * 100, "day_from_open": (c / o - 1) * 100,
                                  "to1530": (prev_close / o - 1) * 100}
    return pd.DataFrame(res).T
for tk in ("SPY", "QQQ", "SMH"):
    t = last_half(tk); dr = r(W[tk])
    t["day"] = dr.reindex(t.index)
    today_ = t.loc[CUT]
    big = t[(t.day <= -3) & (t.index < CUT)]
    D[tk] = {"today_last30": round(float(today_.last30), 2), "today_day": round(float(today_.day), 2),
             "big_days": [str(x.date()) for x in big.index], "big_last30": stat(big.last30),
             "all_last30": stat(t.last30[t.index < CUT]),
             "share_last30_of_day_today": round(float(today_.last30 / today_.day), 2),
             "n_sessions": int(len(t))}
out["D_close"] = D

# ---- E. 東京: 日経とTOPIXの乖離と、米国時間のEWJ ----
def tk_daily(tk):
    x = I[I.ticker == tk].copy(); x["d"] = pd.to_datetime(x.date.dt.date)
    return x.sort_values("date").groupby("d").close.last()
t13 = tk_daily("1306.T"); n21 = tk_daily("1321.T")
gap = (r(n21) - r(t13)).dropna()
E = {"1321_ret": round(float(r(n21).loc[CUT]), 2), "1306_ret": round(float(r(t13).loc[CUT]), 2),
     "nt_gap_today": round(float(gap.loc[CUT]), 2), "nt_gap_rank": int((gap <= gap.loc[CUT]).sum()), "n": int(len(gap)),
     "nt_gap_sd": round(float(gap.std()), 2),
     "period": f"{gap.index[0].date()}~{gap.index[-1].date()}"}
E["tokyo_names"] = {k: round(float(r(W[k]).loc[CUT]), 2) for k in ["6857.T", "8035.T", "285A.T", "4062.T", "9984.T", "000660.KS", "005930.KS", "2330.TW"]}
ewj = r(W["EWJ"]); dxj = r(W["DXJ"])
E["ewj"] = round(float(ewj.loc[CUT]), 2); E["dxj"] = round(float(dxj.loc[CUT]), 2)
# EWJ(米時間 t) と、東京 t+1 の 1306 の関係(約2年、日次)
nxt = r(t13).shift(-1)
ii = ewj.index.intersection(nxt.index)
df = pd.DataFrame({"ewj": ewj.reindex(ii), "same": r(t13).reindex(ii), "jpy": r(W["JPY=X"]).reindex(ii), "next": nxt.reindex(ii)}).dropna()
df["ewj_resid"] = df.ewj - df.same + df.jpy  # 東京引け後に EWJ が織り込んだ分(円建て近似)
b = np.polyfit(df.ewj_resid, df.next, 1)
E["reg_next_on_ewjresid"] = {"slope": round(float(b[0]), 2), "intercept": round(float(b[1]), 2), "n": int(len(df)),
                             "corr": round(float(df[["ewj_resid", "next"]].corr().iloc[0, 1]), 2)}
today_resid = float(ewj.loc[CUT] - r(t13).loc[CUT] + r(W["JPY=X"]).loc[CUT])
E["today_ewj_resid"] = round(today_resid, 2)
E["implied_next_1306"] = round(float(b[0] * today_resid + b[1]), 2)
bigr = df[df.ewj_resid <= -2.5]
E["big_resid_days"] = [{"date": str(t.date()), "resid": round(float(x.ewj_resid), 2), "next_1306": round(float(x.next), 2)} for t, x in bigr.iterrows()]
nkd = W["NKD=F"].dropna()
E["nkd_close"] = float(nkd.loc[CUT]); E["nkd_vol"] = int(V["NKD=F"].loc[CUT]); E["nkd_prev"] = float(nkd.iloc[-2])
out["E_tokyo"] = E

Path(ROOT / "insights/data/analysis").mkdir(parents=True, exist_ok=True)
(ROOT / "insights/data/analysis/2026-11-06.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
