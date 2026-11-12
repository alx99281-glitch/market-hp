"""分析の視点 2026-11-13 号の検証スクリプト。
データ: /tmp/market-data/daily.parquet (Actions取得), daily-review/data/prices.parquet (S&P500採用銘柄)
出力: insights/data/analysis/2026-11-13.json
"""
import json
import numpy as np
import pandas as pd

D = pd.read_parquet('/tmp/market-data/daily.parquet')
D['date'] = pd.to_datetime(D['date']).dt.tz_localize(None).dt.normalize()
SP = pd.read_parquet('daily-review/data/prices.parquet')
SP['date'] = pd.to_datetime(SP['date']).dt.tz_localize(None).dt.normalize()
out = {}


def px(t, col='close', src=D):
    s = src[src.ticker == t].set_index('date')[col].sort_index()
    return s[~s.index.duplicated()]


def r(x, n=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)

# ---------- 1. NVDA: 寄り付きの大幅ギャップダウンから半分以上戻した日 ----------
nv = D[D.ticker == 'NVDA'].set_index('date').sort_index()
last = nv.index[-1]
prev_close = nv.close.iloc[-2]
o, h, l, c = nv.loc[last, ['open', 'high', 'low', 'close']]
peak = nv.close[nv.index >= '2026-01-01'].max()
peak_d = nv.close[nv.index >= '2026-01-01'].idxmax()
out['nvda_day'] = dict(date=str(last.date()), prev_close=r(prev_close), open=r(o), low=r(l), close=r(c),
                       gap_pct=r((o / prev_close - 1) * 100), low_pct=r((l / prev_close - 1) * 100),
                       close_pct=r((c / prev_close - 1) * 100),
                       recovery_from_low=r((c - l) / (prev_close - l)),
                       peak_2026=r(peak), peak_date=str(peak_d.date()), dd_from_peak=r((c / peak - 1) * 100),
                       chg_since_1106=r((c / nv.close.loc['2026-11-06'] - 1) * 100))

# イベント: S&P500採用銘柄(約3年)で、安値が前日終値比-8%以下まで売られた日
spy = px('SPY')
rows = []
for t, g in SP.groupby('ticker'):
    g = g.sort_values('date').set_index('date')
    g = g[~g.index.duplicated()]
    pc = g.close.shift(1)
    lowp = g.low / pc - 1
    idx = np.where(lowp <= -0.08)[0]
    last_used = -999
    for i in idx:
        if i - last_used < 20:  # 同一銘柄20営業日内の重複を除外
            continue
        if i + 20 >= len(g):
            continue
        last_used = i
        d = g.index[i]
        rec = (g.close.iloc[i] - g.low.iloc[i]) / (pc.iloc[i] - g.low.iloc[i])
        f5 = g.close.iloc[i + 5] / g.close.iloc[i] - 1
        f20 = g.close.iloc[i + 20] / g.close.iloc[i] - 1
        if d in spy.index:
            j = spy.index.get_loc(d)
            s5 = spy.iloc[j + 5] / spy.iloc[j] - 1 if j + 5 < len(spy) else np.nan
            s20 = spy.iloc[j + 20] / spy.iloc[j] - 1 if j + 20 < len(spy) else np.nan
        else:
            s5 = s20 = np.nan
        rows.append(dict(t=t, d=d, low=lowp.iloc[i], rec=rec, x5=f5 - s5, x20=f20 - s20))
ev = pd.DataFrame(rows).dropna()


def summ(df):
    return dict(n=int(len(df)), x5_med=r(df.x5.median() * 100), x20_med=r(df.x20.median() * 100),
                x20_pos=r((df.x20 > 0).mean() * 100, 0), x20_mean=r(df.x20.mean() * 100))

out['gap_events'] = dict(
    period=f"{SP.date.min().date()}〜{SP.date.max().date()}",
    all=summ(ev),
    rec_ge_half=summ(ev[ev.rec >= 0.5]),
    rec_lt_quarter=summ(ev[ev.rec < 0.25]),
    rec_25_50=summ(ev[(ev.rec >= 0.25) & (ev.rec < 0.5)]),
    big_low_rec_half=summ(ev[(ev.low <= -0.12) & (ev.rec >= 0.5)]),
)
# 大型株(直近の売買代金上位100)に限定
SP['dv'] = SP.close * SP.volume
top = SP[SP.date >= SP.date.max() - pd.Timedelta(days=90)].groupby('ticker').dv.mean().nlargest(100).index
evb = ev[ev.t.isin(top)]
out['gap_events']['large_rec_ge_half'] = summ(evb[evb.rec >= 0.5])
out['gap_events']['large_rec_lt_half'] = summ(evb[evb.rec < 0.5])

