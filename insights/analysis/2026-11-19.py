"""分析の視点 2026-11-19: 米国 11/18 (エヌビディア決算翌日、FOMC議事要旨) を対象"""
import json, pandas as pd, numpy as np
ASOF = pd.Timestamp('2026-11-18')
d = pd.read_parquet('/tmp/market-data/daily.parquet'); d['date'] = pd.to_datetime(d['date'])
d = d[d.date <= ASOF]
P = d.pivot(index='date', columns='ticker', values='close')
O = d.pivot(index='date', columns='ticker', values='open')
H = d.pivot(index='date', columns='ticker', values='high')
out = {}
def r(a, b, t):
    s = P[t].dropna(); return round((s.loc[:b].iloc[-1] / s.loc[:a].iloc[-1] - 1) * 100, 2)
def last(t): s = P[t].dropna(); return str(s.index[-1].date()), round(float(s.iloc[-1]), 4)

# A. NVDA: 寄り付きで上げて引けで下げた日(ギャップアップ後の反落)
nv = P['NVDA'].dropna(); nvo = O['NVDA'].reindex(nv.index)
prev = nv.shift(1)
gap = (nvo / prev - 1) * 100; ret = (nv / prev - 1) * 100
cond = (gap >= 2) & (ret <= -2)
ev = []
for dt in cond[cond].index:
    i = nv.index.get_loc(dt)
    f = lambda k: round((nv.iloc[i + k] / nv.iloc[i] - 1) * 100, 1) if i + k < len(nv) else None
    ev.append({'date': str(dt.date()), 'gap': round(gap[dt], 1), 'ret': round(ret[dt], 1), 'f5': f(5), 'f20': f(20), 'f60': f(60)})
evd = pd.DataFrame(ev)
done20 = evd.dropna(subset=['f20'])
# 連続安
streak = 0
for x in ret.iloc[::-1]:
    if x < 0: streak += 1
    else: break
hi = nv.rolling(252, min_periods=200).max()
out['nvda'] = {'close': last('NVDA'), 'open': round(float(nvo.iloc[-1]), 2), 'high': round(float(H['NVDA'].loc[ASOF]), 2),
               'gap_pct': round(float(gap.iloc[-1]), 2), 'ret_pct': round(float(ret.iloc[-1]), 2),
               'open_to_close': round(float((nv.iloc[-1] / nvo.iloc[-1] - 1) * 100), 2),
               'down_streak': streak, 'dd_252high': round(float((nv.iloc[-1] / hi.iloc[-1] - 1) * 100), 1),
               'events_gap2_close_m2': ev, 'n': int(len(evd)), 'n_f20': int(len(done20)),
               'f5_med': round(float(evd.f5.dropna().median()), 1) if len(evd) else None,
               'f20_med': round(float(done20.f20.median()), 1) if len(done20) else None,
               'f20_up_pct': round(float((done20.f20 > 0).mean() * 100), 1) if len(done20) else None,
               'f60_med': round(float(evd.f60.dropna().median()), 1),
               'all_f20_med': round(float(((nv.shift(-20) / nv - 1) * 100).dropna().median()), 1)}
