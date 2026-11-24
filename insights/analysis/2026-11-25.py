"""分析の視点 2026-11-25 (米国 2026-11-24 の取引日)"""
import json, numpy as np, pandas as pd
D='/tmp/market-data/'
d=pd.read_parquet(D+'daily.parquet')
p=d.pivot_table(index='date',columns='ticker',values='close')
AS=pd.Timestamp('2026-11-24'); PRV=pd.Timestamp('2026-11-23'); BASE=pd.Timestamp('2026-11-20')
res={}
def s(t): return p[t].dropna()
def r(t): return s(t).pct_change()*100
def fwd(ser,dates,n):
    out=[]
    for dt in dates:
        i=ser.index.get_loc(dt)
        out.append(ser.iloc[i+n]/ser.iloc[i]*100-100 if i+n<len(ser) else np.nan)
    return np.array(out)
def summ(a):
    a=np.array(a,dtype=float); a=a[~np.isnan(a)]
    return dict(n=int(len(a)),median=round(float(np.median(a)),2) if len(a) else None,up=int((a>0).sum()),min=round(float(a.min()),2) if len(a) else None,max=round(float(a.max()),2) if len(a) else None)
def sig(t):
    rr=r(t); sd=rr[:AS].iloc[-251:-1].std(); return round(rr[AS]/sd,1)

# 1 SOX whipsaw: +10%以上の翌日に-5%以下
sx=s('^SOX'); sr=r('^SOX')
idx=list(sr.index)
cases=[]
for i in range(1,len(idx)):
    if sr.iloc[i-1]>=10 and sr.iloc[i]<=-5: cases.append(idx[i])
res['sox']=dict(ret=round(sr[AS],2),prev=round(sr[PRV],2),sigma=sig('^SOX'),
  two_day=round(sx[AS]/sx[BASE]*100-100,2),
  big_up_days=int((sr>=10).sum()),
  whipsaw=[(str(c.date()),round(sr.iloc[sr.index.get_loc(c)-1],1),round(sr[c],1),
            *(round(x,1) if not np.isnan(x) else None for x in [fwd(sx,[c],5)[0],fwd(sx,[c],20)[0]])) for c in cases],
  after_up10_next={**summ(sr.shift(-1)[sr>=10].dropna().values)},
  from_high=round(sx[AS]/sx[:AS].max()*100-100,2))
res['sox']['whip_fwd']={n:summ(fwd(sx,[c for c in cases if c!=AS],n)) for n in (5,20)}
# 2日で月曜の上げのどれだけを残したか
names=['NVDA','AMD','MU','SNDK','TSM','ARM','ASML','CRWV','NBIS','ORCL','ANT','MSFT','GOOGL','AMZN','META','AAPL','SMH','QQQ','SPY','RSP','^DJI','IGV','XLV','XLP','XLU','XLF','XLE','IWM','000660.KS','005930.KS','2330.TW','6857.T','8035.T','285A.T']
ret={}
for t in names:
    if t not in p: continue
    x=s(t)
    if PRV not in x.index or AS not in x.index or BASE not in x.index:
        ret[t]=dict(note='missing'); continue
    m=x[PRV]/x[BASE]*100-100; tu=x[AS]/x[PRV]*100-100; two=x[AS]/x[BASE]*100-100
    ret[t]=dict(mon=round(m,2),tue=round(tu,2),two=round(two,2),kept=round(two/m*100,0) if m>0 else None)
res['retention']=ret
# 3 ローテーション: NDX -1.5%以下かつ DJI +0.5%以上の日
nd=r('^NDX'); dj=r('^DJI'); df=pd.concat([nd,dj],axis=1,keys=['nd','dj']).dropna()
rot=df[(df.nd<=-1.5)&(df.dj>=0.5)]
res['rotation']=dict(today=dict(ndx=round(nd[AS],2),dji=round(dj[AS],2)),n=int(len(rot)),
   dates=[str(x.date()) for x in rot.index],
   fwd_ndx={n:summ(fwd(s('^NDX'),[x for x in rot.index if x!=AS],n)) for n in (5,20)},
   fwd_spx={n:summ(fwd(s('^GSPC'),[x for x in rot.index if x!=AS],n)) for n in (5,20)})
