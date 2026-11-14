"""Insights edition 2026-11-14 (US 2026-11-13). Data: market-data branch."""
import json, numpy as np, pandas as pd
D='/tmp/market-data/'
d=pd.read_parquet(D+'daily.parquet'); p=d.pivot(index='date',columns='ticker',values='close').sort_index()
f=pd.read_parquet(D+'fred.parquet'); fp=f.pivot(index='date',columns='series',values='value').sort_index()
ASOF=pd.Timestamp('2026-11-13'); out={}
def fl(x,n=2): return None if pd.isna(x) else round(float(x),n)

# 1. 10y nominal vs breakeven -> real
tnx=p['^TNX'].dropna(); be=fp['T10YIE'].dropna()
j=pd.concat([tnx.rename('nom'),be.rename('be')],axis=1).dropna(); j=j[j.index<=ASOF]; j['real']=j.nom-j.be
res={}
for n in (1,5,10,21):
    c=(j.iloc[-1]-j.iloc[-1-n])*100; res[f'{n}d']={k:fl(c[k],1) for k in c.index}
res['last']={k:fl(j.iloc[-1][k],3) for k in j.columns}; res['last_date']=str(j.index[-1].date())
# historical: 10d nominal rise >=25bp; real-driven (BE change <=+3bp) vs BE-driven
ch=(j-j.shift(10))*100
spx=p['^GSPC'].dropna(); ndx=p['^NDX'].dropna(); rut=p['^RUT'].dropna(); gold=p['GC=F'].dropna()
def fwd(s,dates,h):
    s=s[s.index<=ASOF]; r=[]
    for t in dates:
        i=s.index.searchsorted(t)
        if i+h<len(s) and s.index[i]==t: r.append(s.iloc[i+h]/s.iloc[i]-1)
    return np.array(r)*100
ev=ch[(ch.nom>=25)].index
# de-overlap 20 trading days
sel=[];last=None
for t in ev:
    if last is None or (t-last).days>30: sel.append(t); last=t
sel=pd.DatetimeIndex(sel)
hist={}
for lab,mask in [('real主導(BE変化<=+3bp)',ch.loc[sel,'be']<=3),('BE主導(BE変化>+3bp)',ch.loc[sel,'be']>3)]:
    ds=sel[mask.values]; ds=ds[ds<ASOF-pd.Timedelta(days=10)]
    row={'n':len(ds)}
    for nm,s in [('SPX',spx),('NDX',ndx),('RUT',rut),('GOLD',gold)]:
        r=fwd(s,ds,20); row[nm+'_20d_med']=fl(np.median(r)) if len(r) else None; row[nm+'_20d_pos']=fl((r>0).mean()*100,0) if len(r) else None
    hist[lab]=row
res['hist_10d_rise25']=hist; res['events_since']=str(j.index[0].date())
out['rates_decomp']=res

# 2. stock-bond correlation: SPX daily return vs 10y yield change
r_spx=spx.pct_change()*100; dy=tnx.diff()*100
sb=pd.concat([r_spx,dy],axis=1,keys=['spx','dy']).dropna(); sb=sb[sb.index<=ASOF]
c60=sb.spx.rolling(60).corr(sb.dy); c250=sb.spx.rolling(250).corr(sb.dy)
pct=(c60<=c60.iloc[-1]).mean()*100
recent=sb.iloc[-60:]
both=((recent.spx<0)&(recent.dy>0)).mean()*100
# bad days for stocks: did bonds hedge? on SPX worst 10% days in last 250, avg yield change
last250=sb.iloc[-250:]; th=last250.spx.quantile(0.1); bad=last250[last250.spx<=th]
by_year={str(y):fl(g.spx.corr(g.dy)) for y,g in sb[sb.index>='2000'].groupby(sb[sb.index>='2000'].index.year)}
# 2026 bad-day yield
out['stock_bond']={'corr60':fl(c60.iloc[-1]),'corr250':fl(c250.iloc[-1]),'corr60_pct_since2000':fl(pct,0),
 'share_spx_down_yield_up_60d':fl(both,0),'bad_days_250_n':len(bad),'bad_days_avg_dy_bp':fl(bad.dy.mean(),1),'bad_days_share_yield_up':fl((bad.dy>0).mean()*100,0),
 'corr_by_year':{k:v for k,v in by_year.items() if int(k)>=2018},'c60_max_2026':fl(c60[c60.index>='2026'].max()),'c60_min_2026':fl(c60[c60.index>='2026'].min()),
 'last5':[[str(i.date()),fl(a),fl(b,1)] for i,(a,b) in sb.iloc[-5:].iterrows()]}
# share since 2000 where corr60<0 (positive yield up= stocks down)
out['stock_bond']['share_corr60_below0_since2000']=fl((c60[c60.index>='2000']<0).mean()*100,0)

# 3. VXN - VIX spread
vx=pd.concat([p['^VXN'],p['^VIX']],axis=1,keys=['vxn','vix']).dropna(); vx=vx[vx.index<=ASOF]; vx['sp']=vx.vxn-vx.vix; vx['ratio']=vx.vxn/vx.vix
v={'last':{k:fl(vx.iloc[-1][k]) for k in vx.columns},'pct_sp_since2010':fl((vx.sp[vx.index>='2010']<=vx.sp.iloc[-1]).mean()*100,1),
   'pct_ratio_since2010':fl((vx.ratio[vx.index>='2010']<=vx.ratio.iloc[-1]).mean()*100,1),
   'ratio_1y_max':[str(vx.ratio.iloc[-250:].idxmax().date()),fl(vx.ratio.iloc[-250:].max())]}