peers = ['NVDA', 'AMD', 'TSM', 'MU', 'SNDK', 'CRWV', 'NBIS', 'ORCL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'AAPL', 'ASML', 'ARM', 'SMH', 'SOXX', 'QQQ', 'SPY', 'RSP', '^DJI', '^GSPC', '^NDX', '^RUT']
out['day'] = {t: r('2026-11-17', '2026-11-18', t) for t in peers}
out['day_o2c'] = {t: round(float((P[t].loc[ASOF] / O[t].loc[ASOF] - 1) * 100), 2) for t in peers if not pd.isna(O[t].loc[ASOF])}

# B. 金利と半導体: 10年金利の変化と SMH の日次相関 (60日ローリング)
tnx = P['^TNX'].dropna(); smh = P['SMH'].dropna()
j = pd.concat([tnx.diff(), smh.pct_change()], axis=1, keys=['dy', 'r']).dropna()
j = j[j.index >= '2010-01-01']
rc = j['dy'].rolling(60).corr(j['r'])
yr = j.groupby(j.index.year).apply(lambda x: round(float(x.dy.corr(x.r)), 2))
# 10年金利が1日+5bp以上の日のSMH
big = j[j.dy >= 0.05]
out['rates_semis'] = {'tnx': last('^TNX'), 'tnx_chg_bp_1d': round(float(tnx.diff().iloc[-1] * 100), 1),
                      'tnx_1m_bp': round(float((tnx.iloc[-1] - tnx.loc[:'2026-10-16'].iloc[-1]) * 100), 1),
                      'irx': last('^IRX'), 'fvx': last('^FVX'),
                      'corr60_now': round(float(rc.iloc[-1]), 2), 'corr60_pctile_since2010': round(float((rc.dropna() < rc.iloc[-1]).mean() * 100), 1),
                      'corr60_min_since2010': round(float(rc.min()), 2), 'corr_by_year': {int(k): v for k, v in yr.items() if k >= 2018},
                      'smh_on_yield_up5bp': {'all_since2010': {'n': int(len(big)), 'med': round(float(big.r.median() * 100), 2), 'up_pct': round(float((big.r > 0).mean() * 100), 1)},
                                             '2026': {'n': int(len(big[big.index.year == 2026])), 'med': round(float(big[big.index.year == 2026].r.median() * 100), 2),
                                                      'up_pct': round(float((big[big.index.year == 2026].r > 0).mean() * 100), 1)}}}
f = pd.read_parquet('/tmp/market-data/fred.parquet'); f['date'] = pd.to_datetime(f['date'])
F = f.pivot(index='date', columns='series', values='value')
core = F['CPILFESL'].dropna()
out['rates_semis']['core_cpi'] = {'last': str(core.index[-1].date()), 'yoy': round(float((core.iloc[-1] / core.iloc[-13] - 1) * 100), 2),
                                  'ann3m': round(float(((core.iloc[-1] / core.iloc[-4]) ** 4 - 1) * 100), 2)}
for s in ['T10YIE', 'DFII10', 'DGS2', 'T5YIFR']:
    x = F[s].dropna(); out['rates_semis'][s] = {'date': str(x.index[-1].date()), 'v': float(x.iloc[-1]), 'chg_1m': round(float(x.iloc[-1] - x.loc[:x.index[-1] - pd.Timedelta(days=30)].iloc[-1]), 2)}

# C. S&P500 5日続落: 過去の5日以上続落の後
sp = P['^GSPC'].dropna(); spr = sp.pct_change()
dn = (spr < 0).astype(int)
run = dn.groupby((dn != dn.shift()).cumsum()).cumsum() * dn
vix = P['^VIX'].dropna()
hi_sp = sp.cummax()
ev = []
for dt in run[run == 5].index:
    i = sp.index.get_loc(dt)
    g = lambda k: round((sp.iloc[i + k] / sp.iloc[i] - 1) * 100, 2) if i + k < len(sp) else None
    ev.append({'date': str(dt.date()), 'cum5': round((sp.iloc[i] / sp.iloc[i - 5] - 1) * 100, 2), 'vix': round(float(vix.loc[:dt].iloc[-1]), 1),
               'dd': round(float((sp.iloc[i] / sp.loc[:dt].iloc[-252:].max() - 1) * 100), 1), 'f5': g(5), 'f20': g(20), 'f60': g(60)})
E = pd.DataFrame(ev)
E20 = E.dropna(subset=['f20'])
allf20 = ((sp.shift(-20) / sp - 1) * 100).dropna()
sub = E20[(E20.vix >= 20)]
out['streak'] = {'run_now': int(run.iloc[-1]), 'cum': round(float((sp.iloc[-1] / sp.iloc[-1 - int(run.iloc[-1])] - 1) * 100), 2),
                 'close': last('^GSPC'), 'dd_1y': round(float((sp.iloc[-1] / sp.iloc[-252:].max() - 1) * 100), 2),
                 'n': int(len(E20)), 'f5_med': round(float(E20.f5.median()), 2), 'f20_med': round(float(E20.f20.median()), 2),
                 'f20_up': round(float((E20.f20 > 0).mean() * 100), 1), 'f60_med': round(float(E.f60.dropna().median()), 2),
                 'base_f20_med': round(float(allf20.median()), 2), 'base_f20_up': round(float((allf20 > 0).mean() * 100), 1),
                 'vix20': {'n': int(len(sub)), 'f20_med': round(float(sub.f20.median()), 2), 'f20_up': round(float((sub.f20 > 0).mean() * 100), 1),
                           'f20_min': round(float(sub.f20.min()), 2)},
                 'recent': ev[-12:], 'vix': last('^VIX'), 'vix3m': last('^VIX3M'), 'vvix': last('^VVIX')}

# D. ダウとS&P500の差
dj = P['^DJI'].dropna()
spread = (dj.pct_change() - sp.pct_change()).dropna() * 100
s250 = spread.iloc[-251:-1].std()
out['dow'] = {'dji': last('^DJI'), 'dji_1d': r('2026-11-17', '2026-11-18', '^DJI'), 'spx_1d': r('2026-11-17', '2026-11-18', '^GSPC'),
              'ndx_1d': r('2026-11-17', '2026-11-18', '^NDX'), 'rsp_1d': r('2026-11-17', '2026-11-18', 'RSP'), 'rut_1d': r('2026-11-17', '2026-11-18', '^RUT'),
              'spread': round(float(spread.iloc[-1]), 2), 'sd250': round(float(s250), 2), 'sigma': round(float(spread.iloc[-1] / s250), 1),
              'n_3y_as_low': int((spread.iloc[-757:-1] <= spread.iloc[-1]).sum())}
sec = ['XLK', 'XLC', 'XLY', 'XLF', 'XLI', 'XLE', 'XLB', 'XLRE', 'XLU', 'XLP', 'XLV', 'KRE', 'IGV', 'XRT', 'ITB']
out['sectors_1d'] = {t: r('2026-11-17', '2026-11-18', t) for t in sec}
try:
    px = pd.read_parquet('daily-review/data/prices.parquet'); px['date'] = pd.to_datetime(px['date'])
    C = px.pivot(index='date', columns='ticker', values='close')
    out['sp500_data_last'] = str(C.index.max().date())
    if C.index.max() >= ASOF:
        dow30 = ['AAPL','AMGN','AMZN','AXP','BA','CAT','CRM','CSCO','CVX','DIS','GS','HD','HON','IBM','JNJ','JPM','KO','MCD','MMM','MRK','MSFT','NKE','NVDA','PG','SHW','TRV','UNH','V','VZ','WMT']
        dp = (C.loc[ASOF, dow30] - C.loc['2026-11-17', dow30]).dropna()
        out['dow_contrib_share'] = {k: round(float(v / dp.sum() * 100), 1) for k, v in dp.sort_values().items()}
        x = C.pct_change(fill_method=None).loc[ASOF].dropna()
        out['breadth_1118'] = {'n': int(len(x)), 'up_pct': round(float((x > 0).mean() * 100), 1), 'median': round(float(x.median() * 100), 2)}
except Exception as e:
    out['sp500_err'] = str(e)

# E. AIの大型株とアンソロピックのロードショー(11/10開始と報道)
cohort = ['NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'ORCL', 'AMD', 'TSM', 'MU', 'CRWV', 'NBIS', 'ARM', 'AAPL']
out['ipo'] = {'since_1109': {t: r('2026-11-09', '2026-11-18', t) for t in cohort + ['SPY', 'RSP', 'QQQ', 'SMH', 'XLP', 'XLV', 'XLU']}}
z = pd.Series(out['ipo']['since_1109'])
out['ipo']['cohort_median'] = round(float(z[cohort].median()), 2)
out['ipo']['cohort_mean'] = round(float(z[cohort].mean()), 2)
# 出来高: QQQ, SMH, NVDA の 11/10 以降の平均 ÷ 直前60日平均
V = d.pivot(index='date', columns='ticker', values='volume')
out['ipo']['vol_ratio'] = {t: round(float(V[t].loc['2026-11-10':ASOF].mean() / V[t].loc[:'2026-11-09'].iloc[-60:].mean()), 2) for t in ['NVDA', 'QQQ', 'SMH', 'SPY', 'MSFT', 'GOOGL']}

# F. ドルと円
jpy = P['JPY=X'].dropna(); dxy = P['DX-Y.NYB'].dropna()
jr = jpy.pct_change() * 100
big_down = jr[jr <= -2].loc['2022':]
out['fx'] = {'usdjpy': last('JPY=X'), 'usdjpy_1m': r('2026-10-16', '2026-11-18', 'JPY=X'), 'dxy': last('DX-Y.NYB'), 'dxy_1m': r('2026-10-16', '2026-11-18', 'DX-Y.NYB'),
             'dxy_hi_since': str(dxy[dxy >= dxy.iloc[-1]].index[-2].date()) if (dxy >= dxy.iloc[-1]).sum() > 1 else None,
             'usdjpy_max_2y': round(float(jpy.loc['2024-11-18':].max()), 2), 'usdjpy_max_2y_date': str(jpy.loc['2024-11-18':].idxmax().date()),
             'days_above_159_2026': int((jpy.loc['2026'] >= 159).sum()),
             'jpy_drop_days_2pct_since2022': [{'date': str(k.date()), 'chg': round(float(v), 2)} for k, v in big_down.items()],
             'eurusd_1m': r('2026-10-16', '2026-11-18', 'EURUSD=X'), 'krw_1m': r('2026-10-16', '2026-11-18', 'KRW=X'), 'twd_1m': r('2026-10-16', '2026-11-18', 'TWD=X')}
# 円と米10年金利の相関(60日)
k = pd.concat([tnx.diff(), jpy.pct_change()], axis=1, keys=['dy', 'fx']).dropna()
out['fx']['corr60_usdjpy_tnx'] = round(float(k.iloc[-60:].dy.corr(k.iloc[-60:].fx)), 2)
out['fx']['corr60_usdjpy_tnx_2025'] = round(float(k.loc['2025'].dy.corr(k.loc['2025'].fx)), 2)
# 介入後(-2%以上の円高日)の20日
ev = []
for dt in big_down.index:
    i = jpy.index.get_loc(dt)
    ev.append({'date': str(dt.date()), 'chg': round(float(jr[dt]), 2), 'f20': round((jpy.iloc[i + 20] / jpy.iloc[i] - 1) * 100, 2) if i + 20 < len(jpy) else None,
               'n225_f20': None})
out['fx']['after_big_yen_up'] = ev
for e_ in ev:
    n = P['^N225'].dropna()
    dt = pd.Timestamp(e_['date'])
    try:
        i = n.index.get_indexer([dt], method='bfill')[0]
        e_['n225_d0'] = round((n.iloc[i] / n.iloc[i - 1] - 1) * 100, 2)
        e_['n225_f20'] = round((n.iloc[i + 20] / n.iloc[i] - 1) * 100, 2) if i + 20 < len(n) else None
    except Exception:
        pass

# G. 商品の同時安 (金・銀・銅がそろって-3%以下)
R = P[["GC=F", "SI=F", "HG=F"]].pct_change()
jd = R[(R <= -0.03).all(axis=1)].index
ev = []
for dt in jd:
    row = {"date": str(dt.date())}
    for t in ["HG=F", "GC=F", "^GSPC", "CL=F"]:
        s = P[t].dropna(); i = s.index.get_indexer([dt], method="bfill")[0]
        row[t + "_f20"] = round((s.iloc[i + 20] / s.iloc[i] - 1) * 100, 2) if i + 20 < len(s) else None
    ev.append(row)
E = pd.DataFrame(ev).dropna()
cg = (P["HG=F"] / P["GC=F"]).dropna()
out["commod"] = {"day": {t: r("2026-11-17", "2026-11-18", t) for t in ["GC=F", "SI=F", "HG=F", "PL=F", "CL=F", "BZ=F", "NG=F", "BTC-USD", "COPX", "GDX", "URA", "XLE", "DX-Y.NYB", "MXN=X", "EWW", "EWZ"]},
                 "m1": {t: r("2026-10-16", "2026-11-18", t) for t in ["GC=F", "SI=F", "HG=F", "CL=F", "BTC-USD", "COPX"]},
                 "hg_sigma": round(float(P["HG=F"].pct_change().iloc[-1] / P["HG=F"].pct_change().iloc[-251:-1].std()), 1),
                 "joint_days": [str(x.date()) for x in jd], "n_done": int(len(E)),
                 "f20_med": {c: round(float(E[c].median()), 2) for c in E.columns if c != "date"},
                 "f20_up": {c: round(float((E[c] > 0).mean() * 100), 1) for c in E.columns if c != "date"},
                 "events": ev,
                 "cu_gold_ratio": {"now": round(float(cg.iloc[-1] * 1000), 3), "pctile_5y": round(float((cg.iloc[-1260:] < cg.iloc[-1]).mean() * 100), 1), "chg_1m_pct": round(float((cg.iloc[-1] / cg.loc[:"2026-10-16"].iloc[-1] - 1) * 100), 2)}}

json.dump(out, open('insights/data/analysis/2026-11-19.json', 'w'), ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, default=str)[:12000])
