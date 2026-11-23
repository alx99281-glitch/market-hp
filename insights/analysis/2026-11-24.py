"""分析の視点 2026-11-24 (米国 2026-11-23 の取引日)"""
import json, numpy as np, pandas as pd
D='/tmp/market-data/'
d=pd.read_parquet(D+'daily.parquet')
p=d.pivot_table(index='date',columns='ticker',values='close')
fu=json.load(open(D+'fundamentals.json'))
AS='2026-11-23'
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
    a=a[~np.isnan(a)]
    return dict(n=int(len(a)),median=round(float(np.median(a)),2) if len(a) else None,up=int((a>0).sum()),min=round(float(a.min()),2) if len(a) else None,max=round(float(a.max()),2) if len(a) else None)

# 1 NVDA
nv=s('NVDA'); nr=r('NVDA')
res['nvda']=dict(
  close=round(nv[AS],2), ret=round(nr[AS],2),
  closes={str(k.date()):round(v,2) for k,v in nv['2026-10-26':AS].items()},
  rank_since2000=int((nr>=nr[AS]).sum()),
  big_days=[(str(k.date()),round(v,1)) for k,v in nr[nr>=20].items()],
  mcap_now=fu['NVDA']['marketCap'], mcap_gain_est=fu['NVDA']['marketCap']*(1-1/(1+nr[AS]/100)),
  fwdPE=fu['NVDA']['forwardPE'], short_float=fu['NVDA']['shortPercentOfFloat'],
  high52=fu['NVDA']['fiftyTwoWeekHigh'], from_high=round(nv[AS]/nv[:AS].max()*100-100,2), ath=round(nv[:AS].max(),2), ath_date=str(nv[:AS].idxmax().date()))
nd=nr[nr>=20].index[:-1]
res['nvda']['fwd_after20']={n:summ(fwd(nv,nd,n)) for n in (1,5,20)}
# 同日 他銘柄
day={t:round(r(t)[AS],2) for t in ['SPY','RSP','QQQ','IWM','SMH','^SOX','MU','SNDK','AMD','TSM','ASML','ARM','CRWV','NBIS','ORCL','MSFT','GOOGL','AMZN','META','AAPL','XLU','XLP','XLV','XLE','GLD','^TNX','DX-Y.NYB','CL=F','BZ=F','^VIX','EWJ','EWT','EWY','NKD=F','005930.KS','000660.KS','2330.TW','IBIT','HYG'] if t in p}
res['day']=day
# SPY-RSP スプレッドの分布
spread=(r('SPY')-r('RSP')).dropna()
res['spy_rsp']=dict(today=round(spread[AS],2),rank=int((spread>=spread[AS]).sum()),n=int(len(spread)),since=str(spread.index[0].date()))

# 2 S&P +4% days
sp=s('^GSPC'); sr=r('^GSPC'); ma200=sp.rolling(200).mean(); dd=sp/sp.cummax()*100-100
big=sr[sr>=4].index
rows=[]
for dt in big:
    i=sp.index.get_loc(dt)
    rows.append(dict(date=str(dt.date()),ret=round(sr[dt],2),below200=bool(sp[dt]<ma200[dt]),dd_prev=round(dd.iloc[i-1],1),
      f5=round(sp.iloc[i+5]/sp.iloc[i]*100-100,2) if i+5<len(sp) else None,
      f20=round(sp.iloc[i+20]/sp.iloc[i]*100-100,2) if i+20<len(sp) else None,
      f60=round(sp.iloc[i+60]/sp.iloc[i]*100-100,2) if i+60<len(sp) else None,
      min20=round(sp.iloc[i+1:i+21].min()/sp.iloc[i]*100-100,2) if i+20<len(sp) else None))
