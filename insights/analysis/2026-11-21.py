"""Insights edition 2026-11-21 (covers US session 2026-11-20)."""
import json, numpy as np, pandas as pd
D = pd.read_parquet('/tmp/market-data/daily.parquet')
P = D.pivot(index='date', columns='ticker', values='close').sort_index()
O = D.pivot(index='date', columns='ticker', values='open').sort_index()
F = pd.read_parquet('/tmp/market-data/fred.parquet')
ASOF = pd.Timestamp('2026-11-20')
P = P.loc[:ASOF]; O = O.loc[:ASOF]
R = P.pct_change(fill_method=None) * 100
out = {}

def fwd(s, dates, h):
    idx = s.dropna().index
    res = []
    for d in dates:
        i = idx.get_loc(d)
        res.append(round((s.loc[idx[i + h]] / s.loc[d] - 1) * 100, 2) if i + h < len(idx) else None)
    return res

def declutter(dates, gap=20, idx=None):
    keep = []; last = None
    for d in dates:
        if last is None or idx.get_loc(d) - idx.get_loc(last) > gap:
            keep.append(d)
        last = d if (last is None or idx.get_loc(d) - idx.get_loc(last) > gap) else last
    return keep

def summ(v):
    v = [x for x in v if x is not None]
    return {'n': len(v), 'median': round(float(np.median(v)), 2) if v else None,
            'pct_up': round(100 * np.mean([x > 0 for x in v]), 0) if v else None,
            'min': min(v) if v else None, 'max': max(v) if v else None}

# A. SOX <= -8% days
sox = P['^SOX'].dropna(); rs = sox.pct_change() * 100
ev = rs[rs <= -8].index
ev_first = declutter(list(ev), 20, sox.index)
A = {'today_sox': round(rs.iloc[-1], 2), 'n_all': len(ev), 'n_first_in_20d': len(ev_first), 'events': []}
spx = P['^GSPC'].dropna()
for d in ev:
    A['events'].append({'date': str(d.date()), 'sox_1d': round(rs.loc[d], 2),
        'sox_5d': fwd(sox, [d], 5)[0], 'sox_20d': fwd(sox, [d], 20)[0], 'sox_60d': fwd(sox, [d], 60)[0],
        'spx_20d': fwd(spx, [d], 20)[0] if d in spx.index else None, 'first_in_20d': d in ev_first})
for h in (5, 20, 60):
    A[f'sox_{h}d_all'] = summ([e[f'sox_{h}d'] for e in A['events'] if e['date'] != '2026-11-20'])
    A[f'sox_{h}d_first'] = summ([e[f'sox_{h}d'] for e in A['events'] if e['first_in_20d'] and e['date'] != '2026-11-20'])
base = sox.pct_change(20).dropna() * 100
A['sox_20d_unconditional_median'] = round(base.median(), 2)
A['sox_dd_from_high'] = round((sox.iloc[-1] / sox.loc['2026-01-01':].max() - 1) * 100, 2)
A['sox_high_date'] = str(sox.loc['2026-01-01':].idxmax().date())
A['events_since_2026_count'] = int((ev >= '2026-01-01').sum())
out['A_sox_crash'] = A

# B. NVDA: idiosyncratic vs sector
names = ['NVDA', 'AMD', 'MU', 'SNDK', 'TSM', 'ASML', 'ARM', 'CRWV', 'NBIS', 'ORCL', 'ANT', 'GOOGL', 'MSFT', 'META', 'AMZN', 'AAPL']
B = {'day': {n: round(R[n].iloc[-1], 2) for n in names}, 'smh': round(R['SMH'].iloc[-1], 2)}
win = R.loc[:'2026-11-19'].tail(250)
betas = {}
for n in ['NVDA', 'AMD', 'MU', 'TSM', 'SNDK']:
    x = win[['SMH', n]].dropna()
    b = np.cov(x[n], x['SMH'])[0, 1] / x['SMH'].var()
    betas[n] = {'beta_smh_250d': round(b, 2), 'expected': round(b * B['smh'], 2), 'actual': B['day'][n],
                'residual': round(B['day'][n] - b * B['smh'], 2), 'resid_sd_250d': round((x[n] - b * x['SMH']).std(), 2)}
B['betas'] = betas
nv = P['NVDA'].dropna()
B['nvda_close'] = round(nv.iloc[-1], 2)
B['nvda_dd_from_high'] = round((nv.iloc[-1] / nv.loc['2026-01-01':].max() - 1) * 100, 2)
B['nvda_high_date'] = str(nv.loc['2026-01-01':].idxmax().date())
wk = nv.resample('W-FRI').last().pct_change() * 100
streak = 0
for v in wk.iloc[::-1]:
    if v < 0: streak += 1
    else: break