# ---------- 2. AI半導体の分岐と日本の関連株 ----------
names = ['NVDA', 'AMD', '^SOX', 'SMH', 'TSM', 'MU', 'ARM', 'CRWV', 'NBIS', 'SNDK', '6857.T', '8035.T', '285A.T', '9984.T', '4062.T', '000660.KS', '005930.KS', '2330.TW']
ch = {}
for t in names:
    s = px(t)
    try:
        ch[t] = dict(d1=r((s.iloc[-1] / s.iloc[-2] - 1) * 100), since_1106=r((s.iloc[-1] / s.loc['2026-11-06'] - 1) * 100), last=str(s.index[-1].date()))
    except KeyError:
        pass
avgo = px('AVGO', src=SP)
ch['AVGO'] = dict(d1=None, since_1106_to_1111=r((avgo.iloc[-1] / avgo.loc['2026-11-06'] - 1) * 100), last=str(avgo.index[-1].date()))
out['chip_moves'] = ch

# 東京(t日) と 直前の米国営業日(t-1)の対応
def jp_us(jp, usl, window=250):
    j = px(jp).pct_change()
    res = {}
    for u in usl:
        us = px(u, src=SP if u == 'AVGO' else D).pct_change()
        us_shift = us.copy()
        # 東京の各営業日に、それより前の最後の米国営業日を対応させる
        L = j.rename('jp').reset_index(); L['date'] = L['date'].astype('datetime64[ns]')
        R = us_shift.rename('us').reset_index(); R['date'] = R['date'].astype('datetime64[ns]')
        aligned = pd.merge_asof(L, R, on='date', direction='backward', allow_exact_matches=False).dropna()
        aligned = aligned.tail(window)
        cc = aligned.jp.corr(aligned.us)
        beta = np.cov(aligned.jp, aligned.us)[0, 1] / aligned.us.var()
        res[u] = dict(corr=r(cc), beta=r(beta), n=int(len(aligned)))
    return res

out['jp_link'] = {jp: jp_us(jp, ['NVDA', 'AMD', 'AVGO', '^SOX']) for jp in ['6857.T', '8035.T', '285A.T', '9984.T']}
a = px('6857.T'); b = px('8035.T')
ratio = (a / b).dropna()
out['adv_tel_ratio'] = dict(last=r(ratio.iloc[-1], 3), at_1106=r(ratio.loc['2026-11-06'], 3),
                            pct_rank_1y=r((ratio.tail(250) < ratio.iloc[-1]).mean() * 100, 0),
                            max_1y=r(ratio.tail(250).max(), 3), max_date=str(ratio.tail(250).idxmax().date()))
# NVDAとAMDの相対(10/6比、11/6比)
nvamd = (px('NVDA') / px('AMD')).dropna()
out['nvda_amd'] = dict(chg_since_1106=r((nvamd.iloc[-1] / nvamd.loc['2026-11-06'] - 1) * 100),
                       chg_since_1006=r((nvamd.iloc[-1] / nvamd.loc['2026-10-06'] - 1) * 100),
                       corr_60d=r(px('NVDA').pct_change().tail(60).corr(px('AMD').pct_change().tail(60))),
                       corr_250d=r(px('NVDA').pct_change().tail(250).corr(px('AMD').pct_change().tail(250))))
# 日次でNVDAが-3%以下かつAMDが+3%以上だった日(2000年以降)
nr = px('NVDA').pct_change(); ar = px('AMD').pct_change()
both = pd.concat([nr, ar], axis=1, keys=['n', 'a']).dropna()
split = both[(both.n <= -0.03) & (both.a >= 0.03)]
out['nvda_amd_split_days'] = dict(n=int(len(split)), dates=[str(x.date()) for x in split.index[-8:]])

