"""分析の視点 2026-11-18: 米国 11/16-17 (エヌビディア決算前の2日間) を対象"""
import json, pandas as pd, numpy as np
ASOF = pd.Timestamp('2026-11-17')
d = pd.read_parquet('/tmp/market-data/daily.parquet'); d['date'] = pd.to_datetime(d['date'])
P = d.pivot(index='date', columns='ticker', values='close')
Pus = P.loc[:ASOF]
out = {}
def r(a, b, t, src=P):
    s = src[t].dropna(); return round((s.loc[:b].iloc[-1] / s.loc[:a].iloc[-1] - 1) * 100, 2)

# A. NVDA
nv = Pus['NVDA'].dropna()
hi252 = nv.rolling(252, min_periods=200).max()
dd = nv / hi252 - 1
ep = []
armed = True
for dt, v in dd.items():
    if armed and v <= -0.30:
        i = nv.index.get_loc(dt)
        f = lambda k: round((nv.iloc[i + k] / nv.iloc[i] - 1) * 100, 1) if i + k < len(nv) else None
        ep.append({'date': str(dt.date()), 'dd': round(v * 100, 1), 'f20': f(20), 'f60': f(60), 'f120': f(120)})
        armed = False
    if v > -0.15: armed = True
asia = {t: r('2026-11-17', '2026-11-18', t) for t in ['6857.T', '8035.T', '2330.TW', '000660.KS', '005930.KS', '^N225', '9984.T', 'NKD=F', 'NQ=F', 'ES=F', '4062.T', '285A.T']}
nvsd = nv.pct_change().iloc[-250:].std() * 100
out['nvda'] = {'close': float(nv.iloc[-1]), 'dd_from_252high': round(dd.iloc[-1] * 100, 1), 'hi252': float(hi252.iloc[-1]),
               'episodes_dd30': ep, 'asia_11_18': asia, 'sd250': round(nvsd, 2),
               'fwdPE_yahoo': json.load(open('/tmp/market-data/fundamentals.json'))['NVDA']['forwardPE'],
               'chg_2d': r('2026-11-13', '2026-11-17', 'NVDA')}

# B. breadth
px = pd.read_parquet('daily-review/data/prices.parquet'); px['date'] = pd.to_datetime(px['date'])
C = px.pivot(index='date', columns='ticker', values='close')
C = C[[c for c in C.columns if not c.startswith('^') and c not in ('QUAL',)]]
rc = C.pct_change(fill_method=None)
br = {}
for dt in ['2026-11-12', '2026-11-13', '2026-11-16', '2026-11-17']:
    x = rc.loc[dt].dropna(); br[dt] = {'n': int(len(x)), 'up_pct': round((x > 0).mean() * 100, 1), 'median': round(x.median() * 100, 2)}
since = (C.loc['2026-11-17'] / C.loc['2026-10-06'] - 1).dropna()
sec = ['SPY', 'RSP', 'QQQ', 'SMH', 'XLK', 'XLC', 'XLY', 'XLF', 'XLI', 'XLE', 'XLB', 'XLRE', 'XLU', 'XLP', 'XLV', 'IWM']
sect = {t: {'d16': r('2026-11-13', '2026-11-16', t, Pus), 'd17': r('2026-11-16', '2026-11-17', t, Pus),
            '2d': r('2026-11-13', '2026-11-17', t, Pus), 'since1006': r('2026-10-06', '2026-11-17', t, Pus)} for t in sec}
# history: S&P <=-1% on 2 consecutive days AND XLP, XLV both down on 2nd day
R = Pus[['^GSPC', 'XLP', 'XLV']].pct_change()
cond = (R['^GSPC'] <= -0.01) & (R['^GSPC'].shift(1) <= -0.01) & (R['XLP'] < 0) & (R['XLV'] < 0)
days = cond[cond].index
sel = []; last = None
for dt in days:
    if last is None or (dt - last).days > 30: sel.append(dt); last = dt
sp = Pus['^GSPC'].dropna()
fw = []
for dt in sel:
    i = sp.index.get_loc(dt)
    if i + 20 < len(sp): fw.append({'d': str(dt.date()), 'f5': (sp.iloc[i+5]/sp.iloc[i]-1)*100, 'f20': (sp.iloc[i+20]/sp.iloc[i]-1)*100})
