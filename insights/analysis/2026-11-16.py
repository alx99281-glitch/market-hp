"""2026-11-16 週末版の分析(データは2026-11-13 NY引けまで。BTCは11/14 01:44 UTC取得時点まで)"""
import json, pandas as pd, numpy as np
d = pd.read_parquet('/tmp/market-data/daily.parquet')
p = d.pivot(index='date', columns='ticker', values='close').sort_index()
out = {}

# ---- 1. NVDA: 週次の連続下落、決算の想定変動 ±9.1% の大きさ ----
nv = p['NVDA'].dropna()
wk = nv.resample('W-FRI').last().dropna()
wr = wk.pct_change()
neg = (wr < 0).astype(int)
streak = neg.groupby((neg != neg.shift()).cumsum()).cumsum() * neg
cur = int(streak.iloc[-1])
past = streak[streak >= cur]
prev_same = past[past.index < wk.index[-1] - pd.Timedelta(days=7*cur)]
# 連続下落が cur 週に達した時点(初到達)を抽出
hits = streak[(streak == cur)]
ev = []
for dt in hits.index[:-1]:
    i = wk.index.get_loc(dt)
    r4 = wk.iloc[i+4]/wk.iloc[i]-1 if i+4 < len(wk) else None
    r13 = wk.iloc[i+13]/wk.iloc[i]-1 if i+13 < len(wk) else None
    total = wk.iloc[i]/wk.iloc[i-cur]-1
    ev.append(dict(date=str(dt.date()), streak_drop=round(total*100,1),
                   next4w=None if r4 is None else round(r4*100,1),
                   next13w=None if r13 is None else round(r13*100,1)))
streak_total = wk.iloc[-1]/wk.iloc[-1-cur]-1
dr = nv.pct_change().dropna()
sd250 = dr.iloc[-250:].std()
last3y = dr[dr.index >= dr.index[-1] - pd.Timedelta(days=365*3)]
out['nvda'] = dict(
    last_close=round(float(nv.iloc[-1]),2), week_ret=round(float(wr.iloc[-1])*100,2),
    current_weekly_losing_streak=cur, streak_total_pct=round(float(streak_total)*100,1),
    weekly_returns_streak=[round(float(x)*100,1) for x in wr.iloc[-cur:]],
    max_streak_since_2000=int(streak.max()), max_streak_date=str(streak.idxmax().date()),
    prior_episodes_same_or_longer=ev,
    sd250_daily_pct=round(float(sd250)*100,2), implied_move_9_1_in_sigma=round(9.1/(sd250*100),2),
    days_abs_ge_9_1_last3y=int((last3y.abs() >= 0.091).sum()), n_days_last3y=int(len(last3y)),
    off_high_pct=round(float(nv.iloc[-1]/nv['2026'].max()-1)*100,1), high_date=str(nv['2026'].idxmax().date()),
)
# 前回5週以上の連続下落の時期
s5 = streak[streak >= 5]
out['nvda']['episodes_ge5w_end_dates'] = sorted({str(g.index[-1].date()) for _, g in s5.groupby((s5.index.to_series().diff() > pd.Timedelta(days=8)).cumsum())})

# ---- 2. ビットコインの週末下落は月曜の株安を示すか ----
b = p['BTC-USD'].dropna()
rows = []
for fri in b.index[b.index.day_of_week == 4]:
    sun = fri + pd.Timedelta(days=2); mon = fri + pd.Timedelta(days=3)
    if sun not in b.index: continue
    wret = b[sun]/b[fri]-1
    rec = dict(fri=fri, btc_wk=wret)
    for t in ['^NDX', '^GSPC', '^N225', 'NKD=F']:
        s = p[t].dropna()
        if fri in s.index and mon in s.index:
            rec[t] = s[mon]/s[fri]-1
    rows.append(rec)
w = pd.DataFrame(rows).set_index('fri')
res = {}
for th in [-0.05, -0.07]:
    sub = w[w.btc_wk <= th]
    r = dict(n=int(len(sub)))
    for t in ['^NDX', '^GSPC', '^N225', 'NKD=F']:
        x = sub[t].dropna()
        r[t] = dict(n=int(len(x)), median=round(float(x.median())*100,2), mean=round(float(x.mean())*100,2), pct_up=round(float((x>0).mean())*100))
    r['dates'] = [str(i.date()) for i in sub.index[-8:]]
    res[f'btc_weekend_le_{int(-th*100)}pct'] = r
allr = {}
for t in ['^NDX', '^GSPC', '^N225', 'NKD=F']:
    x = w[t].dropna(); allr[t] = dict(n=int(len(x)), median=round(float(x.median())*100,2), pct_up=round(float((x>0).mean())*100),
        corr_with_btc_weekend=round(float(w[['btc_wk', t]].dropna().corr().iloc[0,1]),3))