# ---------- 3. 10年金利5.1%とクロスアセット ----------
tnx = px('^TNX'); fvx = px('^FVX'); irx = px('^IRX'); tyx = px('^TYX')
out['rates'] = dict(tnx=r(tnx.iloc[-1], 3), tnx_d1_bp=r((tnx.iloc[-1] - tnx.iloc[-2]) * 100, 1),
                    tnx_3d_bp=r((tnx.iloc[-1] - tnx.loc['2026-11-09']) * 100, 1),
                    fvx=r(fvx.iloc[-1], 3), fvx_d1_bp=r((fvx.iloc[-1] - fvx.iloc[-2]) * 100, 1),
                    fvx_3d_bp=r((fvx.iloc[-1] - fvx.loc['2026-11-09']) * 100, 1),
                    irx=r(irx.iloc[-1], 3), irx_3d_bp=r((irx.iloc[-1] - irx.loc['2026-11-09']) * 100, 1),
                    tyx=r(tyx.iloc[-1], 3),
                    tnx_max_2026=r(tnx[tnx.index >= '2026-01-01'].max(), 3), tnx_max_date=str(tnx[tnx.index >= '2026-01-01'].idxmax().date()),
                    tnx_close_rank_since2007=None)
since07 = tnx[tnx.index >= '2007-08-01']
higher = since07[since07 > tnx.iloc[-1]]
out['rates']['days_higher_since_2007_08'] = int(len(higher))
out['rates']['last_higher_close'] = str(higher.index[-1].date()) if len(higher) else None
dtnx = tnx.diff() * 100


def sens(asset, window, lagged=False):
    a = px(asset).pct_change() * 100
    df = pd.concat([a, dtnx], axis=1, keys=['a', 'y']).dropna()
    df = df.tail(window)
    beta = np.cov(df.a, df.y)[0, 1] / df.y.var() * 10
    return dict(corr=r(df.a.corr(df.y)), beta_per10bp=r(beta), n=int(len(df)))

cross = {}
for asset in ['GC=F', 'BTC-USD', 'JPY=X', 'DX-Y.NYB', 'NDX_', 'IWM', 'TLT']:
    t = '^NDX' if asset == 'NDX_' else asset
    cross[t] = {w: sens(t, w) for w in (20, 60, 250)}
out['cross_sens'] = cross
lastd = {}
for t in ['GC=F', 'BTC-USD', 'JPY=X', 'DX-Y.NYB', 'CL=F', '^VIX', 'TLT', 'HYG', 'LQD']:
    s = px(t)
    lastd[t] = dict(last=r(s.iloc[-1], 3), d1=r((s.iloc[-1] / s.iloc[-2] - 1) * 100), since_1109=r((s.iloc[-1] / s.loc['2026-11-09'] - 1) * 100))
out['cross_moves'] = lastd
dxy = px('DX-Y.NYB')
hi = dxy[dxy > dxy.iloc[-1]]
out['dxy_last_higher'] = str(hi.index[-1].date()) if len(hi) else None
gold = px('GC=F')
g3 = gold.pct_change(3) * 100
out['gold_3d'] = dict(chg=r(g3.iloc[-1]), pct_rank_since2000=r((g3.dropna() < g3.iloc[-1]).mean() * 100, 1),
                      peak_2026=r(gold[gold.index >= '2026-01-01'].max(), 1), peak_date=str(gold[gold.index >= '2026-01-01'].idxmax().date()),
                      dd=r((gold.iloc[-1] / gold[gold.index >= '2026-01-01'].max() - 1) * 100))
jpy = px('JPY=X')
out['usdjpy'] = dict(last=r(jpy.iloc[-1], 3), max_2026=r(jpy[jpy.index >= '2026-01-01'].max(), 3),
                     max_date=str(jpy[jpy.index >= '2026-01-01'].idxmax().date()),
                     days_ge_160_2026=int((jpy[jpy.index >= '2026-01-01'] >= 160).sum()))

