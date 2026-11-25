"""分析の視点 2026-11-26号 (対象: 米国 2026-11-25)"""
import json, numpy as np, pandas as pd
from pathlib import Path
D='/tmp/market-data/'
d=pd.read_parquet(D+'daily.parquet'); d['date']=pd.to_datetime(d['date'])
f=pd.read_parquet(D+'fred.parquet'); f['date']=pd.to_datetime(f['date'])
def s(t,col='close'): return d[d.ticker==t].set_index('date')[col].sort_index()
def px(t): return d[d.ticker==t].set_index('date').sort_index()
out={}
r=lambda x: None if pd.isna(x) else round(float(x),2)

# 1. 日中の大幅安から戻した日
res={}
for t,low_th,close_th in [('^GSPC',-3.0,-0.5),('^NDX',-4.0,-1.0)]:
    p=px(t); pc=p.close.shift(1)
    lowr=(p.low/pc-1)*100; cr=(p.close/pc-1)*100
    rec=(p.close-p.low)/(pc-p.low)
    ev=p[(lowr<=low_th)&(cr>=close_th)].index
    rows=[]
    for dt in ev:
        i=p.index.get_loc(dt)
        g=lambda k: (p.close.iloc[i+k]/p.close.iloc[i]-1)*100 if i+k<len(p) else np.nan
        rows.append({'date':str(dt.date()),'low':r(lowr[dt]),'close':r(cr[dt]),'next1':r(g(1)),'next5':r(g(5)),'next20':r(g(20))})
    past=[x for x in rows if x['date']!='2026-11-25']
    def st(k):
        v=[x[k] for x in past if x[k] is not None]
        return {'n':len(v),'median':r(np.median(v)) if v else None,'up':int(sum(1 for z in v if z>0))}
    res[t]={'today_low':r(lowr.iloc[-1]),'today_close':r(cr.iloc[-1]),'recovery_ratio':r(rec.iloc[-1]),'events':rows,'next1':st('next1'),'next5':st('next5'),'next20':st('next20')}
out['reversal']=res
# 60分足 QQQ
i60=pd.read_parquet(D+'intraday_60m.parquet')
q=i60[(i60.ticker=='QQQ')]
q=q.assign(dt=pd.to_datetime(q[q.columns[0]] if 'datetime' not in q.columns else q['datetime']))
out['qqq_60m_last']=q.tail(8).astype(str).to_dict('records')

# 2. VIX: S&Pほぼ横ばいでVIX+7%、期間構造、感謝祭
vix=s('^VIX'); v9=s('^VIX9D'); v3=s('^VIX3M'); spx=s('^GSPC')
j=pd.concat([spx.pct_change()*100,vix.pct_change()*100],axis=1,keys=['spx','vix']).dropna()
cond=j[(j.spx.abs()<=0.5)&(j.vix>=7)]
out['vix_up_flat']={'n_since2000':int(len(cond)),'dates_recent':[str(x.date()) for x in cond.index[-8:]]}
term=(vix/v3).dropna()
inv=(term>1).astype(int); streak=0
for x in inv[::-1]:
    if x: streak+=1
    else: break
out['vix_term']={'vix':r(vix.iloc[-1]),'vix9d':r(v9.iloc[-1]),'vix3m':r(v3.iloc[-1]),'ratio':round(float(term.iloc[-1]),3),'streak':streak,'v9_over_vix':round(float(v9.iloc[-1]/vix.iloc[-1]),3)}
# 過去の連続逆転の長さ
runs=[];c=0;start=None
for dt,x in inv.items():
    if x: c+=1; start=start or dt
    else:
        if c: runs.append((str(start.date()),c))
        c=0;start=None
out['vix_term']['runs_ge_streak']=[x for x in runs if x[1]>=streak]
# 感謝祭の翌日(金曜)
tg=[]
for y in range(2000,2026):
    nov=pd.date_range(f'{y}-11-01',f'{y}-11-30'); th=[x for x in nov if x.weekday()==3][3]
    wed=th-pd.Timedelta(days=1); fri=th+pd.Timedelta(days=1)
    if wed in spx.index and fri in spx.index:
        i=spx.index.get_loc(fri)
        tg.append({'year':y,'wed':r((spx[wed]/spx.iloc[spx.index.get_loc(wed)-1]-1)*100),'fri':r((spx[fri]/spx[wed]-1)*100),
                   'next5':r((spx.iloc[i+5]/spx[fri]-1)*100),'vix_fri':r((vix[fri]/vix[wed]-1)*100) if fri in vix.index else None})
tgd=pd.DataFrame(tg)
out['thanksgiving']={'rows':tg,'fri_median':r(tgd.fri.median()),'fri_up':int((tgd.fri>0).sum()),'n':len(tgd),
  'vix_fri_median':r(tgd.vix_fri.median()),'vix_fri_down':int((tgd.vix_fri<0).sum()),
  'wed_neg':{'n':int((tgd.wed<0).sum()),'fri_up':int(((tgd.wed<0)&(tgd.fri>0)).sum())},'next5_median':r(tgd.next5.median()),'next5_up':int((tgd.next5>0).sum())}

