"""分析の視点 2026-11-28 (対象: 2026-11-27 米国短縮取引)"""
import json, numpy as np, pandas as pd
D = pd.read_parquet('/tmp/market-data/daily.parquet')
P = D.pivot(index='date', columns='ticker', values='close').sort_index()
ASOF = pd.Timestamp('2026-11-27')
P = P[P.index <= ASOF]
out = {}
def r(x, n=2): return None if pd.isna(x) else round(float(x), n)
def ret(t, a, b):
    s = P[t].dropna(); return (s.loc[:b].iloc[-1] / s.loc[:a].iloc[-1] - 1) * 100

# ---- A: 感謝祭明け金曜(短縮取引)のS&P500
spx = P['^GSPC'].dropna()
tg = []
for y in range(2000, 2027):
    nov = pd.Timestamp(y, 11, 1); th = nov + pd.offsets.Week(weekday=3) + pd.Timedelta(days=21)
    if nov.weekday() == 3: th = nov + pd.Timedelta(days=21)
    fri = th + pd.Timedelta(days=1)
    if fri not in spx.index: continue
    i = spx.index.get_loc(fri)
    prev = spx.iloc[i-1]; d = (spx.iloc[i]/prev-1)*100
    wk = (spx.iloc[i]/spx.iloc[i-4]-1)*100 if i >= 4 else np.nan
    f20 = (spx.iloc[i+20]/spx.iloc[i]-1)*100 if i+20 < len(spx) else np.nan
    f5 = (spx.iloc[i+5]/spx.iloc[i]-1)*100 if i+5 < len(spx) else np.nan
    # 金曜時点の11月月初来
    m0 = spx[spx.index < pd.Timestamp(y, 11, 1)].iloc[-1]
    mtd = (spx.iloc[i]/m0-1)*100
    tg.append(dict(year=y, fri=str(fri.date()), day=r(d), week4=r(wk), mtd=r(mtd), f5=r(f5), f20=r(f20)))
tgdf = pd.DataFrame(tg)
out['A_black_friday'] = dict(rows=tg,
    rank_2026=int((tgdf.day >= tgdf[tgdf.year == 2026].day.iloc[0]).sum()),
    n=len(tgdf), up_count_hist=int((tgdf[tgdf.year < 2026].day > 0).sum()))
# 11月が月初来マイナスで迎えた年のその後20日
neg = tgdf[(tgdf.year < 2026) & (tgdf.mtd < 0)]
out['A_black_friday']['mtd_negative_years'] = neg[['year', 'mtd', 'day', 'f20']].to_dict('records')
# 週(11/20→11/27)の騰落
wk = {t: r(ret(t, '2026-11-20', '2026-11-27')) for t in ['^GSPC', '^NDX', '^SOX', '^RUT', 'RSP', 'SPY', 'NVDA', 'MU', 'AMD', 'ANT', 'CRWV', 'META', 'AMZN', 'MSFT', 'GOOGL', 'ORCL', 'DELL', 'XLP', 'XLK']}
day = {t: r(ret(t, '2026-11-25', '2026-11-27')) for t in ['^GSPC', '^NDX', '^DJI', '^SOX', '^RUT', 'RSP', 'SPY', 'NVDA', 'MU', 'AMD', 'ANT', 'CRWV', 'META', 'AMZN', 'MSFT', 'GOOGL', 'ORCL', 'DELL', 'AAPL', 'XLP', 'XLK', 'TSM', 'ASML', 'WDC', 'STX', 'SNDK', 'NBIS']}
mtd = {t: r(ret(t, '2026-10-30', '2026-11-27')) for t in ['^GSPC', '^NDX', '^SOX', '^RUT', 'RSP', 'TLT', 'GC=F', 'EWZ', 'INDA', 'EWT', 'EWY', 'UAE']}
out['A_week'] = wk; out['A_day'] = day; out['A_mtd'] = mtd
# 安値からの戻り: 11月の高値・安値
for t in ['^GSPC', '^NDX', '^SOX', '^RUT']:
    s = P[t].dropna(); m = s['2026-10-01':]
    hi = m.max(); lo = m.loc[m.idxmax():].min()
    out.setdefault('A_retrace', {})[t] = dict(high=r(hi), high_date=str(m.idxmax().date()), low=r(lo),
        low_date=str(m.loc[m.idxmax():].idxmin().date()), last=r(s.iloc[-1]),
        dd=r((lo/hi-1)*100), recovered_pct=r((s.iloc[-1]-lo)/(hi-lo)*100, 1))
