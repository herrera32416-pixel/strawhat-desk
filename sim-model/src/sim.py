"""Drive-level Monte Carlo football game simulator (vectorized)."""
import numpy as np
def sim_game(rng, n_sims, drives_mu, p_home, p_away, game_sd, ot_home_p, ties=True, pts_td=(7,6,8), pts_td_p=(.94,.04,.02), opp_td_share=0.10):
    """p_*: dict with td, fg, tov drive probabilities (rest = no score).
    game_sd: per-sim per-team logit noise (captures 'day' variance not in ratings)."""
    out={}
    N=np.clip(np.round(rng.normal(drives_mu,1.1,n_sims)),6,22).astype(int)
    scores=[]
    for side,p in (('h',p_home),('a',p_away)):
        nd=N+rng.integers(-1,1,n_sims)*(side=='a')  # alternating possessions; away gets 0/-1
        maxd=int(nd.max())
        shock=rng.normal(0,game_sd,n_sims)[:,None]
        lt=np.log(p['td']/(1-p['td']))+shock; ptd=1/(1+np.exp(-lt))
        lf=np.log(p['fg']/(1-p['fg']))+0.5*shock; pfg=1/(1+np.exp(-lf))
        pfg=np.minimum(pfg,0.97-ptd)
        u=rng.random((n_sims,maxd)); mask=np.arange(maxd)[None,:]<nd[:,None]
        td=(u<ptd)&mask; fg=(u>=ptd)&(u<ptd+pfg)&mask
        tov=(u>=ptd+pfg)&(u<ptd+pfg+p['tov'])&mask
        tdpts=rng.choice(pts_td,size=(n_sims,maxd),p=pts_td_p)
        s=(td*tdpts).sum(1)+3*fg.sum(1)
        defs=(tov&(rng.random((n_sims,maxd))<opp_td_share)).sum(1)*7
        scores.append((s,defs))
    h=scores[0][0]+scores[1][1]; a=scores[1][0]+scores[0][1]
    tie=h==a
    r=rng.random(n_sims)
    if ties:  # OT: ~ 3 pts to winner, small share stays tied (NFL)
        win=r<ot_home_p; stay=rng.random(n_sims)<0.08
        h=h+np.where(tie&~stay&win,3,0); a=a+np.where(tie&~stay&~win,3,0)
    else:
        h=h+np.where(tie&(r<ot_home_p),7,0); a=a+np.where(tie&(r>=ot_home_p),7,0)
    return h,a