# 3. 金利: PCE上振れでも10年低下
def fs(name): return f[f.series==name].set_index('date')['value'].sort_index()
tnx=s('^TNX'); irx=s('^IRX'); fvx=s('^FVX')
t10y3m=fs('T10Y3M'); be=fs('T10YIE'); real=fs('DFII10'); t5f=fs('T5YIFR')
out['rates']={'tnx':[r(x) for x in tnx.iloc[-3:]],'tnx_chg_bp':r((tnx.iloc[-1]-tnx.iloc[-2])*100),
  'tnx_1m_bp':r((tnx.iloc[-1]-tnx.iloc[-22])*100),'irx_1m_bp':r((irx.iloc[-1]-irx.iloc[-22])*100),
  'tnx_high_3m':r(tnx.iloc[-63:].max()),'tnx_high_date':str(tnx.iloc[-63:].idxmax().date()),
  't10y3m':r(t10y3m.iloc[-1]),'t10y3m_1m':r(t10y3m.iloc[-1]-t10y3m.loc[:t10y3m.index[-1]-pd.Timedelta(days=30)].iloc[-1]),
  'be10':r(be.iloc[-1]),'be10_date':str(be.index[-1].date()),'be10_low_since':str(be[be<=be.iloc[-1]].index[-2].date()) if (be<=be.iloc[-1]).sum()>1 else None,
  'real10':r(real.iloc[-1]),'real10_date':str(real.index[-1].date()),'t5y5y':r(t5f.iloc[-1])}
# PCE発表日ではなく「10年-3か月差が1か月で大きく縮小」した後の株(S&P)
sp=spx
m=t10y3m.dropna(); chg=m-m.shift(21)
ev=chg[chg<=-0.25]
# 重複を避け、20営業日空ける
sel=[];last=None
for dt in ev.index:
    if last is None or (dt-last).days>40: sel.append(dt); last=dt
rows=[]
for dt in sel:
    if dt<pd.Timestamp('2000-01-01') or dt not in sp.index: continue
    i=sp.index.get_loc(dt)
    rows.append({'date':str(dt.date()),'chg':r(chg[dt]),'level':r(m[dt]),'spx20':r((sp.iloc[i+20]/sp.iloc[i]-1)*100) if i+20<len(sp) else None})
out['curve_flatten_events']=rows
# 円: 米10年とドル円の相関
jpy=s('JPY=X')
z=pd.concat([jpy.pct_change()*100,tnx.diff()*100],axis=1,keys=['jpy','tnx']).dropna()
out['jpy_corr']={'60d':r(z.iloc[-60:].corr().iloc[0,1]),'250d':r(z.iloc[-250:].corr().iloc[0,1]),'jpy':r(jpy.iloc[-1]),'jpy_1m':r((jpy.iloc[-1]/jpy.iloc[-22]-1)*100)}

# 4. デル・HP vs メモリ
hw={}
for t in ['DELL','HPQ','MU','SNDK','WDC','STX']:
    p=px(t).tail(4)
    pc=p.close.shift(1)
    hw[t]={'dates':[str(x.date()) for x in p.index],'close':[r(x) for x in p.close],'ret':r((p.close.iloc[-1]/pc.iloc[-1]-1)*100),
            'open':r((p.open.iloc[-1]/pc.iloc[-1]-1)*100),'low':r((p.low.iloc[-1]/pc.iloc[-1]-1)*100)}
out['hw_memory']=hw
rets=pd.concat({t:s(t).pct_change() for t in ['DELL','HPQ','MU']},axis=1).dropna()
out['hw_corr60']={'DELL_MU':r(rets.iloc[-60:].corr().loc['DELL','MU']),'HPQ_MU':r(rets.iloc[-60:].corr().loc['HPQ','MU']),
                  'DELL_MU_prev':r(rets.iloc[-61:-1].corr().loc['DELL','MU']),'HPQ_MU_prev':r(rets.iloc[-61:-1].corr().loc['HPQ','MU'])}
# デル: 日中-10%以下から引けプラスは過去に
p=px('DELL'); pc=p.close.shift(1); lr=(p.low/pc-1)*100; cr=(p.close/pc-1)*100
out['dell_rev']={'n':int(((lr<=-8)&(cr>0)).sum()),'dates':[str(x.date()) for x in p[(lr<=-8)&(cr>0)].index],'since':str(p.index[0].date())}
# 1か月
out['hw_1m']={t:r((s(t).iloc[-1]/s(t).iloc[-22]-1)*100) for t in ['DELL','HPQ','MU','SNDK']}