# ---------- 4. 金利上昇日の小型株・均等加重 ----------
rel = {}
for t in ['IWM', 'RSP', 'KRE', 'XLU', 'XLRE']:
    a = px(t).pct_change() * 100
    s = px('SPY').pct_change() * 100
    df = pd.concat([a - s, dtnx, tnx], axis=1, keys=['rel', 'dy', 'lvl']).dropna()
    df['lvl_prev'] = df.lvl.shift(1)
    big = df[df.dy >= 8]
    res = dict(today_rel=r(df.rel.iloc[-1]),
               up8_all=dict(n=int(len(big)), med=r(big.rel.median()), neg=r((big.rel < 0).mean() * 100, 0)),
               up8_hi=dict(n=int(len(big[big.lvl_prev >= 4.5])), med=r(big[big.lvl_prev >= 4.5].rel.median()), neg=r((big[big.lvl_prev >= 4.5].rel < 0).mean() * 100, 0)),
               up8_lo=dict(n=int(len(big[big.lvl_prev < 4.5])), med=r(big[big.lvl_prev < 4.5].rel.median()), neg=r((big[big.lvl_prev < 4.5].rel < 0).mean() * 100, 0)))
    for w in (60, 250):
        x = df.tail(w)
        res[f'beta{w}_per10bp'] = r(np.cov(x.rel, x.dy)[0, 1] / x.dy.var() * 10, 3)
        res[f'corr{w}'] = r(x.rel.corr(x.dy))
    # 2022年以降
    x = df[df.index >= '2022-01-01']
    res['beta_2022_per10bp'] = r(np.cov(x.rel, x.dy)[0, 1] / x.dy.var() * 10, 3)
    rel[t] = res
out['rate_rel'] = rel
iwm = px('IWM'); spyc = px('SPY')
rr = (iwm / spyc).dropna()
out['iwm_spy'] = dict(chg_since_1109=r((rr.iloc[-1] / rr.loc['2026-11-09'] - 1) * 100),
                      chg_1m=r((rr.iloc[-1] / rr.iloc[-22] - 1) * 100),
                      iwm_ytd=r((iwm.iloc[-1] / iwm[iwm.index < '2026-01-01'].iloc[-1] - 1) * 100),
                      spy_ytd=r((spyc.iloc[-1] / spyc[spyc.index < '2026-01-01'].iloc[-1] - 1) * 100))
# 日本: 東京の翌日 vs 米10年金利変化(東京t日 vs 米t-1日)
jp_rate = {}
for t in ['EWJ', 'DXJ']:
    a = px(t).pct_change() * 100
    s = px('SPY').pct_change() * 100
    df = pd.concat([a - s, dtnx], axis=1, keys=['rel', 'dy']).dropna().tail(250)
    jp_rate[t] = dict(beta250_per10bp=r(np.cov(df.rel, df.dy)[0, 1] / df.dy.var() * 10, 3), corr=r(df.rel.corr(df.dy)), today_rel=r(df.rel.iloc[-1]))
out['jp_rate_rel'] = jp_rate

# NKD vs 東京終値(報道値)
nkd = px('NKD=F')
out['nkd'] = dict(last=r(nkd.iloc[-1], 0), date=str(nkd.index[-1].date()), tokyo_close_1112_reported=60819.36,
                  gap_vs_tokyo=r((nkd.iloc[-1] / 60819.36 - 1) * 100))

with open('insights/data/analysis/2026-11-13.json', 'w') as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))

# ---------- 追加: 大型株で安値-12%以下から半分以上戻した例、アドバンテストの対NVDA相関の推移 ----------
evb2 = evb[(evb.low <= -0.12) & (evb.rec >= 0.5)]
out['gap_events']['large_low12_rec_half'] = summ(evb2)
out['gap_events']['large_low12_rec_half_list'] = [dict(t=x.t, d=str(x.d.date()), low=r(x.low * 100), rec=r(x.rec), x20=r(x.x20 * 100)) for x in evb2.itertuples()]
roll = {}
j = px('6857.T').pct_change()
for u in ['NVDA', 'AMD', '^SOX']:
    us = px(u).pct_change()
    L = j.rename('jp').reset_index(); L['date'] = L['date'].astype('datetime64[ns]')
    R = us.rename('us').reset_index(); R['date'] = R['date'].astype('datetime64[ns]')
    al = pd.merge_asof(L, R, on='date', direction='backward', allow_exact_matches=False).dropna().set_index('date')
    roll[u] = {str(y): r(al[al.index.year == y].jp.corr(al[al.index.year == y].us)) for y in range(2021, 2027)}
out['adv_corr_by_year'] = roll
with open('insights/data/analysis/2026-11-13.json', 'w') as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print(json.dumps({k: out[k] for k in ['adv_corr_by_year']}, ensure_ascii=False), json.dumps(out['gap_events']['large_low12_rec_half'], ensure_ascii=False), json.dumps(out['gap_events']['large_low12_rec_half_list'], ensure_ascii=False))
