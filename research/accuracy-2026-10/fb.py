import pandas as pd,numpy as np,glob
from scipy.optimize import minimize
from scipy.stats import norm
H='/workspace/strawhat-desk/v1/data/history/'
lg=lambda p:np.log(np.clip(p,1e-4,1-1e-4)/(1-np.clip(p,1e-4,1-1e-4)));sg=lambda x:1/(1+np.exp(-x))
def imp(a):
    a=pd.to_numeric(a,errors='coerce');return np.where(a<0,-a/(-a+100),100/(a+100))
def wf(df,feats,calib=False,label=''):
    df=df.dropna(subset=['y','q']+feats).copy();df=df[(df.q>0.001)&(df.q<.999)]
    R=[]
    for s in sorted(df.season.unique())[1:]:
        tr,te=df[df.season<s],df[df.season==s]
        if len(tr)<200 or len(te)<50: continue
        def P(d,t):
            z=(1+t[0])*lg(d.q)+t[1] if calib else lg(d.q);k=2 if calib else 0
            for i,f in enumerate(feats): z=z+t[k+i]*d[f]
            return sg(z)
        n=(2 if calib else 0)+len(feats)
        t=minimize(lambda t:-np.mean(tr.y*np.log(P(tr,t))+(1-tr.y)*np.log(1-P(tr,t)))+1e-3*np.sum(t**2),np.zeros(n)).x
        R.append(pd.DataFrame({'y':te.y,'q':te.q,'p':P(te,t),'s':s,'t':str(np.round(t,3))}))
    r=pd.concat(R)
    m=lambda c:(-np.mean(r.y*np.log(r[c])+(1-r.y)*np.log(1-r[c])),np.mean((r[c]-r.y)**2),np.mean((r[c]>.5)==(r.y==1)))
    a,b=m('q'),m('p');sb=sum(np.mean((g.p-g.y)**2)<np.mean((g.q-g.y)**2) for _,g in r.groupby('s'))
    keep=b[1]<a[1] and b[2]>a[2] and b[0]<a[0]
    print(f"{label:42s} n={len(r):5d} dLL={1000*(b[0]-a[0]):+.2f} dBrier={1000*(b[1]-a[1]):+.2f} hit {a[2]:.3f}->{b[2]:.3f} seasons {sb}/{r.s.nunique()} last-fit {r.t.iloc[-1]} {'KEEP' if keep else ''}")
    return r
for sp in('cfb','nfl'):
    df=pd.concat(pd.read_csv(f) for f in glob.glob(H+sp+'/20*.csv'));df=df.dropna(subset=['home_score','away_score'])
    if sp=='nfl': df=df[df.game_type.isin(['REG','WC','DIV','CON','SB'])] if 'game_type' in df else df
    h,a=imp(df.close_h_ml),imp(df.close_a_ml);ml=df.assign(q=h/(h+a),y=(df.home_score>df.away_score).astype(float))
    ml=ml[df.home_score!=df.away_score]
    print(f'== {sp.upper()} ML')
    wf(ml,[],True,'fav-longshot calibration')
    ml['hd']=((ml.q<.5)&(ml.neutral!=1)).astype(float) if 'neutral' in ml else (ml.q<.5).astype(float)
    wf(ml,['hd'],label='home-dog flag')
    if 'fpi_home_margin' in ml:
        ml['fz']=ml.fpi_home_margin+ml.close_spread
        wf(ml,['fz'],label='FPI minus spread')
    # spreads
    h,a=imp(df.close_h_sp_price),imp(df.close_a_sp_price);mar=df.home_score-df.away_score+df.close_spread
    s=df.assign(q=h/(h+a),y=np.where(mar>0,1.0,np.where(mar<0,0.0,np.nan)))
    sp_=s.close_spread
    s['k3']=np.sign(-sp_)*(sp_.abs().isin([2.5,3.5,6.5,7.5])).astype(float)*np.where(sp_.abs().isin([2.5,6.5]),1,-1)
    s['hfav']=(sp_<0).astype(float)
    s['big']=(sp_.abs()>=21).astype(float)*np.sign(-sp_)
    s['fz']=(s.fpi_home_margin+s.close_spread) if 'fpi_home_margin' in s else np.nan
    print(f'== {sp.upper()} spread (base no-vig price)')
    for f in ['k3','hfav','big','fz']:
        try: wf(s,[f],label=f)
        except Exception as e: print(f,e)
    wf(s,[],True,'calibration')
    o,u=imp(df.get('close_over_price',pd.Series(np.nan,index=df.index))),None
    tot=df.home_score+df.away_score
    t=df.assign(q=0.5,y=np.where(tot>df.close_total,1.0,np.where(tot<df.close_total,0.0,np.nan)))
    t['q']=0.5+1e-6
    t['op']=df.open_total-df.close_total if 'open_total' in df else np.nan
    print(f'== {sp.upper()} totals (base 50%)  over rate {np.nanmean(t.y):.3f}')
    wf(t,['op'],label='total moved down open->close')
    s['mv']=s.close_spread-s.open_spread
    wf(s,['mv'],label='spread line move (open->close)')