bd=pd.DataFrame(rows)
past=bd[bd.date<AS]
# 最初の+4%日 (直前60営業日に+4%日なし)
first=[]
for dt in big[:-1]:
    i=sp.index.get_loc(dt); prev=sp.index[max(0,i-60):i]
    if not any(x in big for x in prev): first.append(dt)
res['sp4']=dict(today=bd[bd.date==AS].to_dict('records'),n_past=int(len(past)),below200_share=round(past.below200.mean()*100,1),
  fwd={k:summ(past[k].astype(float).values) for k in ('f5','f20','f60')},
  min20=summ(past.min20.astype(float).values),
  first_only={n:summ(fwd(sp,first,n)) for n in (5,20,60)}, first_dates=[str(x.date()) for x in first],
  ma200_today=round(ma200[AS],1), dd_today=round(dd[AS],2), dd_prev=round(dd.shift(1)[AS],2),
  table=past[past.date.isin([str(x.date()) for x in first])].to_dict('records'))

# 3 VIX
vx=s('^VIX'); v3=s('^VIX3M'); v9=s('^VIX9D'); vr=r('^VIX')
j=pd.concat([vx,v3,v9,sp],axis=1,keys=['vix','v3','v9','sp']).dropna(subset=['vix','sp'])
j['vr']=j.vix.pct_change()*100; j['ratio']=j.vix/j.v3
res['vix']=dict(vix=round(vx[AS],2),ret=round(vr[AS],2),vix3m=round(v3[AS],2),vix9d=round(v9[AS],2),ratio=round(j.ratio[AS],3),
  rank_drop=int((vr<=vr[AS]).sum()), n=int(vr.notna().sum()), since=str(vr.dropna().index[0].date()))
cond=j[(j.vr<=-20)&(j.index<AS)]
res['vix']['drop20']=dict(dates=[str(x.date()) for x in cond.index],**{f'f{n}':summ(fwd(sp,cond.index,n)) for n in (5,20)})
c2=cond[cond.ratio>1]
res['vix']['drop20_inverted']=dict(dates=[str(x.date()) for x in c2.index],**{f'f{n}':summ(fwd(sp,c2.index,n)) for n in (5,20)})
c3=cond[cond.ratio<=1]
res['vix']['drop20_normal']=dict(n=int(len(c3)),**{f'f{n}':summ(fwd(sp,c3.index,n)) for n in (5,20)})
# 期間構造の逆転が続いた日数
inv=(j.ratio>1); k=0
for v in inv[:AS][::-1]:
    if v: k+=1
    else: break
res['vix']['inverted_streak']=k

# 4 Asia: TSM ADR vs 2330.TW 翌日
tw=s('2330.TW'); ts=s('TSM')
a=pd.DataFrame({'tsm':ts.pct_change()*100})
tr=tw.pct_change()*100
nxt=[]
for dt in a.index:
    after=tr[tr.index>dt]
    nxt.append(after.iloc[0] if len(after) else np.nan)
a['tw_next']=nxt; a=a.dropna()
a=a[a.index>='2015-01-01']
b=np.polyfit(a.tsm,a.tw_next,1)
res['asia']=dict(tsm=round(r('TSM')[AS],2),tw_today=round(tr[AS],2),beta=round(b[0],3),corr=round(a.corr().iloc[0,1],3),n=int(len(a)),
  pred=round(b[0]*r('TSM')[AS]+b[1],2))
bigt=a[a.tsm>=8]
res['asia']['tsm_ge8']=[(str(k.date()),round(x.tsm,1),round(x.tw_next,1)) for k,x in bigt.iterrows()]
# 台湾の値幅制限(10%)に当たった翌日
res['asia']['tw_limit_days']=int((tr.abs()>=9.5).sum())
# 日経
nk=s('^N225'); nkd=s('NKD=F')
res['asia']['nkd']=round(nkd[AS],1); res['asia']['n225']=round(nk.iloc[-1],2); res['asia']['n225_date']=str(nk.index[-1].date())
res['asia']['nkd_vs_n225']=round(nkd[AS]/nk.iloc[-1]*100-100,2)
for t in ['6857.T','8035.T','285A.T','9984.T']:
    if t in p: res['asia'][t]=dict(last=round(s(t).iloc[-1],1),date=str(s(t).index[-1].date()),ret_1113_1120=round(s(t).iloc[-1]/s(t)[:'2026-11-13'].iloc[-1]*100-100,2))
