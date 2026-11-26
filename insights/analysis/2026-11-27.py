"""2026-11-27 (SGT) 感謝祭休場明けの号の分析。データ: market-data ブランチ (11/26 18:50 UTC 取得)"""
import json, numpy as np, pandas as pd
d = pd.read_parquet('/tmp/market-data/daily.parquet')
p = d.pivot(index='date', columns='ticker', values='close')
out = {}

# 1. 関税案(11/25 USTR)と国別ETF。11/23終値→11/25終値(WSJ報道11/24、正式案11/25)
rates = {'EWS': 'シンガポール 10%(合意なければ20%)', 'EWG': 'EU 15%(ドイツ)', 'EWQ': 'EU 15%(フランス)',
         'EWI': 'EU 15%(イタリア)', 'EWN': 'EU 15%(オランダ)', 'EWJ': '日本 15%(最大20%)', 'EWY': '韓国 15%(最大25%)',
         'EWL': 'スイス 15%', 'EWT': '台湾 15%(最大25%)', 'INDA': 'インド 17%(合意なければ25%)', 'EIDO': 'インドネシア 18%',
         'EWM': 'マレーシア 18%', 'THD': 'タイ 18%', 'MCHI': '中国 20%(既存に上乗せ)', 'VNM': 'ベトナム 35%(合意なら20%)',
         'EWW': 'メキシコ 判断保留', 'NORW': 'ノルウェー 判断保留', 'EWZ': 'ブラジル 対象外', 'EWU': '英国 対象外',
         'EWC': 'カナダ 対象外', 'EWA': '豪州 対象外'}
r2 = (p.loc['2026-11-25'] / p.loc['2026-11-23'] - 1) * 100
r1 = (p.loc['2026-11-25'] / p.loc['2026-11-24'] - 1) * 100
acwi2 = r2['ACWI']
rows = []
for t, lab in rates.items():
    rows.append({'ticker': t, 'label': lab, 'r2d': round(r2[t], 2), 'r2d_vs_acwi': round(r2[t] - acwi2, 2), 'r1d': round(r1[t], 2)})
out['tariff_etf'] = {'acwi_2d': round(acwi2, 2), 'spy_2d': round(r2['SPY'], 2), 'rows': rows}
tgt = [r['r2d_vs_acwi'] for r in rows if '対象外' not in r['label'] and '保留' not in r['label']]
non = [r['r2d_vs_acwi'] for r in rows if '対象外' in r['label'] or '保留' in r['label']]
out['tariff_group'] = {'target_median': round(float(np.median(tgt)), 2), 'non_median': round(float(np.median(non)), 2), 'n_t': len(tgt), 'n_n': len(non)}
thu = (p.loc['2026-11-26'] / p.loc['2026-11-25'] - 1) * 100
out['thu'] = {t: round(thu[t], 2) for t in ['^GDAXI', '^STOXX50E', '^FTSE', '^AXJO', '^TA125.TA', '^BVSP', '^MXX', 'XU100.IS',
                                            'ES=F', 'NQ=F', 'NKD=F', 'MXN=X', 'BRL=X', 'CNY=X', 'JPY=X', 'EURUSD=X', 'KRW=X', 'TWD=X',
                                            'GC=F', 'SI=F', 'HG=F', 'PL=F', 'PA=F', 'NG=F', 'CL=F', 'BTC-USD'] if not np.isnan(thu[t])}

# 2. 感謝祭の木曜のDAXと金曜のS&P500 (2000-2025)
g = p['^GSPC'].dropna(); dax = p['^GDAXI'].dropna()
rows = []
for y in range(2000, 2026):
    nov = pd.date_range(f'{y}-11-01', f'{y}-11-30')
    thx = [x for x in nov if x.weekday() == 3][3]
    fri = thx + pd.Timedelta(days=1); wed = thx - pd.Timedelta(days=1)
    if thx not in dax.index or fri not in g.index or wed not in g.index: continue
    dprev = dax[dax.index < thx].iloc[-1]
    rd = (dax[thx] / dprev - 1) * 100
    rf = (g[fri] / g[wed] - 1) * 100
    nxt = g[g.index > fri]
    r5 = (nxt.iloc[4] / g[fri] - 1) * 100
    rows.append({'year': y, 'dax_thu': round(rd, 2), 'spx_fri': round(rf, 2), 'spx_next5': round(r5, 2)})
