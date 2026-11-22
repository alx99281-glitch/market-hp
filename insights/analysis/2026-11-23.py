"""Weekend edition 2026-11-23 (SGT). Data through 2026-11-20 NY close."""
import json, numpy as np, pandas as pd
D = pd.read_parquet('/tmp/market-data/daily.parquet'); D['date'] = pd.to_datetime(D['date'])
P = pd.read_parquet('daily-review/data/prices.parquet'); P['date'] = pd.to_datetime(P['date'])
px = D.pivot_table(index='date', columns='ticker', values='close')
out = {}
def r(x, n=2): return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)
def stats(s):
    s = s.dropna(); return {'n': int(len(s)), 'median': r(s.median()), 'mean': r(s.mean()), 'up_pct': r((s > 0).mean()*100, 0), 'min': r(s.min()), 'max': r(s.max())}

# A. worst weeks and the following period
res = {}
for tk, th in [('^GSPC', -7.0), ('^NDX', -9.0)]:
    s = px[tk].dropna()
    wk = s.resample('W-FRI').last().dropna()
    wr = wk.pct_change()*100
    ev = wr[wr <= th]
    rows = []
    for d, v in ev.items():
        i = s.index.get_indexer([s.index[s.index <= d][-1]])[0]
        f = lambda k: (s.iloc[i+k]/s.iloc[i]-1)*100 if i+k < len(s) else np.nan
        rows.append({'week_end': str(d.date()), 'week_pct': r(v), 'next_day': r(f(1)), 'next_5d': r(f(5)), 'next_20d': r(f(20)), 'next_60d': r(f(60))})
    df = pd.DataFrame(rows)
    # de-cluster: first event with no other within prior 8 weeks
    dts = pd.to_datetime(df.week_end); first = [k == 0 or (dts[k]-dts[k-1]).days > 56 for k in range(len(dts))]
    res[tk] = {'threshold': th, 'events': rows,
               'all': {c: stats(df[c]) for c in ['next_day', 'next_5d', 'next_20d', 'next_60d']},
               'first_only': {c: stats(df[first][c]) for c in ['next_day', 'next_5d', 'next_20d', 'next_60d']},
               'latest_week_pct': r(wr.iloc[-1])}
out['worst_week'] = res
# Nikkei on the next Tokyo session after S&P week <= -7%
s = px['^GSPC'].dropna(); n2 = px['^N225'].dropna()
wk = s.resample('W-FRI').last().pct_change()*100
nk = []
for d, v in wk[wk <= -7].items():
    fri = s.index[s.index <= d][-1]; nxt = n2.index[n2.index > fri]
    if len(nxt) and fri in n2.index or len(n2.index[n2.index <= fri]):
        prev = n2[n2.index <= fri].iloc[-1]
        if len(nxt): nk.append({'week_end': str(d.date()), 'nikkei_next_session': r((n2[nxt[0]]/prev-1)*100), 'session': str(nxt[0].date())})
out['worst_week']['nikkei_next'] = nk
out['worst_week']['nikkei_next_stats'] = stats(pd.Series([x['nikkei_next_session'] for x in nk]))

# Thanksgiving week: Fri before -> Fri after (half day)
tg = []
for y in range(2000, 2026):
    nov = pd.date_range(f'{y}-11-01', f'{y}-11-30'); thu = [d for d in nov if d.weekday() == 3][3]
    fb = s[s.index <= thu - pd.Timedelta(days=6)].iloc[-1]; fbd = s.index[s.index <= thu - pd.Timedelta(days=6)][-1]
    fa = s[s.index <= thu + pd.Timedelta(days=1)].iloc[-1]
    prior20 = (fb/s[s.index <= fbd].iloc[-21]-1)*100
    tg.append({'year': y, 'week_pct': r((fa/fb-1)*100), 'prior_20d_pct': r(prior20)})
tgdf = pd.DataFrame(tg)
out['thanksgiving'] = {'rows': tg, 'all': stats(tgdf.week_pct), 'all_others': stats(pd.Series([w for w in (s.resample('W-FRI').last().pct_change()*100).dropna()])),
                       'prior20_neg5': stats(tgdf[tgdf.prior_20d_pct <= -5].week_pct), 'prior20_neg5_years': tgdf[tgdf.prior_20d_pct <= -5].year.tolist(),
                       'latest_prior20': r((s.iloc[-1]/s.iloc[-21]-1)*100)}