res['all_weekends'] = allr
# 2021年以降に限定
w21 = w[w.index >= '2021-01-01']
sub = w21[w21.btc_wk <= -0.05]
res['since2021_le_5pct'] = {t: dict(n=int(sub[t].notna().sum()), median=round(float(sub[t].median())*100,2), pct_up=round(float((sub[t].dropna()>0).mean())*100)) for t in ['^NDX','^N225','NKD=F']}
res['since2021_corr'] = {t: round(float(w21[['btc_wk', t]].dropna().corr().iloc[0,1]),3) for t in ['^NDX','^N225','NKD=F']}
# 現在: 報道の日曜値 64,821(CoinDesk、11/15 12:33 EST)と、取得済みの最終値
res['btc_latest_in_data'] = {str(k.date()): round(float(v)) for k, v in b.iloc[-4:].items()}
res['btc_reported_sun'] = 64821
res['btc_reported_vs_1112'] = round((64821/b['2026-11-12']-1)*100,1)
res['btc_reported_vs_1104'] = round((64821/b['2026-11-04']-1)*100,1)
# BTCとナスダックの直近60日の日次相関(平日のみ)
j = pd.concat([b.pct_change(), p['^NDX'].pct_change()], axis=1, sort=True).dropna()
j.columns = ['btc', 'ndx']
res['corr_btc_ndx_60d'] = round(float(j.iloc[-60:].corr().iloc[0,1]),3)
res['corr_btc_ndx_250d'] = round(float(j.iloc[-250:].corr().iloc[0,1]),3)
out['btc_weekend'] = res

# ---- 3. 「売りではなく入れ替え」: NVDA高値(10/6)以降のセクター ----
start = pd.Timestamp('2026-10-06'); end = p.index[p['^GSPC'].notna()][-1]
secs = ['XLK','SMH','XLC','XLY','XLF','XLI','XLE','XLB','XLU','XLP','XLV','XLRE','RSP','SPY','QQQ','IWM']
rets = {s: round(float(p[s].dropna().loc[:end].iloc[-1]/p[s].dropna().loc[:start].iloc[-1]-1)*100,2) for s in secs}
wk_start = pd.Timestamp('2026-11-06')
rets_w = {s: round(float(p[s].dropna().loc[:end].iloc[-1]/p[s].dropna().loc[:wk_start].iloc[-1]-1)*100,2) for s in secs}
rets_d = {s: (round(float(p[s].dropna().pct_change().loc[end])*100,2) if end in p[s].dropna().index else None) for s in secs}
last_dates = {s: str(p[s].dropna().index[-1].date()) for s in secs}
# S&P500採用銘柄の騰落(10/6→11/13)
pr = pd.read_parquet('daily-review/data/prices.parquet')
pc = pr.pivot(index='date', columns='ticker', values='adj_close').sort_index()
pc = pc.drop(columns=[c for c in pc.columns if c.startswith('^')])
a = pc.loc[:start].iloc[-1]; z = pc.loc[:end].ffill().iloc[-1]
r = (z/a-1).dropna()
lastday = pc.loc[:end].index[-1]
breadth = dict(n=int(len(r)), pct_up=round(float((r>0).mean())*100,1), median=round(float(r.median())*100,2),
               eq_mean=round(float(r.mean())*100,2), last_date_in_constituents=str(lastday.date()))
# 11/13の値上がり比率
dd = pc.pct_change().loc[end].dropna() if end in pc.index else pd.Series(dtype=float)
breadth['pct_up_1113'] = round(float((dd>0).mean())*100,1) if len(dd) else None
breadth['n_1113'] = int(len(dd))
# 歴史: SMH -3%以下かつ XLP +1%以上の日、その後20日のS&P500
sm = p['SMH'].pct_change(); xp = p['XLP'].pct_change(); sp = p['^GSPC'].dropna()
cond = (sm <= -0.03) & (xp >= 0.01)
dates = cond[cond].index
ev = []; lastd = None
for dt in dates:
    if lastd is not None and (dt - lastd).days < 30: continue
    lastd = dt
    i = sp.index.get_loc(dt)
    if i+20 < len(sp): ev.append(sp.iloc[i+20]/sp.iloc[i]-1)
ev = pd.Series(ev)
out['rotation'] = dict(last_dates=last_dates, since_1006=rets, week=rets_w, day_1113=rets_d, sp500_breadth_since_1006=breadth,
    smh_down3_xlp_up1=dict(n=int(len(ev)), n_raw_days=int(cond.sum()), sp_next20_median=round(float(ev.median())*100,2), sp_next20_pct_up=round(float((ev>0).mean())*100)),
    spx_off_high=round(float(sp.iloc[-1]/sp['2026'].max()-1)*100,2), spx_high_date=str(sp['2026'].idxmax().date()),
    vix=round(float(p['^VIX'].dropna().iloc[-1]),2))
json.dump(out, open('insights/data/analysis/2026-11-16.json','w'), ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