res['asia']['ewy']=round(r('EWY')[AS],2); res['asia']['ewt']=round(r('EWT')[AS],2); res['asia']['ewj']=round(r('EWJ')[AS],2)

# 5 memory divergence MU vs SNDK
mu=r('MU'); sn=r('SNDK'); m=pd.concat([mu,sn],axis=1,keys=['mu','sn']).dropna()
m['gap']=m.mu-m.sn
res['mem']=dict(mu=round(mu[AS],2),sndk=round(sn[AS],2),gap=round(m.gap[AS],2),n=int(len(m)),since=str(m.index[0].date()),
  rank_gap=int((m.gap.abs()>=abs(m.gap[AS])).sum()),
  opp_sign_10=int(((np.sign(m.mu)!=np.sign(m.sn))&(m.gap.abs()>=10)).sum()),
  corr_all=round(m.mu.corr(m.sn),3), corr_60=round(m.mu[-61:-1].corr(m.sn[-61:-1]),3),
  sndk_closes={str(k.date()):round(v,2) for k,v in s('SNDK')['2026-11-09':AS].items()},
  mu_closes={str(k.date()):round(v,2) for k,v in s('MU')['2026-11-09':AS].items()},
  wdc=round(r('WDC')[AS],2) if 'WDC' in p and s('WDC').index[-1]==pd.Timestamp(AS) else None,
  stx=round(r('STX')[AS],2) if 'STX' in p and s('STX').index[-1]==pd.Timestamp(AS) else None,
  fwdPE={t:fu[t].get('forwardPE') for t in ['MU','SNDK','WDC','STX']},
  samsung=round(r('005930.KS')[AS],2), hynix=round(r('000660.KS')[AS],2))
top=m.gap.abs().sort_values(ascending=False).head(6)
res['mem']['top_gaps']=[(str(k.date()),round(m.mu[k],1),round(m.sn[k],1)) for k in top.index]

# 6 cross asset: dollar, gold, oil, 10y
dx=s('DX-Y.NYB')
res['xa']=dict(dxy=round(dx[AS],3),dxy_ret=round(r('DX-Y.NYB')[AS],2),dxy_high_since=str(dx[dx>=dx[AS]].index[-2].date()) if (dx>=dx[AS]).sum()>1 else 'n/a',
  tnx=round(s('^TNX')[AS],3),tnx_chg_bp=round((s('^TNX')[AS]-s('^TNX').iloc[-2])*100,1),irx=round(s('^IRX')[AS],3),
  gold=round(s('GC=F')[AS],1),gold_ret=round(r('GC=F')[AS],2),wti=round(s('CL=F')[AS],2),wti_ret=round(r('CL=F')[AS],2),brent=round(s('BZ=F')[AS],2),brent_ret=round(r('BZ=F')[AS],2))
# S&P +3%以上 かつ ドル指数上昇 の日
both=pd.concat([sr,r('DX-Y.NYB')],axis=1,keys=['sp','dx']).dropna()
x=both[(both.sp>=3)]
res['xa']['sp3_days']=int(len(x)); res['xa']['sp3_dxup']=int((x.dx>0).sum())
oil_sd=r('CL=F')[-251:-1].std(); res['xa']['wti_sigma']=round(r('CL=F')[AS]/oil_sd,2)
json.dump(res,open('insights/data/analysis/2026-11-24.json','w'),ensure_ascii=False,indent=1,default=str)
print(json.dumps(res,ensure_ascii=False,default=str)[:9000])