# B. Bitcoin weekend follow-up
b = px['BTC-USD'].dropna()
out['btc'] = {'last_rows': {str(k.date()): r(v, 0) for k, v in b.tail(8).items()},
              'ath': r(b.max(), 0), 'ath_date': str(b.idxmax().date()),
              'nov16_monday': {'NDX': r((px['^NDX'].loc['2026-11-16']/px['^NDX'].loc['2026-11-13']-1)*100), 'N225': r((px['^N225'].loc['2026-11-16']/px['^N225'].loc['2026-11-13']-1)*100)}}
rets = px[['BTC-USD', '^NDX', 'SMH', 'IBIT']].pct_change(fill_method=None)
al = rets.dropna(subset=['^NDX'])
out['btc']['corr_btc_ndx_60d'] = r(al['BTC-USD'].tail(60).corr(al['^NDX'].tail(60)))
out['btc']['corr_btc_ndx_250d'] = r(al['BTC-USD'].tail(250).corr(al['^NDX'].tail(250)))
out['btc']['corr_ibit_smh_60d'] = r(al['IBIT'].tail(60).corr(al['SMH'].tail(60)))
iv = D[D.ticker == 'IBIT'].set_index('date')['volume']
out['btc']['ibit_vol_last5'] = {str(k.date()): int(v) for k, v in iv.tail(5).items()}
out['btc']['ibit_vol_rank_last5'] = [int((iv >= v).sum()) for v in iv.tail(5)]
out['btc']['ibit_days'] = int(len(iv))
# weekend from Friday UTC (data close) to report Sat low
for lvl in [55300, 55632, 60000]:
    out['btc'][f'vs_{lvl}'] = {'from_1119': r((lvl/b.loc['2026-11-19']-1)*100), 'from_ath': r((lvl/b.max()-1)*100)}
# history: weekends BTC <= -5% (Fri->Sun close) since 2021 -> Monday NDX / N225 (repeat earlier test incl. 11/16)
wkds = []
for fri in b.index[(b.index.weekday == 4) & (b.index >= '2021-01-01')]:
    sun = fri + pd.Timedelta(days=2); mon = fri + pd.Timedelta(days=3)
    if sun in b.index and mon in px.index:
        wr_ = (b[sun]/b[fri]-1)*100
        nd = px['^NDX']; nkk = px['^N225']
        ndm = (nd.get(mon)/nd.get(fri)-1)*100 if pd.notna(nd.get(mon)) and pd.notna(nd.get(fri)) else np.nan
        nkm = (nkk.get(mon)/nkk.get(fri)-1)*100 if pd.notna(nkk.get(mon)) and pd.notna(nkk.get(fri)) else np.nan
        wkds.append((fri, wr_, ndm, nkm))
w = pd.DataFrame(wkds, columns=['fri', 'wk', 'ndx', 'nk'])
sel = w[w.wk <= -5]
out['btc']['weekend_le5_since2021'] = {'n': int(len(sel)), 'ndx': stats(sel.ndx), 'n225': stats(sel.nk), 'dates': [str(d.date()) for d in sel.fri]}

# C. Breadth of S&P500 members
c = P.pivot_table(index='date', columns='ticker', values='adj_close')
c = c[[k for k in c.columns if not k.startswith('^')]]
ma50 = c.rolling(50).mean(); ma200 = c.rolling(200).mean()
a50 = (c > ma50).sum(1)/c.notna().sum(1)*100; a200 = (c > ma200).sum(1)/((ma200.notna()) & c.notna()).sum(1)*100
hi = c.rolling(252, min_periods=200).max(); dd = (c/hi-1)*100
b50 = a50[ma50.notna().sum(1) > 400]; b200 = a200[ma200.notna().sum(1) > 400]
wk_ret = (c.iloc[-1]/c.iloc[-6]-1)*100
out['breadth'] = {'date': str(c.index[-1].date()), 'pct_above_50d': r(b50.iloc[-1], 1), 'pct_above_200d': r(b200.iloc[-1], 1),
                  'pct_above_50d_1w_ago': r(b50.iloc[-6], 1), 'pct_above_50d_1m_ago': r(b50.iloc[-22], 1),
                  'median_dd_52w': r(dd.iloc[-1].median(), 1), 'members': int(c.iloc[-1].notna().sum()),
                  'min_50d': r(b50.min(), 1), 'min_50d_date': str(b50.idxmin().date()), 'start': str(b50.index[0].date()),
                  'min_200d': r(b200.min(), 1), 'min_200d_date': str(b200.idxmin().date()),
                  'week_pct_up': r((wk_ret > 0).mean()*100, 1), 'week_median': r(wk_ret.median()), 'week_pct_le_-10': r((wk_ret <= -10).mean()*100, 1)}
