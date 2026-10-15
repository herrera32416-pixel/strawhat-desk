import pandas as pd,numpy as np,glob
from scipy.optimize import minimize
D='/workspace/strawhat-desk/research/trends-2026-10/data/';H='/workspace/strawhat-desk/v1/data/history/'
lg=lambda p:np.log(np.clip(p,1e-4,1-1e-4)/(1-np.clip(p,1e-4,1-1e-4)));sg=lambda x:1/(1+np.exp(-x))
def imp(a):
    a=pd.to_numeric(a,errors='coerce');return pd.Series(np.where(a<0,-a/(-a+100),100/(a+100)),index=a.index)
def wf(df,feats,calib=False,label=''):
    df=df.dropna(subset=['y','q']+feats).copy();df=df[(df.q>0)&(df.q<1)]
    ss=sorted(df.season.unique());R=[]
    for s in ss[1:]:
        tr,te=df[df.season<s],df[df.season==s]
        if len(tr)<300 or len(te)<100: continue
        def P(d,t):
            z=(1+t[0])*lg(d.q)+t[1] if calib else lg(d.q)
            k=2 if calib else 0
            for i,f in enumerate(feats): z=z+t[k+i]*d[f]
            return sg(z)
        n=(2 if calib else 0)+len(feats)
        f=lambda t:-np.mean(tr.y*np.log(P(tr,t))+(1-tr.y)*np.log(1-P(tr,t)))+1e-3*np.sum(np.square(t))
        t=minimize(f,np.zeros(n)).x;R.append(pd.DataFrame({'y':te.y,'q':te.q,'p':P(te,t),'s':s}))
    if not R: return
    r=pd.concat(R)
    def m(c):
        p=r[c];return -np.mean(r.y*np.log(p)+(1-r.y)*np.log(1-p)),np.mean((p-r.y)**2),np.mean((p>.5)==(r.y==1))
    a,b=m('q'),m('p');seas=sum(1 for s,g in r.groupby('s') if np.mean((g.p-g.y)**2)<np.mean((g.q-g.y)**2))
    keep=b[0]<a[0] and b[1]<a[1] and b[2]>a[2]
    print(f"{label:38s} n={len(r):5d} dLL={1000*(b[0]-a[0]):+.2f} dBrier={1000*(b[1]-a[1]):+.2f} hit {a[2]:.3f}->{b[2]:.3f} seasons better {seas}/{r.s.nunique()} {'KEEP?' if keep else ''}")
# NHL features
nhl=pd.read_csv(D+'nhl_features.csv')
print('== NHL ML (base = closing no-vig)')
for f in ['n7','rest','b2b','b2b_h','b2b_a','gw3','gw7','gb2b','ghot','gqual','gshare','backup_h','form','split','split_h','road','tz','dist']:
    if f in nhl: wf(nhl,[f],label=f)
wf(nhl,[],calib=True,label='calibration a+b·logit(q)')
mp=pd.read_csv(D+'nhl_model_preds.csv');x=nhl.drop(columns=['m']).merge(mp,on=['date','home','away']);x['xg']=lg(x.m)-lg(x.q)
wf(x,['xg'],label='xG model gap (5v5/score-adj proxy)')
# line movement: history csvs
def hist(sp):
    df=pd.concat(pd.read_csv(f) for f in glob.glob(H+sp+'/20*.csv'));return df
for sp in('nhl','mlb'):
    df=hist(sp);df=df[df.status_detail.astype(str).str.startswith('Final')].copy()
    hc,ac=imp(df.ml_home_close),imp(df.ml_away_close);ho,ao=imp(df.ml_home_open),imp(df.ml_away_open)
    df['q']=hc/(hc+ac);qo=ho/(ho+ao);df['mv']=lg(df.q)-lg(qo);df['y']=(df.home_score>df.away_score).astype(float)
    df['books']=df.odds_providers_n
    print(f'== {sp.upper()} ML movement (open->close), n with open={qo.notna().sum()}')
    wf(df,['mv'],label='line movement (close-open)')
    wf(df,[],calib=True,label='calibration (fav-longshot)')
    mvd=df.dropna(subset=['mv']);mvd=mvd[mvd.mv.abs()>lg(0.52)-lg(0.5)]
    hit=((mvd.mv>0)==(mvd.y==1)).mean();print(f'   bet WITH movement (>~2pp): n={len(mvd)} hit {hit:.3f}; fav hit same games {((mvd.q>.5)==(mvd.y==1)).mean():.3f}')
    o,u=imp(df.over_price),imp(df.under_price);df2=df.assign(q=o/(o+u),y=np.where(df.home_score+df.away_score>df.total,1.0,np.where(df.home_score+df.away_score<df.total,0.0,np.nan)))
    wf(df2,[],calib=True,label='totals calibration')
# MLB/NFL totals features
mlb=pd.read_csv(D+'mlb_features.csv')
print('== MLB ML');[wf(mlb,[f],label=f) for f in ['platoon','sp_rest','pen3','ump_runs','dan','tzc']]
t=mlb.rename(columns={'q':'qq','y':'yy'}).assign(q=lambda d:d.q_over,y=lambda d:d.y_over)
print('== MLB totals');[wf(t,[f],label=f) for f in ['ump_runs','temp','wind_out','pen3_sum']]
nfl=pd.read_csv(D+'nfl_features.csv');t=nfl.drop(columns=['q','y']).rename(columns={'q_over':'q','y_over':'y'})
print('== NFL totals');[wf(t,[f],label=f) for f in ['wind','cold']]