B['nvda_weekly_down_streak'] = streak
B['nvda_streak_return'] = round((nv.iloc[-1] / nv.resample('W-FRI').last().iloc[-streak - 1] - 1) * 100, 2)
B['ant_close'] = round(P['ANT'].dropna().iloc[-1], 2)
B['ant_vs_ipo83'] = round((P['ANT'].dropna().iloc[-1] / 83 - 1) * 100, 2)
# NVDA <=-10% days since 2015 forward
rn = nv.pct_change() * 100
evn = rn.loc['2010-01-01':][rn.loc['2010-01-01':] <= -10].index
B['nvda_le_-10_since2010'] = [{'date': str(d.date()), 'r': round(rn.loc[d], 2), 'f20': fwd(nv, [d], 20)[0], 'f60': fwd(nv, [d], 60)[0]} for d in evn]
B['nvda_le_-10_f20'] = summ([e['f20'] for e in B['nvda_le_-10_since2010'] if e['date'] != '2026-11-20'])
B['nvda_le_-10_f60'] = summ([e['f60'] for e in B['nvda_le_-10_since2010'] if e['date'] != '2026-11-20'])
out['B_nvda_vs_sector'] = B

# C. stocks and gold down >=3% same day; bonds
g = P['GC=F']; si = P['SI=F']
both = R.index[(R['^GSPC'] <= -3) & (R['GC=F'] <= -3)]
C = {'today': {k: round(R[k].iloc[-1], 2) for k in ['^GSPC', 'GC=F', 'SI=F', 'HG=F', 'BTC-USD', 'TLT', 'IEF', 'LQD', 'HYG', 'CL=F', 'JPY=X', 'DX-Y.NYB', 'GDX']},
     'tnx_bp': round((P['^TNX'].iloc[-1] - P['^TNX'].iloc[-2]) * 100, 1),
     'fvx_bp': round((P['^FVX'].iloc[-1] - P['^FVX'].iloc[-2]) * 100, 1),
     'irx_bp': round((P['^IRX'].iloc[-1] - P['^IRX'].iloc[-2]) * 100, 1),
     'events': []}
for d in both:
    C['events'].append({'date': str(d.date()), 'spx': round(R.loc[d, '^GSPC'], 2), 'gold': round(R.loc[d, 'GC=F'], 2),
                        'tlt': round(R.loc[d, 'TLT'], 2) if not np.isnan(R.loc[d, 'TLT']) else None,
                        'gold_20d': fwd(g, [d], 20)[0], 'spx_20d': fwd(spx, [d], 20)[0]})
C['gold_dd_from_high'] = round((g.iloc[-1] / g.loc['2026-01-01':].max() - 1) * 100, 2)
C['gold_high_date'] = str(g.loc['2026-01-01':].idxmax().date())
# gold vs SPX 60d correlation now vs history
_x = R[['^GSPC', 'GC=F', 'TLT']].dropna()
cc = _x['^GSPC'].rolling(60).corr(_x['GC=F'])
C['corr_spx_gold_60d_now'] = round(cc.iloc[-1], 2)
C['corr_spx_gold_60d_pct_since2005'] = round((cc.loc['2005':] < cc.iloc[-1]).mean() * 100, 1)
cb = _x['^GSPC'].rolling(20).corr(_x['TLT'])
C['corr_spx_tlt_20d_now'] = round(cb.iloc[-1], 2)
C['corr_spx_tlt_20d_5dago'] = round(cb.iloc[-6], 2)
# 10y move on SPX <= -3% days, 2022-2026 vs earlier
big = R.index[R['^GSPC'] <= -3]
tnxd = P['^TNX'].diff() * 100
C['tnx_bp_on_spx_le_-3'] = {'2000-2021_median': round(tnxd.loc[big[big < '2022-01-01']].median(), 1),
                            '2022-2026_median': round(tnxd.loc[big[big >= '2022-01-01']].median(), 1),
                            'n_2022_2026': int((big >= '2022-01-01').sum()),
                            'pct_yield_down_2022_2026': round((tnxd.loc[big[big >= '2022-01-01']] < 0).mean() * 100, 0)}
out['C_cross_asset'] = C

# D. Breakevens / inflation expectations vs hike pricing
fr = F.pivot_table(index='date', columns='series', values='value')
Dd = {}
for s in ['T10YIE', 'T5YIFR', 'DFII10', 'DGS2', 'DGS10', 'T10Y3M', 'T5YIE']:
    if s in fr.columns:
        x = fr[s].dropna()
        Dd[s] = {'last': float(x.iloc[-1]), 'last_date': str(x.index[-1].date()),
                 'chg_5obs': round(float(x.iloc[-1] - x.iloc[-6]), 3), 'chg_21obs': round(float(x.iloc[-1] - x.iloc[-22]), 3),
                 'min_since': str(x[x <= x.iloc[-1]].index[-2].date()) if (x[:-1] <= x.iloc[-1]).any() else 'none'}
        Dd[s]['recent'] = {str(k.date()): float(v) for k, v in x.tail(6).items()}