rut = P['^RUT'].dropna(); out['A_rut_high'] = dict(last=r(rut.iloc[-1]), max_prior=r(rut.iloc[:-1].max()), max_prior_date=str(rut.iloc[:-1].idxmax().date()))

# ---- B: VIX期間構造の逆転解消
v = P[['^VIX', '^VIX3M']].dropna(); ratio = v['^VIX']/v['^VIX3M']
inv = ratio > 1
runs = []; cnt = 0
for i, (dt, x) in enumerate(inv.items()):
    if x: cnt += 1
    else:
        if cnt >= 5:
            st = spx.loc[:dt]
            j = spx.index.get_loc(dt) if dt in spx.index else None
            f = {}
            if j is not None:
                for h in (5, 20, 60):
                    f[h] = r((spx.iloc[j+h]/spx.iloc[j]-1)*100) if j+h < len(spx) else None
            runs.append(dict(end=str(dt.date()), length=cnt, ratio_end=r(ratio.loc[dt], 3), f5=f.get(5), f20=f.get(20), f60=f.get(60),
                vix_end=r(v['^VIX'].loc[dt])))
        cnt = 0
rd = pd.DataFrame(runs)
hist = rd[rd.end < '2026-11-27']
out['B_vix'] = dict(ratio_last=r(ratio.iloc[-1], 4), ratio_prev=r(ratio.iloc[-2], 4), inverted_last=bool(inv.iloc[-1]),
    run_before=int(cnt), vix=r(v['^VIX'].iloc[-1]), vix3m=r(v['^VIX3M'].iloc[-1]),
    vix9d=r(P['^VIX9D'].dropna().iloc[-1]), vix9d_prev=r(P['^VIX9D'].dropna().iloc[-2]), vvix=r(P['^VVIX'].dropna().iloc[-1]),
    vix_chg=r((v['^VIX'].iloc[-1]/v['^VIX'].iloc[-2]-1)*100),
    runs_ge5=runs[-12:], n_hist=len(hist),
    f20_up=int((hist.f20 > 0).sum()), f20_n=int(hist.f20.notna().sum()), f20_med=r(hist.f20.median()),
    f60_up=int((hist.f60 > 0).sum()), f60_n=int(hist.f60.notna().sum()), f60_med=r(hist.f60.median()),
    f5_up=int((hist.f5 > 0).sum()), f5_med=r(hist.f5.median()))
# 現在の連続逆転日数(最終日を除く)
c = 0
for x in inv.iloc[-2::-1]:
    if x: c += 1
    else: break
out['B_vix']['inversion_days_until_prev'] = c

# ---- C: 金+3%超かつ米10年+5bp以上かつドル高
g = P['GC=F'].dropna(); tnx = P['^TNX'].dropna(); dx = P['DX-Y.NYB'].dropna(); si = P['SI=F'].dropna()
df = pd.concat([g.pct_change()*100, tnx.diff()*100, dx.pct_change()*100, si.pct_change()*100, spx.pct_change()*100], axis=1, keys=['gold', 'tnx_bp', 'dxy', 'silver', 'spx']).dropna()
last = df.iloc[-1]
big = df[df.gold >= 3]
both = big[(big.tnx_bp >= 5)]
both_dx = both[both.dxy > 0]
gs = g.pct_change().dropna()*100; sd = gs.iloc[-251:-1].std()
gfwd = []
for dt in both.index:
    j = g.index.get_loc(dt)
    gfwd.append(dict(date=str(dt.date()), gold=r(df.loc[dt, 'gold']), tnx_bp=r(df.loc[dt, 'tnx_bp'], 1), dxy=r(df.loc[dt, 'dxy']),
        gold_f20=r((g.iloc[j+20]/g.iloc[j]-1)*100) if j+20 < len(g) else None))