spread=(r('RSP')-r('SPY')).dropna()
res['rotation']['rsp_minus_spy']=dict(today=round(spread[AS],2),rank_since=str(spread.index[0].date()),rank=int((spread>=spread[AS]).sum()),n=int(len(spread)),prev=round(spread[PRV],2))
sect=['XLV','XLP','XLU','XLF','XLE','XLI','XLB','XLRE','XLY','XLC','XLK']
res['sectors']={t:round(r(t)[AS],2) for t in sect}
res['sectors_sigma']={t:sig(t) for t in sect}
xv=r('XLV'); xk=r('XLK'); dd=pd.concat([xv,xk],axis=1,keys=['v','k']).dropna()
res['xlv_xlk']=dict(today=round(xv[AS]-xk[AS],2),n_ge=int(((dd.v-dd.k)>=(xv[AS]-xk[AS])).sum()),since=str(dd.index[0].date()))
# 4 メモリ: MU -11% 2日前比、相関
mu=s('MU'); mr=r('MU')
res['memory']=dict(mu=round(mr[AS],2),mu_sigma=sig('MU'),mu_close=round(mu[AS],2),mu_from_high=round(mu[AS]/mu[:AS].max()*100-100,1),mu_high_date=str(mu[:AS].idxmax().date()),
   sndk=round(r('SNDK')[AS],2), hynix_tue=round(r('000660.KS').get(AS,np.nan),2),
   mu_le_m10=int((mr<=-10).sum()), mu_le_m10_dates=[str(x.date()) for x in mr[mr<=-10].index[-6:]])
dl=pd.read_parquet('daily-review/data/prices.parquet')
dell=dl[dl.ticker=='DELL'].set_index('date')['close'].sort_index()
dell.index=pd.to_datetime(dell.index)
hpq=dl[dl.ticker=='HPQ'].set_index('date')['close'].sort_index(); hpq.index=pd.to_datetime(hpq.index)
j=pd.concat([dell.pct_change(),mu.pct_change(),hpq.pct_change(),s('SMH').pct_change()],axis=1,keys=['DELL','MU','HPQ','SMH']).dropna()
res['memory']['corr60_dell_mu']=round(j['DELL'].iloc[-60:].corr(j['MU'].iloc[-60:]),2)
res['memory']['corr60_dell_smh']=round(j['DELL'].iloc[-60:].corr(j['SMH'].iloc[-60:]),2)
res['memory']['corr60_hpq_mu']=round(j['HPQ'].iloc[-60:].corr(j['MU'].iloc[-60:]),2)
res['memory']['dell_last']=dict(date=str(dell.index[-1].date()),close=round(dell.iloc[-1],2),from_high=round(dell.iloc[-1]/dell.max()*100-100,1),high_date=str(dell.idxmax().date()),ytd=round(dell.iloc[-1]/dell[:'2025-12-31'].iloc[-1]*100-100,1))
# 5 ANT
an=s('ANT')
res['ant']=dict(closes={str(k.date()):round(v,2) for k,v in an.items()},ipo=83.0,vs_ipo=round(an[AS]/83*100-100,2),from_high=round(an[AS]/an.max()*100-100,1))
res['ant']['corr_beta']=None
x=pd.concat([r('ANT'),r('NVDA'),r('IGV'),r('QQQ')],axis=1,keys=['ANT','NVDA','IGV','QQQ']).dropna()
res['ant']['daily']=x.round(2).reset_index().astype(str).values.tolist()
# 6 関税報道の当日反応
tar=['CNY=X','KRW=X','TWD=X','INR=X','JPY=X','EURUSD=X','MXN=X','VNM','INDA','FXI','KWEB','MCHI','EWJ','EWG','EWY','EWT','EWW','XRT','ITB','HG=F','CL=F','GC=F','DX-Y.NYB','NKD=F','^TNX','^FVX','^IRX','TLT','BTC-USD','^VIX','^VIX3M','^VXN','^MOVE']
res['tariff_day']={t:dict(ret=round(r(t)[AS],2),sigma=sig(t),level=round(s(t)[AS],4)) for t in tar if t in p and AS in s(t).index}
v=s('^VIX'); v3=s('^VIX3M')
res['vix']=dict(vix=round(v[AS],2),ratio=round(v[AS]/v3[AS],3),prev_ratio=round(v[PRV]/v3[PRV],3))
# SOX -7%以下の日のVIX変化の分布
vv=r('^VIX'); dd2=pd.concat([sr,vv],axis=1,keys=['sox','vix']).dropna()
big=dd2[dd2.sox<=-7]
res['vix']['sox_le_m7']=dict(n=int(len(big)),vix_median=round(big.vix.median(),1),vix_le_today=int((big.vix<=vv[AS]).sum()))
# NKD vs N225
res['nkd']=dict(nkd=float(s('NKD=F')[AS]),n225=float(s('^N225').iloc[-1]),n225_date=str(s('^N225').index[-1].date()))
res['nkd']['gap']=round(res['nkd']['nkd']/res['nkd']['n225']*100-100,2)
json.dump(res,open('insights/data/analysis/2026-11-25.json','w'),ensure_ascii=False,indent=1,default=str)
print(json.dumps(res,ensure_ascii=False,default=str)[:9000])