fw = pd.DataFrame(fw)
allf20 = (sp.shift(-20) / sp - 1).dropna() * 100
out['breadth'] = {'daily': br, 'since1006': {'n': int(len(since)), 'up_pct': round((since > 0).mean() * 100, 1), 'median': round(since.median() * 100, 2)},
                  'since1013_s1006_ref': '前号は11/13時点で上昇72.1%、中央値+7.2%', 'sectors': sect,
                  'hist': {'raw_days': int(len(days)), 'n': int(len(fw)), 'f5_med': round(fw.f5.median(), 2), 'f20_med': round(fw.f20.median(), 2),
                           'f20_up': round((fw.f20 > 0).mean() * 100, 1), 'f20_mean': round(fw.f20.mean(), 2),
                           'all_f20_med': round(allf20.median(), 2), 'all_f20_up': round((allf20 > 0).mean() * 100, 1),
                           'recent': fw.tail(6).round(2).to_dict('records')}}

# C. VIX term structure
v = Pus[['^VIX', '^VIX3M', '^VVIX']].dropna(subset=['^VIX', '^VIX3M'])
ratio = v['^VIX'] / v['^VIX3M']
inv = ratio > 1
ev = []
for i in range(20, len(inv)):
    if inv.iloc[i] and not inv.iloc[i-20:i].any():
        ev.append(inv.index[i])
rows = []
for dt in ev:
    i = sp.index.get_loc(dt)
    g = lambda k: round((sp.iloc[i+k]/sp.iloc[i]-1)*100, 2) if i + k < len(sp) else None
    # days inverted in next 20
    j = inv.index.get_loc(dt)
    dur = int(inv.iloc[j:j+20].sum())
    mn = round((sp.iloc[i:i+21].min()/sp.iloc[i]-1)*100, 2) if i + 20 < len(sp) else None
    rows.append({'d': str(dt.date()), 'vix': round(v['^VIX'].loc[dt], 2), 'f5': g(5), 'f20': g(20), 'f60': g(60), 'min20': mn, 'inv_days20': dur})
E2 = pd.DataFrame(rows)
done = E2.dropna(subset=['f60'])
out['vix'] = {'ratio_last': round(ratio.iloc[-1], 3), 'vix': float(v['^VIX'].iloc[-1]), 'vix3m': float(v['^VIX3M'].iloc[-1]), 'vvix': float(v['^VVIX'].iloc[-1]),
              'ratio_hist': {k: round(float(ratio.loc[k]), 3) for k in ['2026-11-12', '2026-11-13', '2026-11-16', '2026-11-17']},
              'start': str(v.index[0].date()), 'n_events': int(len(E2)), 'n_done60': int(len(done)),
              'f20_med': round(done.f20.median(), 2), 'f20_up': round((done.f20 > 0).mean() * 100, 1),
              'f60_med': round(done.f60.median(), 2), 'f60_up': round((done.f60 > 0).mean() * 100, 1),
              'min20_med': round(done.min20.median(), 2), 'inv_days20_med': float(done.inv_days20.median()),
              'all_f60_med': round(((sp.shift(-60)/sp-1).dropna()*100).loc['2007':].median(), 2),
              'events': E2.tail(10).to_dict('records')}
# was there an inversion in 2026 already?
out['vix']['inv_days_2026'] = int(inv.loc['2026'].sum())

# D. memory
mem = ['MU', 'SNDK', '000660.KS', '005930.KS', 'NVDA', 'SMH']
out['memory'] = {t: {'since1006': r('2026-10-06', '2026-11-17', t), 'since1112': r('2026-11-12', '2026-11-17', t),
                     'dd_from_252high': round((P[t].dropna().loc[:ASOF].iloc[-1] / P[t].dropna().loc[:ASOF].iloc[-252:].max() - 1) * 100, 1)} for t in mem}
rr = Pus[['MU', 'NVDA', 'SNDK', 'SMH']].pct_change().dropna()
out['memory']['corr60_MU_NVDA'] = round(rr['MU'].iloc[-60:].corr(rr['NVDA'].iloc[-60:]), 2)
out['memory']['corr60_MU_SMH'] = round(rr['MU'].iloc[-60:].corr(rr['SMH'].iloc[-60:]), 2)
out['memory']['corr250_MU_NVDA'] = round(rr['MU'].iloc[-250:].corr(rr['NVDA'].iloc[-250:]), 2)
mf = json.load(open('/tmp/market-data/fundamentals.json'))
out['memory']['fwdPE'] = {t: mf[t].get('forwardPE') for t in ['MU', 'SNDK', 'NVDA'] if t in mf}
out['memory']['asia_11_18'] = {t: r('2026-11-17', '2026-11-18', t) for t in ['000660.KS', '005930.KS']}