g52 = g.iloc[-253:-1]
out['C_gold'] = dict(gold=r(g.iloc[-1], 1), gold_chg=r(last.gold), gold_sigma=r(last.gold/sd, 1), silver_chg=r(last.silver), tnx=r(tnx.iloc[-1], 3), tnx_bp=r(last.tnx_bp, 1),
    dxy_chg=r(last.dxy), spx_chg=r(last.spx), n_gold3=len(big), n_gold3_tnx5=len(both), n_with_dxy_up=len(both_dx), events=gfwd,
    gold_low_52w=r(g52.min(), 1), gold_low_52w_date=str(g52.idxmin().date()), gold_high_52w=r(g52.max(), 1), gold_high_52w_date=str(g52.idxmax().date()),
    gold_from_high=r((g.iloc[-1]/g52.max()-1)*100), gvz=r(P['^GVZ'].dropna().iloc[-1]), gvz_date=str(P['^GVZ'].dropna().index[-1].date()),
    gold_mtd=mtd['GC=F'], gold_gold3_count_since2000=int((df.gold >= 3).sum()))
# 金とS&P500の60日相関
gc = pd.concat([g.pct_change(), spx.pct_change(), tnx.diff()], axis=1, keys=['g', 's', 't']).dropna()
out['C_gold']['corr60_gold_spx'] = r(gc.g.iloc[-60:].corr(gc.s.iloc[-60:]))
out['C_gold']['corr60_gold_tnx'] = r(gc.g.iloc[-60:].corr(gc.t.iloc[-60:]))
out['C_gold']['corr_all_gold_spx'] = r(gc.g.corr(gc.s))

# ---- D: ブラジル
ewz = P['EWZ'].dropna(); brl = P['BRL=X'].dropna(); bv = P['^BVSP'].dropna()
e1 = ewz.pct_change()*100
# 2営業日(休場をはさむ)換算: 感謝祭で米上場EWZは11/25→11/27
sd_e = e1.iloc[-251:-1].std()
evs = []
for dt in e1[e1 >= 9].index:
    j = ewz.index.get_loc(dt)
    evs.append(dict(date=str(dt.date()), ewz=r(e1.loc[dt]), f5=r((ewz.iloc[j+5]/ewz.iloc[j]-1)*100) if j+5 < len(ewz) else None,
        f20=r((ewz.iloc[j+20]/ewz.iloc[j]-1)*100) if j+20 < len(ewz) else None,
        f60=r((ewz.iloc[j+60]/ewz.iloc[j]-1)*100) if j+60 < len(ewz) else None))
ev = pd.DataFrame(evs); evh = ev[ev.date < '2026-11-27']
b1 = brl.pct_change()*100
bpos = b1[b1 <= -4]
out['D_brazil'] = dict(ewz_chg=r(e1.iloc[-1]), ewz_sigma=r(e1.iloc[-1]/sd_e, 1), ewz_last=r(ewz.iloc[-1]),
    brl=r(brl.iloc[-1], 4), brl_chg=r(b1.iloc[-1]), brl_prev_date=str(brl.index[-2].date()),
    bvsp_tail=[[str(i.date()), r(x)] for i, x in bv.tail(5).items()],
    ewz_mtd=mtd['EWZ'], ewz_vs_acwi_mtd=r(mtd['EWZ'] - ret('ACWI', '2026-10-30', '2026-11-27')),
    events_ge9=evs, n_hist=len(evh), f20_up=int((evh.f20 > 0).sum()), f20_n=int(evh.f20.notna().sum()), f20_med=r(evh.f20.median()),
    f60_up=int((evh.f60 > 0).sum()), f60_n=int(evh.f60.notna().sum()), f60_med=r(evh.f60.median()),
    brl_drop4_dates=[str(x.date()) for x in bpos.index])
# 円/レアル
jpy = P['JPY=X'].dropna()
brljpy = (jpy/brl).dropna()
out['D_brazil']['brljpy'] = r(brljpy.iloc[-1], 2); out['D_brazil']['brljpy_chg'] = r((brljpy.iloc[-1]/brljpy.iloc[-2]-1)*100)
out['D_brazil']['brljpy_max_since'] = str(brljpy[brljpy >= brljpy.iloc[-1]].index[-2].date()) if (brljpy >= brljpy.iloc[-1]).sum() > 1 else 'データ内最高'
out['D_brazil']['brljpy_1y_pct'] = r((brljpy.iloc[:-1].iloc[-252:] < brljpy.iloc[-1]).mean()*100, 1)

# ---- E: インド・UAEと韓国・台湾の1か月の差
def rel(a, b, n=21):
    x = (P[a].dropna().pct_change(n)*100 - P[b].dropna().pct_change(n)*100).dropna(); return x