# forward: ratio top 5% since 2010 -> NDX vs SPX next 20d, and NDX abs
r10=vx[vx.index>='2010']; thr=r10.ratio.quantile(0.95); v['ratio_p95']=fl(thr)
ev=r10[r10.ratio>=thr].index; sel=[];last=None
for t in ev:
    if last is None or (t-last).days>30: sel.append(t); last=t
sel=[t for t in sel if t<ASOF-pd.Timedelta(days=35)]
a=fwd(ndx,sel,20); b=fwd(spx,sel,20)
v['hist']={'n':len(sel),'ndx_20d_med':fl(np.median(a)),'ndx_minus_spx_20d_med':fl(np.median(a-b)),'ndx_beats_share':fl(((a-b)>0).mean()*100,0),'dates':[str(t.date()) for t in sel]}
# baseline
allr=fwd(ndx,list(r10.index[::5]),20)-fwd(spx,list(r10.index[::5]),20); v['baseline_ndx_minus_spx_20d_med']=fl(np.median(allr))
v['vix9d_vix']=fl(p['^VIX9D'][ASOF]/p['^VIX'][ASOF],3)
out['vxn_vix']=v

# 4. SOX: big weekly gain then Friday drop; Dow up & NDX down days
sox=p['^SOX'].dropna(); dji=p['^DJI'].dropna()
x=pd.concat([sox.pct_change()*100,ndx.pct_change()*100,dji.pct_change()*100,(sox/sox.shift(5)-1)*100],axis=1,keys=['sox','ndx','dji','sox5']).dropna(); x=x[x.index<=ASOF]
x['sox4_prior']=((sox/sox.shift(5))/(sox/sox.shift(1))-1).reindex(x.index)*100
cond=(x.sox<=-3)&(x.sox4_prior>=8)
ev=x[cond].index; sel=[];last=None
for t in ev:
    if last is None or (t-last).days>20: sel.append(t); last=t
sel_past=[t for t in sel if t<ASOF]
s5=fwd(sox,sel_past,5); s20=fwd(sox,sel_past,20)
out['sox_reversal']={'today':{k:fl(x.iloc[-1][k]) for k in x.columns},'n':len(sel_past),
  'sox_5d_med':fl(np.median(s5)) if len(s5) else None,'sox_20d_med':fl(np.median(s20)) if len(s20) else None,'sox_20d_pos':fl((s20>0).mean()*100,0) if len(s20) else None,
  'cases':[[str(t.date()),fl(x.loc[t,'sox4_prior'],1),fl(x.loc[t,'sox'],1),fl(a,1),fl(b,1)] for t,a,b in zip(sel_past,list(fwd(sox,sel_past,5))+[None]*9,list(fwd(sox,sel_past,20))+[None]*9)]}
# baseline 20d SOX since 2000 (weekly sampling)
bs=fwd(sox,list(x.index[::5]),20); out['sox_reversal']['baseline_20d_med']=fl(np.median(bs)); out['sox_reversal']['baseline_20d_pos']=fl((bs>0).mean()*100,0)
cond2=(x.dji>=0)&(x.ndx<=-1.2)&(x.sox<=-3)
out['sox_reversal']['dji_up_ndx_down_n_since2000']=int(cond2.sum()); out['sox_reversal']['dji_up_ndx_down_dates_recent']=[str(t.date()) for t in x[cond2].index[-8:]]
# intraday SMH/SPY 11/13
i=pd.read_parquet(D+'intraday_60m.parquet'); ii=i[(i.date>='2026-11-13 14:00')&(i.date<'2026-11-14')].pivot(index='date',columns='ticker',values=['open','close'])
pc={'SMH':p['SMH'].dropna().iloc[-1],'SPY':p['SPY'].dropna().iloc[-1],'QQQ':p['QQQ'].dropna().iloc[-1]}
intr={}
for t in ['SMH','SPY','QQQ']:
    o=ii[('open',t)].iloc[0]; c1=ii[('close',t)].iloc[0]; cl=ii[('close',t)].iloc[-1]; lo=i[(i.ticker==t)&(i.date>='2026-11-13 14:00')&(i.date<'2026-11-14')].low.min()
    intr[t]={'prev_close_1112':fl(pc[t]),'open':fl((o/pc[t]-1)*100),'first_hour':fl((c1/pc[t]-1)*100),'low':fl((lo/pc[t]-1)*100),'close':fl((cl/pc[t]-1)*100)}
out['intraday_1113']=intr

# 5. weekly / snapshot values
snap={}
for t in ['^GSPC','^NDX','^DJI','^RUT','^SOX','^VIX','^VXN','^TNX','^FVX','^TYX','DX-Y.NYB','JPY=X','GC=F','NKD=F','CL=F','HE=F','BTC-USD','^MOVE']:
    s=p[t].dropna(); s=s[s.index<=ASOF]
    snap[t]={'last':fl(s.iloc[-1],3),'d1':fl((s.iloc[-1]/s.iloc[-2]-1)*100),'w':fl((s.iloc[-1]/s[s.index<=pd.Timestamp('2026-11-06')].iloc[-1]-1)*100),'d1_diff':fl(s.iloc[-1]-s.iloc[-2],3)}
b=p['BTC-USD'].dropna(); snap['BTC_latest']=[str(b.index[-1].date()),fl(b.iloc[-1],0)]
out['snap']=snap
json.dump(out,open('insights/data/analysis/2026-11-14.json','w'),ensure_ascii=False,indent=1)
print(json.dumps(out,ensure_ascii=False,indent=1))
