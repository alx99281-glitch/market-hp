"""分析の視点 2026-11-20: 米国 11/19 (S&P500 6日続落 -2.0%、アンソロピック上場初日、新興国通貨安) を対象"""
import json, pandas as pd, numpy as np
ASOF = pd.Timestamp('2026-11-19')
d = pd.read_parquet('/tmp/market-data/daily.parquet'); d['date'] = pd.to_datetime(d['date'])
d = d[d.date <= ASOF]
P = d.pivot(index='date', columns='ticker', values='close')
O = d.pivot(index='date', columns='ticker', values='open')
out = {}
def rd(x, k=2): return None if x is None or pd.isna(x) else round(float(x), k)
def chg(t, a='2026-11-18', b='2026-11-19'):
    s = P[t].dropna(); return rd((s.loc[:b].iloc[-1] / s.loc[:a].iloc[-1] - 1) * 100)

# A. 6日続落 + 最終日-1.5%以下 の後 (S&P500, 2000年以降)
sp = P['^GSPC'].dropna(); r = sp.pct_change() * 100
streak = (r < 0).astype(int); st = streak.groupby((streak == 0).cumsum()).cumsum()
cond = (st >= 6) & (r <= -1.5)
ev = []
last_i = -999
for dt in cond[cond].index:
    i = sp.index.get_loc(dt)
    if i - last_i < 10: continue  # 10営業日以内の重複は除外
    last_i = i
    f = lambda k: rd((sp.iloc[i + k] / sp.iloc[i] - 1) * 100, 1) if i + k < len(sp) else None
    ev.append({'date': str(dt.date()), 'streak': int(st[dt]), 'ret': rd(r[dt]), 'vix': rd(P['^VIX'].get(dt), 1), 'f1': f(1), 'f5': f(5), 'f20': f(20), 'f60': f(60)})
evd = pd.DataFrame(ev)
fwd_all = {k: rd(((sp.shift(-k) / sp - 1) * 100).dropna().median(), 1) for k in (5, 20, 60)}
def stats(col):
    x = evd[col].dropna(); return {'n': int(len(x)), 'med': rd(x.median(), 1), 'up_pct': rd((x > 0).mean() * 100, 0), 'min': rd(x.min(), 1), 'max': rd(x.max(), 1)}
hi = sp.rolling(252).max()
vt = (P['^VIX'] / P['^VIX3M']).dropna()
out['streak'] = {'close': rd(sp.iloc[-1]), 'ret': rd(r.iloc[-1]), 'streak': int(st.iloc[-1]),
                 'streak_cum': rd((sp.iloc[-1] / sp.iloc[-1 - int(st.iloc[-1])] - 1) * 100),
                 'dd_252high': rd((sp.iloc[-1] / hi.iloc[-1] - 1) * 100),
                 'events': ev, 'f1': stats('f1'), 'f5': stats('f5'), 'f20': stats('f20'), 'f60': stats('f60'), 'all_med': fwd_all,
                 'vix': rd(P['^VIX'].iloc[-1]), 'vix3m': rd(P['^VIX3M'].iloc[-1]), 'vix_term': rd(vt.iloc[-1], 3),
                 'vix_term_pct_since2010': rd((vt[vt.index >= '2010'] < vt.iloc[-1]).mean() * 100, 1),
                 'vvix': rd(P['^VVIX'].iloc[-1], 1), 'vxn': rd(P['^VXN'].iloc[-1], 1),
                 'rsp_vs_spy': {'RSP': chg('RSP'), 'SPY': chg('SPY')},
                 'day': {t: chg(t) for t in ['^GSPC', '^NDX', '^DJI', '^RUT', 'SMH', 'XLK', 'XLC', 'XLY', 'XLV', 'XLI', 'XLF', 'XLP', 'XLU', 'XLE', 'XLB', 'XLRE', 'IGV', 'ARKK', 'KRE']}}
# 2026年の-2%以下の日数
r26 = r[r.index.year == 2026]; out['streak']['days_le_m2_2026'] = int((r26 <= -2).sum())
# 寄り付き→引け
out['streak']['o2c'] = {t: rd((P[t].loc[ASOF] / O[t].loc[ASOF] - 1) * 100) for t in ['SPY', 'QQQ', 'SMH', 'ANT', 'AMD', 'NVDA']}