df = pd.DataFrame(rows)
same = int((np.sign(df.dax_thu) == np.sign(df.spx_fri)).sum())
big = df[df.dax_thu >= 1.0]
out['thanksgiving'] = {'n': len(df), 'corr': round(df.dax_thu.corr(df.spx_fri), 2), 'same_sign': same,
                      'dax_up1': big.to_dict('records'), 'rows': df.to_dict('records'),
                      'beta': round(float(np.polyfit(df.dax_thu, df.spx_fri, 1)[0]), 3)}

# 3. 月末: 11月の株と債券の差、その後
spx = p['^GSPC'].dropna(); tlt = p['TLT'].dropna()
oct_end = spx[spx.index <= '2026-10-31'].index[-1]
out['nov'] = {'oct_end': str(oct_end.date()), 'spx_mtd': round((spx['2026-11-25'] / spx[oct_end] - 1) * 100, 2),
              'tlt_mtd': round((tlt['2026-11-25'] / tlt[oct_end] - 1) * 100, 2),
              'ief_mtd': round((p['IEF']['2026-11-25'] / p['IEF'][oct_end] - 1) * 100, 2),
              'rsp_mtd': round((p['RSP']['2026-11-25'] / p['RSP'][oct_end] - 1) * 100, 2),
              'ndx_mtd': round((p['^NDX']['2026-11-25'] / p['^NDX'][oct_end] - 1) * 100, 2)}
both = pd.concat([spx, tlt], axis=1, keys=['s', 't']).dropna()
res = []
months = sorted(set((x.year, x.month) for x in both.index))
for (y, m) in months[1:-1]:
    idx = both.index[(both.index.year == y) & (both.index.month == m)]
    prev = both.index[both.index < idx[0]][-1]
    if len(idx) < 5: continue
    cut = idx[-3]  # 月末3営業日前(今回の11/25は月末11/30の2営業日前+短縮日)
    diff = (both.s[cut] / both.s[prev] - 1) * 100 - (both.t[cut] / both.t[prev] - 1) * 100
    last = idx[-1]
    after = both.index[both.index > last]
    if len(after) < 5: continue
    r_end = (both.s[last] / both.s[cut] - 1) * 100
    r_last = (both.s[last] / both.s[idx[-2]] - 1) * 100
    r_next5 = (both.s[after[4]] / both.s[last] - 1) * 100
    res.append({'month': f'{y}-{m:02d}', 'diff': round(diff, 2), 'r_cut_to_end': round(r_end, 2), 'r_lastday': round(r_last, 2), 'r_next5': round(r_next5, 2)})
rd = pd.DataFrame(res)
cur = out['nov']['spx_mtd'] - out['nov']['tlt_mtd']
low = rd[rd['diff'] <= -6].sort_values('diff')
def st(x): return {'n': len(x), 'up_end': int((x.r_cut_to_end > 0).sum()), 'med_end': round(x.r_cut_to_end.median(), 2),
                   'up_last': int((x.r_lastday > 0).sum()), 'med_last': round(x.r_lastday.median(), 2),
                   'up_next5': int((x.r_next5 > 0).sum()), 'med_next5': round(x.r_next5.median(), 2)}
out['rebal'] = {'current_diff': round(cur, 2), 'all': st(rd), 'low6': st(low), 'low6_rows': low.to_dict('records'),
                'high6': st(rd[rd['diff'] >= 6])}

# 4. メキシコペソとブラジルレアル
for t in ['MXN=X', 'BRL=X']:
    s = p[t].dropna(); r = s.pct_change() * 100
    sd = r.iloc[-251:-1].std()
    r3 = (s.iloc[-1] / s.loc['2026-11-23'] - 1) * 100
    r3h = (s / s.shift(3) - 1) * 100
    sd3 = r3h.iloc[-750:-1].std()
    cnt = int((r3h.loc['2023-11-26':].abs() >= abs(r3)).sum())
    out[t] = {'last': round(s.iloc[-1], 4), 'r1': round(r.iloc[-1], 2), 'sig1': round(r.iloc[-1] / sd, 1), 'r3': round(r3, 2),
              'sig3': round(r3 / sd3, 1), 'n_ge_3y': cnt, 'last_date': str(s.index[-1].date()),
              'r1m': round((s.iloc[-1] / s[s.index <= '2026-10-26'].iloc[-1] - 1) * 100, 2)}
out['ewz_ew_w'] = {'EWW_2d': round(r2['EWW'], 2), 'EWZ_2d': round(r2['EWZ'], 2), 'MXX_thu': out['thu'].get('^MXX'), 'BVSP_thu': out['thu'].get('^BVSP')}
json.dump(out, open('/home/user/market-hp/insights/data/analysis/2026-11-27.json', 'w'), ensure_ascii=False, indent=1, default=float)
print(json.dumps(out, ensure_ascii=False, indent=1, default=float))
