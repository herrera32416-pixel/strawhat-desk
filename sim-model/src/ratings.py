"""Sequential, opponent-adjusted, recency-weighted, Bayesian-shrunk team ratings.
State only ever contains games strictly before the week being predicted (walk-forward)."""
import numpy as np, pandas as pd
from collections import defaultdict
class Ratings:
    def __init__(self, metrics, decay=0.92, prior_k=4.0, carry=0.6):
        self.m=metrics; self.decay=decay; self.k=prior_k; self.carry=carry
        self.sw=defaultdict(float)            # (team,side) -> sum weights
        self.sx=defaultdict(lambda: defaultdict(float))
        self.lg={x:0.0 for x in metrics}; self.lg_n=0
    def get(self, team, side):
        w=self.sw[(team,side)]; s=self.sx[(team,side)]
        return {x:(s[x]+self.k*self.lg[x])/(w+self.k) for x in self.m}, w
    def new_season(self):
        for key in list(self.sw):            # regress toward mean between seasons
            self.sw[key]*=self.carry*0.5
            for x in self.m: self.sx[key][x]*=self.carry*0.5
    def update_week(self, obs):
        """obs: DataFrame with team, opp, and off_<m>, def_<m> (what the defense allowed) for each metric."""
        pre={}
        for _,r in obs.iterrows():
            pre[(r.team,'off')]=self.get(r.team,'off')[0]; pre[(r.team,'def')]=self.get(r.team,'def')[0]
        for key in list(self.sw):
            self.sw[key]*=self.decay
            for x in self.m: self.sx[key][x]*=self.decay
        for _,r in obs.iterrows():
            od=pre.get((r.opp,'def')); oo=pre.get((r.opp,'off'))
            for x in self.m:
                # opponent adjustment: remove what opp defense usually allows above league
                ao=r['off_'+x]-(od[x]-self.lg[x]); ad=r['def_'+x]-(oo[x]-self.lg[x])
                self.sx[(r.team,'off')][x]+=ao; self.sx[(r.team,'def')][x]+=ad
            self.sw[(r.team,'off')]+=1; self.sw[(r.team,'def')]+=1
        # league means (running, slow)
        n=len(obs)
        for x in self.m:
            mu=obs['off_'+x].mean()
            self.lg[x]=mu if self.lg_n==0 else 0.97*self.lg[x]+0.03*mu
        self.lg_n+=n