# B. アンソロピック上場初日と出資者 (アマゾン、アルファベット)
ant = d[d.ticker == 'ANT'].iloc[-1]
mega = ['AMZN', 'GOOGL', 'META', 'MSFT', 'AAPL', 'NVDA', 'ORCL', 'AMD', 'CRWV', 'NBIS', 'MU', 'TSM', 'QQQ', 'XLC']
out['ant'] = {'ipo_price': 83.0, 'open': rd(ant.open), 'high': rd(ant.high), 'low': rd(ant.low), 'close': rd(ant.close), 'volume': int(ant.volume),
              'close_vs_ipo': rd((ant.close / 83 - 1) * 100), 'close_vs_open': rd((ant.close / ant.open - 1) * 100),
              'day': {t: chg(t) for t in mega}, 'o2c': {t: rd((P[t].loc[ASOF] / O[t].loc[ASOF] - 1) * 100) for t in mega}}
# 出資者2社の、他の大型ハイテク(MSFT, META, AAPL)平均との差: 過去60日の日次差の標準偏差と比べる
others = P[['MSFT', 'META', 'AAPL']].pct_change().mean(axis=1) * 100
inv = P[['AMZN', 'GOOGL']].pct_change().mean(axis=1) * 100
spread = (inv - others).dropna()
sd60 = spread.iloc[-61:-1].std()
out['ant']['investors_minus_others'] = {'today': rd(spread.iloc[-1]), 'sd60': rd(sd60), 'z': rd(spread.iloc[-1] / sd60, 1),
                                        'last5': {str(k.date()): rd(v) for k, v in spread.iloc[-5:].items()}}
# アマゾンの保有株数(報道値 1,920,511,218株、目論見書ベース、Reuters経由)× 終値
amzn_sh = 1920511218
fund = json.load(open('/tmp/market-data/fundamentals.json'))
out['ant']['amzn_stake_usd_bn_at_close'] = rd(amzn_sh * ant.close / 1e9, 1)
out['ant']['amzn_stake_usd_bn_at_open'] = rd(amzn_sh * ant.open / 1e9, 1)
out['ant']['amzn_mcap_bn_fundamentals'] = rd(fund['AMZN']['marketCap'] / 1e9, 0)
out['ant']['googl_mcap_bn_fundamentals'] = rd(fund['GOOGL']['marketCap'] / 1e9, 0) if 'GOOGL' in fund else None

# C. 株安の日に何がヘッジになったか: S&P500 -2%以下の日の各資産
hedges = {'TLT': 'TLT', 'GC=F': 'GC=F', 'JPY=X': 'JPY=X', 'BTC-USD': 'BTC-USD', 'DX-Y.NYB': 'DX-Y.NYB', 'CHF=X': 'CHF=X', 'SI=F': 'SI=F'}
R = P.pct_change() * 100
down = r[r <= -2].index
rows = {}
for t in hedges:
    x = R[t].reindex(down).dropna()
    by = {}
    for lab, a, b in [('2008-2019', 2008, 2019), ('2020-2021', 2020, 2021), ('2022-2025', 2022, 2025), ('2026', 2026, 2026)]:
        y = x[(x.index.year >= a) & (x.index.year <= b)]
        if len(y): by[lab] = {'n': int(len(y)), 'med': rd(y.median()), 'up_pct': rd((y > 0).mean() * 100, 0)}
    rows[t] = {'today': rd(R[t].iloc[-1]), 'by_period': by}
out['hedges'] = rows
# 10年金利の変化 (bp)
dy = P['^TNX'].diff() * 100
y26 = dy.reindex(r26[r26 <= -2].index)
out['hedges']['tnx_bp_on_m2_days_2026'] = {str(k.date()): rd(v, 1) for k, v in y26.items()}
out['hedges']['tnx_today_bp'] = rd(dy.iloc[-1], 1)
# 株と債券(TLT)の60日相関
j = pd.concat([R['SPY'], R['TLT']], axis=1).dropna()
c60 = j['SPY'].rolling(60).corr(j['TLT'])
out['hedges']['spy_tlt_corr60'] = {'now': rd(c60.iloc[-1]), '1m_ago': rd(c60.iloc[-22]), '3m_ago': rd(c60.iloc[-64]),
                                   'pct_since2010': rd((c60[c60.index >= '2010'] < c60.iloc[-1]).mean() * 100, 0)}
spy_gld = pd.concat([R['SPY'], R['GC=F']], axis=1).dropna()
g60 = spy_gld['SPY'].rolling(60).corr(spy_gld['GC=F'])
out['hedges']['spy_gold_corr60'] = {'now': rd(g60.iloc[-1]), '3m_ago': rd(g60.iloc[-64]), 'pct_since2010': rd((g60[g60.index >= '2010'] < g60.iloc[-1]).mean() * 100, 0)}
out['hedges']['gold_1m'] = chg('GC=F', '2026-10-19', '2026-11-19'); out['hedges']['silver_2d'] = chg('SI=F', '2026-11-17', '2026-11-19')
out['hedges']['gold_2d'] = chg('GC=F', '2026-11-17', '2026-11-19')

