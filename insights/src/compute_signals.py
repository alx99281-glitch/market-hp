"""「分析の視点」タブの定量検証。

X やニュースで語られる相場の経験則を、公開データで毎回検証して
insights/data/signals.json に書き出す。編集コメント（editions/*.json）は
この数値だけを引用する。データ出所はすべて Yahoo Finance (yfinance)。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "signals.json"

SECTOR_ETFS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
JP_NAMES = {
    "285A.T": "キオクシア", "6857.T": "アドバンテスト", "8035.T": "東京エレクトロン",
    "4062.T": "イビデン", "9984.T": "ソフトバンクG", "8306.T": "三菱UFJ",
    "7203.T": "トヨタ", "1306.T": "TOPIX連動ETF",
}
HYPERSCALERS = ["MSFT", "GOOGL", "AMZN", "META", "ORCL"]
MEMORY = ["MU", "SNDK", "WDC", "STX", "285A.T"]


def closes(tickers, period="max", field="Close"):
    df = yf.download(tickers, period=period, auto_adjust=True, progress=False, threads=True)
    out = df[field]
    if isinstance(out, pd.Series):
        out = out.to_frame(tickers if isinstance(tickers, str) else tickers[0])
    out.index = pd.to_datetime(out.index).tz_localize(None)
    return out


def rnd(x, n=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), n)


def tstat(s):
    s = pd.Series(s).dropna()
    if len(s) < 3 or s.std() == 0:
        return None
    return float(s.mean() / (s.std() / np.sqrt(len(s))))


def next_session_align(target_index, lagged):
    """日本の各営業日に、直近の米国セッション（+1日ずらし済み）を対応させる。"""
    left = pd.DataFrame({"d": pd.DatetimeIndex(target_index).astype("datetime64[ns]")})
    right = lagged.copy()
    right.index = pd.DatetimeIndex(right.index).astype("datetime64[ns]")
    right = right.rename_axis("d").reset_index()
    m = pd.merge_asof(left, right, on="d", direction="backward", tolerance=pd.Timedelta(days=4))
    m.index = target_index
    return m.drop(columns="d")


def forward_stats(price, mask, horizons=(5, 20, 60)):
    """シグナル日の先行リターンを全期間平均と比較する。

    重複を避けるためシグナルは最短20営業日空けて数える。
    """
    idx = np.where(mask.reindex(price.index).fillna(False).values)[0]
    picked, last = [], -10**9
    for i in idx:
        if i - last >= 20:
            picked.append(i)
            last = i
    res = {"n": len(picked)}
    p = price.values
    for h in horizons:
        fwd = pd.Series(p).shift(-h) / pd.Series(p) - 1
        sig = fwd.iloc[picked].dropna()
        res[f"fwd{h}d"] = rnd(sig.mean() * 100)
        res[f"hit{h}d"] = rnd((sig > 0).mean() * 100, 0)
        res[f"base{h}d"] = rnd(fwd.mean() * 100)
        res[f"basehit{h}d"] = rnd((fwd.dropna() > 0).mean() * 100, 0)
    return res


def intraday_jp():
    """前場・後場の分解。ETF(1306=TOPIX, 1321=日経225)の60分足、約2年。"""
    out = {}
    for tk, label in (("1321.T", "日経225ETF"), ("1306.T", "TOPIX ETF")):
        d = yf.download(tk, period="729d", interval="60m", auto_adjust=False, progress=False)
        if d.empty:
            continue
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        d.index = pd.to_datetime(d.index)
        d.index = d.index.tz_convert("Asia/Tokyo") if d.index.tz else d.index.tz_localize("UTC").tz_convert("Asia/Tokyo")
        d["date"] = d.index.date
        d["hour"] = d.index.hour
        rows = []
        for day, g in d.groupby("date"):
            am, pm = g[g.hour < 12], g[g.hour >= 12]
            if am.empty or pm.empty:
                continue
            rows.append({
                "date": pd.Timestamp(day), "open": am.Open.iloc[0], "am_close": am.Close.iloc[-1],
                "pm_open": pm.Open.iloc[0], "close": pm.Close.iloc[-1],
            })
        r = pd.DataFrame(rows).set_index("date").sort_index()
        r["gap"] = (r.open / r.close.shift(1) - 1) * 100
        r["am"] = (r.am_close / r.open - 1) * 100
        r["lunch"] = (r.pm_open / r.am_close - 1) * 100
        r["pm"] = (r.close / r.pm_open - 1) * 100
        r = r.dropna()
        r = r[r.gap.abs() < 15]  # 60分足は分割未調整のため、分割日のギャップを除外
        def block(x):
            return {
                "n": len(x),
                **{f"{c}_mean_bp": rnd(x[c].mean() * 100, 1) for c in ("gap", "am", "lunch", "pm")},
                **{f"{c}_cum_pct": rnd(((1 + x[c] / 100).prod() - 1) * 100, 1) for c in ("gap", "am", "lunch", "pm")},
                "am_t": rnd(tstat(x.am)), "pm_t": rnd(tstat(x.pm)),
                "am_win": rnd((x.am > 0).mean() * 100, 0), "pm_win": rnd((x.pm > 0).mean() * 100, 0),
                "gap_am_corr": rnd(x.gap.corr(x.am)), "am_pm_corr": rnd(x.am.corr(x.pm)),
            }
        down_gap = r[r.gap < -0.5]
        monthly = r[["gap", "am", "pm"]].groupby(r.index.to_period("M")).sum().tail(12)
        out[label] = {
            "ticker": tk, "start": str(r.index[0].date()), "end": str(r.index[-1].date()),
            "all": block(r), "last20": block(r.tail(20)), "last60": block(r.tail(60)), "last120": block(r.tail(120)),
            "after_gap_down": block(down_gap) if len(down_gap) > 5 else None,
            "monthly": [{"m": str(k), "gap": rnd(v.gap, 1), "am": rnd(v.am, 1), "pm": rnd(v.pm, 1)} for k, v in monthly.iterrows()],
        }
    return out


def dispersion():
    """米セクターETF間の20日リターン格差と、先行S&P500リターン。"""
    px = closes(SECTOR_ETFS + ["SPY"])
    px = px.loc["1999-01-01":].dropna(how="all")
    ret20 = px[SECTOR_ETFS].pct_change(20)
    disp = ret20.std(axis=1) * 100
    spy = px["SPY"].dropna()
    disp = disp.reindex(spy.index).dropna()
    spy = spy.reindex(disp.index)
    pct = disp.rolling(1260, min_periods=504).rank(pct=True) * 100
    dd = spy / spy.rolling(250, min_periods=60).max() - 1
    fwd_dd = pd.Series(
        [spy.iloc[i:i + 21].min() / spy.iloc[i] - 1 if i + 21 <= len(spy) else np.nan for i in range(len(spy))],
        index=spy.index,
    ) * 100
    fwd20 = (spy.shift(-20) / spy - 1) * 100
    q = pd.qcut(disp, 5, labels=False)
    table = []
    for i in range(5):
        m = q == i
        table.append({
            "quintile": i + 1, "disp": rnd(disp[m].mean()), "fwd20": rnd(fwd20[m].mean()),
            "hit20": rnd((fwd20[m].dropna() > 0).mean() * 100, 0), "maxdd20": rnd(fwd_dd[m].mean()),
            "p_dd5": rnd((fwd_dd[m].dropna() < -5).mean() * 100, 0),
        })
    # 指数が高値圏（-3%以内）なのに格差だけ大きい局面が「天井サイン」説の本丸
    near_high = dd > -0.03
    high_q = q == 4
    combo = near_high & high_q
    last = ret20.iloc[-1].sort_values()
    return {
        "start": str(spy.index[0].date()), "end": str(spy.index[-1].date()), "by_quintile": table,
        "current": rnd(disp.iloc[-1]), "current_pct_5y": rnd(pct.iloc[-1], 0),
        "current_quintile": int(np.searchsorted(pd.Series(disp).quantile([.2, .4, .6, .8]).values, disp.iloc[-1]) + 1),
        "near_high_and_top_quintile": {
            "days": int(combo.sum()), "fwd20": rnd(fwd20[combo].mean()), "hit20": rnd((fwd20[combo].dropna() > 0).mean() * 100, 0),
            "maxdd20": rnd(fwd_dd[combo].mean()), "p_dd5": rnd((fwd_dd[combo].dropna() < -5).mean() * 100, 0),
            "is_now": bool(combo.iloc[-1]),
        },
        "base": {"fwd20": rnd(fwd20.mean()), "hit20": rnd((fwd20.dropna() > 0).mean() * 100, 0),
                 "maxdd20": rnd(fwd_dd.mean()), "p_dd5": rnd((fwd_dd.dropna() < -5).mean() * 100, 0)},
        "leaders_20d": [{"t": k, "r": rnd(v * 100, 1)} for k, v in last.tail(3)[::-1].items()],
        "laggards_20d": [{"t": k, "r": rnd(v * 100, 1)} for k, v in last.head(3).items()],
    }


def volume_bottom():
    """出来高クライマックスは底か。下落局面の高出来高陰線とその後。"""
    res = {}
    for tk, label in (("^GSPC", "S&P500"), ("^N225", "日経平均")):
        d = yf.download(tk, period="max", auto_adjust=True, progress=False)
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        d.index = pd.to_datetime(d.index).tz_localize(None)
        d = d[d.Volume > 0].loc["2005-01-01":]
        c, v = d.Close, d.Volume
        vr = v / v.rolling(50).mean()
        dd20 = c / c.rolling(20).max() - 1
        r = c.pct_change()
        sig = (dd20 < -0.05) & (r < -0.015) & (vr > 1.5)
        # 確認: クライマックス後5日以内に、シグナル日の高値を終値で上抜く
        confirm = pd.Series(False, index=c.index)
        for i in np.where(sig.values)[0]:
            hi = d.High.iloc[i]
            for j in range(i + 1, min(i + 6, len(c))):
                if c.iloc[j] > hi:
                    confirm.iloc[j] = True
                    break
        res[label] = {
            "start": str(c.index[0].date()),
            "climax": forward_stats(c, sig), "confirmed": forward_stats(c, confirm),
            "latest": {"date": str(c.index[-1].date()), "ret": rnd(r.iloc[-1] * 100), "vol_ratio": rnd(vr.iloc[-1]),
                       "dd20": rnd(dd20.iloc[-1] * 100), "signal_today": bool(sig.iloc[-1]),
                       "last_signal": str(c.index[sig.values][-1].date()) if sig.any() else None},
        }
    return res


def transmission():
    """前夜の米市場→翌日の日本。直近120日と250日の感応度。"""
    us = closes(["^SOX", "^NDX", "^GSPC", "^TNX", "JPY=X"], period="3y")
    jp = closes(list(JP_NAMES) + ["^N225"], period="3y")
    f = pd.DataFrame({
        "sox": us["^SOX"].pct_change() * 100, "ndx": us["^NDX"].pct_change() * 100,
        "spx": us["^GSPC"].pct_change() * 100, "t10": us["^TNX"].diff() * 100,
    })
    fx = (us["JPY=X"].pct_change() * 100).rename("fx")
    y = jp.pct_change() * 100
    y = y.where(y.abs() < 25)  # 調整漏れの分割・データ異常を除外
    # 米国T日の引け→日本T+1日。営業日のズレは前方補完せず、直近の米営業日に合わせる
    us_lag = f.dropna().copy()
    us_lag.index = us_lag.index + pd.Timedelta(days=1)
    x = next_session_align(y.index, us_lag)

    def ols(tk, win):
        df = pd.concat([y[tk], x[["sox", "t10"]]], axis=1).dropna().tail(win)
        X = np.column_stack([np.ones(len(df)), df.sox, df.t10])
        b, *_ = np.linalg.lstsq(X, df[tk].values, rcond=None)
        pred = X @ b
        ss = ((df[tk] - df[tk].mean()) ** 2).sum()
        return {"sox_beta": rnd(b[1]), "t10_per10bp": rnd(b[2] * 10, 2), "r2": rnd(1 - ((df[tk] - pred) ** 2).sum() / ss)}

    table = []
    for tk in ["^N225"] + list(JP_NAMES):
        if tk not in y:
            continue
        table.append({"ticker": tk, "name": JP_NAMES.get(tk, "日経平均"), "d120": ols(tk, 120), "d250": ols(tk, 250)})
    n = pd.concat([y["^N225"], x[["sox"]]], axis=1).dropna()
    big_down = n[n.sox < -3]
    huge_down = n[n.sox < -5]
    last = f.dropna().iloc[-1]
    corr_rate = pd.concat([us["^GSPC"].pct_change(), us["^TNX"].diff()], axis=1).dropna()
    corr_rate.columns = ["spx", "t10"]
    return {
        "table": table,
        "after_sox_down3": {"n": len(big_down), "nikkei_mean": rnd(big_down["^N225"].mean()),
                            "nikkei_win": rnd((big_down["^N225"] > 0).mean() * 100, 0)},
        "after_sox_down5": {"n": len(huge_down), "nikkei_mean": rnd(huge_down["^N225"].mean()),
                            "nikkei_win": rnd((huge_down["^N225"] > 0).mean() * 100, 0),
                            "nikkei_worst": rnd(huge_down["^N225"].min())},
        "last_us": {"date": str(f.dropna().index[-1].date()), "sox": rnd(last.sox), "ndx": rnd(last.ndx),
                    "spx": rnd(last.spx), "t10_bp": rnd(last.t10, 1), "usdjpy_pct": rnd(fx.dropna().iloc[-1])},
        "spx_vs_10y_corr60": rnd(corr_rate.spx.tail(60).corr(corr_rate.t10.tail(60))),
        "spx_vs_10y_corr250": rnd(corr_rate.spx.tail(250).corr(corr_rate.t10.tail(250))),
        "tnx_level": rnd(us["^TNX"].dropna().iloc[-1]),
    }


def hyperscaler_memory():
    """capex負担とメモリ株のバリュエーション。決算データはyfinance準拠。"""
    rows = []
    for t in HYPERSCALERS:
        try:
            k = yf.Ticker(t)
            cf = k.quarterly_cashflow
            inc = k.quarterly_income_stmt
            info = k.get_info()
            capex = -cf.loc["Capital Expenditure"].dropna()
            ocf = cf.loc["Operating Cash Flow"].dropna()
            rev = inc.loc["Total Revenue"].dropna()
            c4, o4, r4 = capex.iloc[:4].sum(), ocf.iloc[:4].sum(), rev.iloc[:4].sum()
            rows.append({
                "t": t, "last_q": str(capex.index[0].date()),
                "stale": (pd.Timestamp.now() - capex.index[0]).days > 110, "capex_ttm_bn": rnd(c4 / 1e9, 1), "capex_sales": rnd(c4 / r4 * 100, 1),
                "capex_ocf": rnd(c4 / o4 * 100, 0), "fcf_ttm_bn": rnd((o4 - c4) / 1e9, 1),
                "capex_yoy": rnd((capex.iloc[0] / capex.iloc[4] - 1) * 100, 0) if len(capex) > 4 else None,
                "fwd_pe": rnd(info.get("forwardPE"), 1),
            })
        except Exception as e:
            print(f"[warn] {t}: {e}", file=sys.stderr)
    mem = []
    px = closes(MEMORY + ["^SOX"], period="2y")
    for t in MEMORY:
        try:
            k = yf.Ticker(t)
            info = k.get_info()
            s = k.history(period="2y", auto_adjust=True)["Close"].dropna()  # downloadは分割未調整の場合がある
            mem.append({
                "t": t, "trailing_pe": rnd(info.get("trailingPE"), 1), "fwd_pe": rnd(info.get("forwardPE"), 1),
                "pb": rnd(info.get("priceToBook"), 1), "op_margin": rnd((info.get("operatingMargins") or np.nan) * 100, 0),
                "ret_1d": rnd((s.iloc[-1] / s.iloc[-2] - 1) * 100, 1), "ret_1m": rnd((s.iloc[-1] / s.iloc[-22] - 1) * 100, 1),
                "from_high": rnd((s.iloc[-1] / s.max() - 1) * 100, 1),
            })
        except Exception as e:
            print(f"[warn] {t}: {e}", file=sys.stderr)
    # 米メモリの当日→翌営業日のキオクシアは transmission と同様に翌日対応
    lead = None
    if "285A.T" in px and "MU" in px:
        mu = px[["MU", "SNDK"]].mean(axis=1).pct_change().dropna() * 100
        mu.index = mu.index + pd.Timedelta(days=1)
        k = px["285A.T"].pct_change().dropna() * 100
        j = next_session_align(k.index, mu.rename("us").to_frame())
        j["k"] = k
        j = j.dropna().tail(120)
        lead = {"corr": rnd(j.k.corr(j.us)), "beta": rnd(np.polyfit(j.us, j.k, 1)[0]), "n": len(j)}
    return {"hyperscalers": rows, "memory": mem, "kioxia_vs_us_memory": lead}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes")}
    for name, fn in (("intraday_jp", intraday_jp), ("dispersion", dispersion), ("volume_bottom", volume_bottom),
                     ("transmission", transmission), ("hyperscaler_memory", hyperscaler_memory)):
        try:
            out[name] = fn()
        except Exception as e:  # 1検証の失敗で全体を止めない。ページ側で欠損表示する
            print(f"[error] {name}: {e}", file=sys.stderr)
            out[name] = None
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