# 5. 東京・韓国の半導体: 前夜SOXからの説明
sox=s('^SOX')
asia={}
for t,nm in [('6857.T','アドバンテスト'),('8035.T','東京エレクトロン'),('285A.T','キオクシア'),('9984.T','ソフトバンクG'),('4062.T','イビデン'),('000660.KS','SKハイニックス'),('005930.KS','サムスン電子')]:
    a=s(t)
    ar=a.pct_change()*100
    # アジアの日付tに対し、米国の直近の前営業日のSOX
    sx=(sox.pct_change()*100)
    sx_prev=sx.reindex(a.index, method=None)
    prev=[]
    for dt in a.index:
        k=sx.index.searchsorted(dt)-1
        prev.append(sx.iloc[k] if k>=0 else np.nan)
    df=pd.DataFrame({'a':ar,'sox_prev':prev},index=a.index).dropna()
    w=df.iloc[-251:-1]
    b=np.polyfit(w.sox_prev,w.a,1)
    pred=b[0]*df.sox_prev.iloc[-1]+b[1]
    # 2日通算(11/24 + 11/25) vs SOX 2日(11/23+11/24)
    two=(a.iloc[-1]/a.iloc[-3]-1)*100
    asia[t]={'name':nm,'date':str(a.index[-1].date()),'ret':r(ar.iloc[-1]),'beta250':r(b[0]),'pred':r(pred),'resid':r(ar.iloc[-1]-pred),'two_day':r(two),
             'corr250':r(w.corr().iloc[0,1]),'prev_date':str(a.index[-2].date()),'prev_ret':r(ar.iloc[-2])}
out['asia_semis']=asia
out['sox']={'last3':[r(x) for x in (sox.pct_change()*100).iloc[-3:]],'two_day':r((sox.iloc[-2]/sox.iloc[-4]-1)*100),
  'low_today':r((px('^SOX').low.iloc[-1]/sox.iloc[-2]-1)*100),'since_1120':r((sox.iloc[-1]/sox.loc['2026-11-20']-1)*100)}
nk=s('NKD=F'); out['nkd']={'last':r(nk.iloc[-1]),'chg':r((nk.iloc[-1]/nk.iloc[-2]-1)*100)}
n225=s('^N225'); out['n225']={'last_date':str(n225.index[-1].date()),'last':r(n225.iloc[-1])}

# 6. 原油: 11月の下落と過去の大幅月間下落後のCPI
bz=s('BZ=F'); cl=s('CL=F')
me=bz.resample('ME').last(); mret=me.pct_change()*100
cur=(bz.iloc[-1]/bz.loc[:'2026-10-31'].iloc[-1]-1)*100
clm=(cl.iloc[-1]/cl.loc[:'2026-10-31'].iloc[-1]-1)*100
hist=mret.iloc[:-1].dropna()
rank=int((hist<=cur).sum())
cpi=fs('CPIAUCSL'); cpim=cpi.resample('ME').last()
rows=[]
for dt,v in hist[hist<=-15].items():
    try:
        i=cpim.index.get_loc(dt)
        rows.append({'month':str(dt.date())[:7],'brent':r(v),'cpi_next3m_ann':r(((cpim.iloc[i+3]/cpim.iloc[i])**4-1)*100) if i+3<len(cpim) else None,
                     'cpi_prev3m_ann':r(((cpim.iloc[i]/cpim.iloc[i-3])**4-1)*100)})
    except Exception: pass
out['oil']={'brent_mtd':r(cur),'wti_mtd':r(clm),'brent_last':r(bz.iloc[-1]),'brent_oct_end':r(bz.loc[:'2026-10-31'].iloc[-1]),
  'rank_since2000':rank,'n_months':len(hist),'worse_months':[(str(k.date())[:7],r(v)) for k,v in hist[hist<=cur].items()],
  'big_drop_months':rows,'cpi_last':str(cpi.index[-1].date()),'cpi_yoy':r((cpi.iloc[-1]/cpi.iloc[-13]-1)*100),
  'be10':r(be.iloc[-1]),'be10_1m':r(be.iloc[-1]-be.loc[:be.index[-1]-pd.Timedelta(days=30)].iloc[-1]),
  'ng_1d':r((s('NG=F').iloc[-1]/s('NG=F').iloc[-2]-1)*100),'cl_1d':r((cl.iloc[-1]/cl.iloc[-2]-1)*100)}
v=[x['cpi_next3m_ann']-x['cpi_prev3m_ann'] for x in rows if x['cpi_next3m_ann'] is not None]
out['oil']['cpi_decel']={'n':len(v),'median_change':r(np.median(v)) if v else None,'decel':int(sum(1 for z in v if z<0))}

# スナップショット
snap={}
for t in ['^GSPC','^DJI','^NDX','^SOX','SPY','RSP','NVDA','ANT','DELL','HPQ','MU','^VIX','^TNX','DX-Y.NYB','NKD=F','JPY=X','GC=F','CL=F','BZ=F','META','ORCL','XLB','XLE','XLRE','XLK','IWM']:
    a=s(t); snap[t]={'close':r(a.iloc[-1]),'chg':r((a.iloc[-1]/a.iloc[-2]-1)*100),'date':str(a.index[-1].date())}
out['snapshot']=snap
Path('insights/data/analysis').mkdir(parents=True,exist_ok=True)
json.dump(out,open('insights/data/analysis/2026-11-26.json','w'),ensure_ascii=False,indent=1,default=str)
print(json.dumps({k:v for k,v in out.items() if k not in('qqq_60m_last',)},ensure_ascii=False,default=str)[:12000])