# episodes where %>50d first fell below 20 (after being >=40), forward SPX 20d
spx = c.index.map(lambda d: px['^GSPC'].get(d)); spx = pd.Series(spx, index=c.index).astype(float)
ev = []; armed = True
for d, v in b50.items():
    if v >= 40: armed = True
    if armed and v < 20:
        i = spx.index.get_loc(d)
        ev.append({'date': str(d.date()), 'pct_above_50d': r(v, 1), 'spx_fwd20': r((spx.iloc[i+20]/spx.iloc[i]-1)*100) if i+20 < len(spx) else None,
                   'spx_min_fwd20': r((spx.iloc[i:i+21].min()/spx.iloc[i]-1)*100)})
        armed = False
out['breadth']['below20_events'] = ev
# sector-ish: RSP vs SPY 1w, 1m
out['breadth']['rsp_spy'] = {k: {t: r((px[t].dropna().iloc[-1]/px[t].dropna().iloc[-1-n]-1)*100) for t in ['RSP', 'SPY']} for k, n in [('1w', 5), ('1m', 21)]}

# D. Dell / server & PC makers vs memory
cl = c.copy()
names = ['DELL', 'HPE', 'HPQ', 'SMCI', 'MU', 'WDC', 'STX', 'NVDA']
rt = cl[[n for n in names if n in cl.columns]].pct_change(fill_method=None)
spr = px['SPY'].pct_change(fill_method=None).reindex(rt.index)
tab = {}
for n in ['DELL', 'HPE', 'HPQ', 'SMCI']:
    x = cl[n].dropna()
    row = {'close': r(x.iloc[-1]), 'r_1w': r((x.iloc[-1]/x.iloc[-6]-1)*100), 'r_1m': r((x.iloc[-1]/x.iloc[-22]-1)*100),
           'ytd': r((x.iloc[-1]/x[x.index < '2026-01-01'].iloc[-1]-1)*100), 'dd_52w': r((x.iloc[-1]/x.tail(252).max()-1)*100)}
    for per, sl in [('2025', slice('2025-01-01', '2025-12-31')), ('2026', slice('2026-01-01', None)), ('last60', None)]:
        q = rt.loc[sl] if sl else rt.tail(60); sp = spr.loc[q.index]
        ex = q.sub(sp, axis=0)
        row[f'corr_mu_{per}'] = r(q[n].corr(q['MU']))
        row[f'corr_excess_mu_{per}'] = r(ex[n].corr(ex['MU']))
    tab[n] = row
out['servers'] = tab
mu = cl['MU'].dropna()
out['servers']['MU'] = {'r_1m': r((mu.iloc[-1]/mu.iloc[-22]-1)*100), 'ytd': r((mu.iloc[-1]/mu[mu.index < '2026-01-01'].iloc[-1]-1)*100), 'dd_52w': r((mu.iloc[-1]/mu.tail(252).max()-1)*100)}
# 20d relative: DELL/SPY vs MU/SPY by quarter of 2026
q = (cl[['DELL', 'HPQ', 'MU']].div(px['SPY'].reindex(cl.index), axis=0)).resample('QE').last().pct_change()*100
out['servers']['quarterly_rel_vs_spy'] = {str(k.date()): {kk: r(vv) for kk, vv in v.items()} for k, v in q.dropna().tail(6).iterrows()}
# biggest 1d moves of DELL in last 2 years (earnings proxies)
dr = rt['DELL'].dropna()*100
big = dr[dr.abs() >= 8].tail(10)
out['servers']['dell_big_days'] = {str(k.date()): r(v) for k, v in big.items()}
json.dump(out, open('insights/data/analysis/2026-11-23.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