sp = rel('INDA', 'EWT')
sp2 = (P['INDA'].pct_change(21) - (P['EWT'].pct_change(21)+P['EWY'].pct_change(21))/2).dropna()*100
spq = sp2.dropna()
fw = []
# 過去に差が+25pt超になった局面の、その後の差の変化(20日)
ewt = P['EWT'].dropna(); inda = P['INDA'].dropna()
tbl = []
prev_end = None
for dt, x in spq.items():
    if x >= 25 and (prev_end is None or (dt - prev_end).days > 60):
        j = spq.index.get_loc(dt)
        f = None
        if j+20 < len(spq):
            d2 = spq.index[j+20]
            ia = (P['INDA'].loc[d2]/P['INDA'].loc[dt]-1)*100
            ta = ((P['EWT'].loc[d2]/P['EWT'].loc[dt]-1)*100 + (P['EWY'].loc[d2]/P['EWY'].loc[dt]-1)*100)/2
            f = r(ia - ta)
        tbl.append(dict(date=str(dt.date()), spread=r(x, 1), next20_rel=f)); prev_end = dt
out['E_rotation'] = dict(spread_last=r(spq.iloc[-1], 1), pct_rank=r((spq < spq.iloc[-1]).mean()*100, 1), start=str(spq.index[0].date()),
    inda_21=r(P['INDA'].pct_change(21).iloc[-1]*100), ewt_21=r(P['EWT'].pct_change(21).iloc[-1]*100), ewy_21=r(P['EWY'].pct_change(21).iloc[-1]*100),
    ewj_21=r(P['EWJ'].pct_change(21).iloc[-1]*100), uae_21=r(P['UAE'].pct_change(21).iloc[-1]*100), acwi_21=r(P['ACWI'].pct_change(21).iloc[-1]*100),
    episodes=tbl, max=r(spq.max(), 1), max_date=str(spq.idxmax().date()),
    day_chg={t: r((P[t].dropna().iloc[-1]/P[t].dropna().iloc[-2]-1)*100) for t in ['INDA', 'EWT', 'EWY', 'EWJ', 'UAE']})
eh = pd.DataFrame(tbl); eh = eh[eh.date < '2026-11-01']
out['E_rotation']['hist_n'] = len(eh); out['E_rotation']['hist_reverse'] = int((eh.next20_rel < 0).sum()) if len(eh) else 0

json.dump(out, open('/home/user/market-hp/insights/data/analysis/2026-11-28.json', 'w'), ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, default=str)[:12000])

# ---- 追加: 週間騰落の順位、金とS&P500の相関の分位
w = spx.pct_change(5)*100
wk_last = (spx.iloc[-1]/spx.loc[:'2026-11-20'].iloc[-1]-1)*100
prior = w[(w >= wk_last) & (w.index < '2026-11-21')]
out['A_week_rank'] = dict(week=r(wk_last), last_bigger_5d=str(prior.index[-1].date()) if len(prior) else None)
c60 = gc.g.rolling(60).corr(gc.s).dropna()
out['C_gold']['corr60_pct_since2000'] = r((c60 < c60.iloc[-1]).mean()*100, 1)
out['C_gold']['corr60_higher_last'] = str(c60[(c60 >= c60.iloc[-1]) & (c60.index < c60.index[-1] - pd.Timedelta(days=90))].index[-1].date()) if ((c60 >= c60.iloc[-1]) & (c60.index < c60.index[-1] - pd.Timedelta(days=90))).any() else None
# RSPとSPYの11月の差
out['A_rsp_spy_mtd'] = r(ret('RSP', '2026-10-30', '2026-11-27') - ret('SPY', '2026-10-30', '2026-11-27'))
m = {}
rsp = P['RSP'].dropna(); spy = P['SPY'].dropna()
mm = (rsp.resample('ME').last().pct_change() - spy.resample('ME').last().pct_change()).dropna()*100
out['A_rsp_spy_monthly_rank'] = dict(n=len(mm), bigger=int((mm.iloc[:-1] >= out['A_rsp_spy_mtd']).sum()), top=[[str(i.date()), r(x)] for i, x in mm.iloc[:-1].nlargest(5).items()])
json.dump(out, open('/home/user/market-hp/insights/data/analysis/2026-11-28.json', 'w'), ensure_ascii=False, indent=1, default=str)
print(out['A_week_rank'], out['C_gold']['corr60_pct_since2000'], out['C_gold']['corr60_higher_last'], out['A_rsp_spy_mtd'], out['A_rsp_spy_monthly_rank'])