out['D_breakevens'] = Dd
out['D_fred_columns_sample'] = list(fr.columns)[:5]

# E. VIX and S&P losing streak
vix = P['^VIX'].dropna()
E = {'vix': round(vix.iloc[-1], 2), 'vix9d': round(P['^VIX9D'].iloc[-1], 2), 'vix3m': round(P['^VIX3M'].iloc[-1], 2),
     'vxn': round(P['^VXN'].iloc[-1], 2)}
# first close >=35 after 60 days below
cross = [d for i, d in enumerate(vix.index[1:], 1) if vix.iloc[i] >= 35 and (vix.iloc[max(0, i - 60):i] < 35).all()]
E['vix_first_ge35'] = [{'date': str(d.date()), 'vix': round(vix.loc[d], 1), 'spx_5d': fwd(spx, [d], 5)[0],
                         'spx_20d': fwd(spx, [d], 20)[0], 'spx_60d': fwd(spx, [d], 60)[0],
                         'spx_min_next20_pct': round((spx.loc[d:].iloc[1:21].min() / spx.loc[d] - 1) * 100, 2) if len(spx.loc[d:]) > 1 else None} for d in cross]
for h in (5, 20, 60):
    E[f'vix35_spx_{h}d'] = summ([e[f'spx_{h}d'] for e in E['vix_first_ge35'] if e['date'] != '2026-11-20'])
E['vix35_min_next20'] = summ([e['spx_min_next20_pct'] for e in E['vix_first_ge35'] if e['date'] != '2026-11-20'])
r_spx = spx.pct_change()
st = (r_spx < 0).astype(int); run = st.groupby((st != st.shift()).cumsum()).cumsum() * st
E['spx_streak_now'] = int(run.iloc[-1])
E['spx_streak_cum'] = round((spx.iloc[-1] / spx.iloc[-1 - int(run.iloc[-1])] - 1) * 100, 2)
s7 = run[(run == 7)].index
E['spx_7day_streaks'] = [{'date': str(d.date()), 'f20': fwd(spx, [d], 20)[0]} for d in s7]
E['spx_dd_from_high'] = round((spx.iloc[-1] / spx.max() - 1) * 100, 2)
E['spx_high_date'] = str(spx.idxmax().date())
E['ndx_ytd'] = round((P['^NDX'].iloc[-1] / P['^NDX'].loc[:'2025-12-31'].iloc[-1] - 1) * 100, 2)
E['spx_ytd'] = round((spx.iloc[-1] / spx.loc[:'2025-12-31'].iloc[-1] - 1) * 100, 2)
E['rsp_ytd'] = round((P['RSP'].iloc[-1] / P['RSP'].loc[:'2025-12-31'].iloc[-1] - 1) * 100, 2)
E['rsp_minus_spy_1d'] = round(R['RSP'].iloc[-1] - R['SPY'].iloc[-1], 2)
sec = ['XLK', 'XLC', 'XLY', 'XLF', 'XLI', 'XLV', 'XLP', 'XLU', 'XLE', 'XLB', 'XLRE']
E['sectors_1d'] = {s: round(R[s].iloc[-1], 2) for s in sec}
E['sectors_ytd'] = {s: round((P[s].iloc[-1] / P[s].loc[:'2025-12-31'].iloc[-1] - 1) * 100, 2) for s in sec}
out['E_vix_streak'] = E

# J. Japan: NKD vs N225, holiday
n225 = P['^N225'].dropna()
out['J_japan'] = {'nkd': round(P['NKD=F'].iloc[-1], 0), 'nkd_1d': round(R['NKD=F'].iloc[-1], 2),
                  'n225_last': round(n225.iloc[-1], 0), 'n225_last_date': str(n225.index[-1].date()),
                  'nkd_vs_n225_pct': round((P['NKD=F'].iloc[-1] / n225.iloc[-1] - 1) * 100, 2),
                  'ewj_1d': round(R['DXJ'].iloc[-1], 2), 'ewt_1d': round(R['EWT'].iloc[-1], 2), 'ewy_1d': round(R['EWY'].iloc[-1], 2),
                  'tel_8035_last': str(P['8035.T'].dropna().index[-1].date()), 'jpy': round(P['JPY=X'].iloc[-1], 2)}
json.dump(out, open('/home/user/market-hp/insights/data/analysis/2026-11-21.json', 'w'), ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, default=str)[:200])