# D. 新興国通貨: ドル高(DXY)に対する感応度と今回の動き
fx = ['MXN=X', 'ZAR=X', 'BRL=X', 'IDR=X', 'INR=X', 'TRY=X', 'KRW=X', 'TWD=X', 'PLN=X', 'JPY=X', 'EURUSD=X']
def sig(t):
    s = R[t].dropna(); sd = s.iloc[-251:-1].std(); return rd(s.iloc[-1] / sd, 1)
out['emfx'] = {t: {'d1': rd(R[t].iloc[-1]), 'sigma': sig(t), 'd5': chg(t, '2026-11-12', '2026-11-19'), 'm1': chg(t, '2026-10-19', '2026-11-19')} for t in fx}
out['emfx']['DXY'] = {'d1': chg('DX-Y.NYB'), 'm1': chg('DX-Y.NYB', '2026-10-19', '2026-11-19'), 'level': rd(P['DX-Y.NYB'].iloc[-1], 3)}
# MXNの3%以上のペソ安の日の後、EWW(メキシコ株ETF)とS&P500の20日
mx = R['MXN=X'].dropna(); big = mx[mx >= 3].index
evm = []
for dt in big:
    i = sp.index.searchsorted(dt)
    if i + 20 < len(sp) and sp.index[i] == dt:
        evm.append({'date': str(dt.date()), 'mxn': rd(mx[dt]), 'spx_d': rd(r[dt]), 'spx_f20': rd((sp.iloc[i + 20] / sp.iloc[i] - 1) * 100, 1)})
out['emfx']['mxn_3pct_days'] = evm
out['emfx']['mxn_3pct_n'] = int(len(big))
out['emfx']['equity'] = {t: {'d1': chg(t), 'm1': chg(t, '2026-10-19', '2026-11-19')} for t in ['EWW', 'EWZ', 'EZA', 'EEM', 'ACWI', 'EWJ']}

json.dump(out, open('insights/data/analysis/2026-11-20.json', 'w'), ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, default=str)[:12000])

# E. QQQ: 寄り付き+1.5%以上・引け-2%以下(反転の日)の後
q = P['QQQ'].dropna(); qo = O['QQQ'].reindex(q.index); qp = q.shift(1)
gap = (qo / qp - 1) * 100; qr = (q / qp - 1) * 100
cq = (gap >= 1.5) & (qr <= -2)
evq = []
for dt in cq[cq].index:
    i = q.index.get_loc(dt)
    f = lambda k: rd((q.iloc[i + k] / q.iloc[i] - 1) * 100, 1) if i + k < len(q) else None
    evq.append({'date': str(dt.date()), 'gap': rd(gap[dt], 1), 'ret': rd(qr[dt], 1), 'f5': f(5), 'f20': f(20)})
eq = pd.DataFrame(evq); e20 = eq.f20.dropna(); e5 = eq.f5.dropna()
out['qqq_reversal'] = {'today': {'gap': rd(gap.iloc[-1]), 'ret': rd(qr.iloc[-1])}, 'n': int(len(eq)), 'events': evq,
                       'f5': {'n': int(len(e5)), 'med': rd(e5.median(), 1), 'up_pct': rd((e5 > 0).mean() * 100, 0)},
                       'f20': {'n': int(len(e20)), 'med': rd(e20.median(), 1), 'up_pct': rd((e20 > 0).mean() * 100, 0)},
                       'all_f20_med': rd(((q.shift(-20) / q - 1) * 100).dropna().median(), 1),
                       'hourly_all_negative': True}
out['japan'] = {'nkd_1119': rd(P['NKD=F'].loc[ASOF], 0), 'n225_1118': rd(P['^N225'].loc['2026-11-18'], 0),
                'nkd_vs_n225': rd((P['NKD=F'].loc[ASOF] / P['^N225'].loc['2026-11-18'] - 1) * 100), 'ewj_d1': chg('EWJ'), 'usdjpy': rd(P['JPY=X'].iloc[-1], 3)}
out['emfx']['two_day'] = {t: chg(t, '2026-11-17', '2026-11-19') for t in ['MXN=X', 'ZAR=X', 'BRL=X', 'PLN=X', 'JPY=X', 'KRW=X']}
json.dump(out, open('insights/data/analysis/2026-11-20.json', 'w'), ensure_ascii=False, indent=1, default=str)
print(json.dumps({k: out[k] for k in ['qqq_reversal', 'japan']}, ensure_ascii=False)); print(out['emfx']['two_day'])