# E. mega IPO
ipos = {'Visa': '2008-03-19', 'Facebook': '2012-05-18', 'Alibaba': '2014-09-19', 'Uber': '2019-05-10', 'Rivian': '2021-11-10', 'Arm': '2023-09-14'}
q = P['QQQ'].dropna(); s5 = P['^GSPC'].dropna()
ir = []
for k, dt in ipos.items():
    i = q.index.get_indexer([pd.Timestamp(dt)], method='bfill')[0]
    ir.append({'ipo': k, 'date': dt, 'qqq_pre5': round((q.iloc[i-1]/q.iloc[i-6]-1)*100, 2), 'qqq_post10': round((q.iloc[i+10]/q.iloc[i-1]-1)*100, 2),
               'qqq_post20': round((q.iloc[i+20]/q.iloc[i-1]-1)*100, 2)})
out['ipo'] = {'events': ir, 'qqq_since1110': r('2026-11-09', '2026-11-17', 'QQQ'), 'spx_since1110': r('2026-11-09', '2026-11-17', '^GSPC'),
              'nvda_since1110': r('2026-11-09', '2026-11-17', 'NVDA'), 'msft_since1110': r('2026-11-09', '2026-11-17', 'MSFT'),
              'googl_since1110': r('2026-11-09', '2026-11-17', 'GOOGL'), 'amzn_since1110': r('2026-11-09', '2026-11-17', 'AMZN'),
              'all_qqq_post20_med': round(((q.shift(-21)/q-1).dropna()*100).median(), 2)}
# snapshot
snap = {t: {'close': round(float(Pus[t].dropna().iloc[-1]), 3), 'd1': r('2026-11-16', '2026-11-17', t, Pus), 'd2': r('2026-11-13', '2026-11-17', t, Pus)}
        for t in ['^GSPC', '^NDX', '^DJI', '^RUT', '^SOX', 'NVDA', '^VIX', '^TNX', '^TYX', 'JPY=X', 'GC=F', 'CL=F', 'BTC-USD', 'HYG']}
out['snapshot'] = snap
out['spx_from_high'] = round((sp.iloc[-1] / sp.loc['2026'].max() - 1) * 100, 2)
json.dump(out, open('insights/data/analysis/2026-11-18.json', 'w'), ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, default=str)[:12000])

# C2. 20日以内の再逆転(現在の状況: 11/5-6に逆転、11/17に再逆転)
re = []
for i in range(60, len(inv)):
    if inv.iloc[i] and not inv.iloc[i-1] and inv.iloc[i-20:i-1].any() and not inv.iloc[i-60:i-20].any():
        dt = inv.index[i]; k = sp.index.get_loc(dt)
        if k + 60 < len(sp): re.append({'d': str(dt.date()), 'f20': round((sp.iloc[k+20]/sp.iloc[k]-1)*100, 2), 'f60': round((sp.iloc[k+60]/sp.iloc[k]-1)*100, 2)})
re = pd.DataFrame(re)
allf20_06 = (sp.shift(-20)/sp-1).loc['2006-07':].dropna()*100
out['vix']['reinv'] = {'n': int(len(re)), 'f20_med': round(re.f20.median(), 2), 'f20_up': round((re.f20 > 0).mean()*100, 1),
                       'f20_min': float(re.f20.min()), 'f60_med': round(re.f60.median(), 2), 'note': '重複を含む'}
out['vix']['all_f20_med_since2006'] = round(allf20_06.median(), 2); out['vix']['all_f20_up_since2006'] = round((allf20_06 > 0).mean()*100, 1)
fr = pd.read_parquet('/tmp/market-data/fred.parquet')
out['fred_cols'] = list(fr.columns)[:5]
json.dump(out, open('insights/data/analysis/2026-11-18.json', 'w'), ensure_ascii=False, indent=1, default=str)
print(out['vix']['reinv'], out['vix']['all_f20_med_since2006'], out['vix']['all_f20_up_since2006'], out['fred_cols'])
