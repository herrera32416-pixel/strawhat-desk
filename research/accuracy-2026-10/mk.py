import pandas as pd,numpy as np,glob
H='/workspace/strawhat-desk/v1/data/history/'
def imp(a):
    a=pd.to_numeric(a,errors='coerce');return np.where(a<0,-a/(-a+100),100/(a+100))
def rep(name,q,won):
    m=~np.isnan(q)&~np.isnan(won);q,won=q[m],won[m]
    conf=np.maximum(q,1-q);pick=(q>.5)
    hit=np.where(pick,won,1-won)
    print(f"{name}: n={len(q)} hit(higher no-vig side) {hit.mean():.3f}")
    for lo,hi in((.5,.52),(.52,.55),(.55,.6),(.6,1.01)):
        s=(conf>=lo)&(conf<hi);print(f"   conf {lo:.2f}-{hi:.2f}: n={s.sum()} hit {hit[s].mean() if s.sum() else float('nan'):.3f}")
for sp,hc,ac,hs,as_ in(('nhl','home','away','home_score','away_score'),('mlb','home','away','home_score','away_score')):
    df=pd.concat(pd.read_csv(f) for f in glob.glob(H+sp+'/20*.csv'));df=df[df.status_detail.astype(str).str.startswith('Final')]
    tot=df.home_score+df.away_score
    o,u=imp(df.over_price),imp(df.under_price);q=o/(o+u);won=np.where(tot>df.total,1.0,np.where(tot<df.total,0.0,np.nan))
    rep(f'{sp.upper()} total',q,won)
    a,h=imp(df.sp_price_away),imp(df.sp_price_home);q=h/(a+h);mar=df.home_score-df.away_score+df.spread_home
    won=np.where(mar>0,1.0,np.where(mar<0,0.0,np.nan));rep(f'{sp.upper()} puck/run line (home side)',q,won)
for sp in('cfb','nfl'):
    df=pd.concat(pd.read_csv(f) for f in glob.glob(H+sp+'/20*.csv'));df=df.dropna(subset=['home_score','away_score'])
    h,a=imp(df.close_h_sp_price),imp(df.close_a_sp_price);q=h/(h+a)
    mar=df.home_score-df.away_score+df.close_spread;won=np.where(mar>0,1.0,np.where(mar<0,0.0,np.nan))
    rep(f'{sp.upper()} spread (price no-vig)',q,won)
    # FPI vs spread
    if 'fpi_home_margin' in df:
        d2=df.dropna(subset=['fpi_home_margin','close_spread'])
        e=d2.fpi_home_margin+d2.close_spread;mar=d2.home_score-d2.away_score+d2.close_spread
        ok=mar!=0;hit=((e>0)==(mar>0))[ok]
        print(f"   FPI side of spread: n={ok.sum()} hit {hit.mean():.3f}")
        for t in(1,3,5):
            s=(abs(e)>=t)&ok;print(f"     |FPI-line|>={t}: n={s.sum()} hit {((e>0)==(mar>0))[s].mean():.3f}")
