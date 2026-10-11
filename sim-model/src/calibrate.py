"""v2 step 1: walk-forward recalibration of sim output. For season S, every map is fit only on out-of-sample sim preds from seasons < S.
 - margin stretch: result ~ a*sim_margin + b ; total: total ~ a*sim_total + b (removes compression + totals bias)
 - probabilities: Normal(adj_mean, sd_resid_prior) -> P(win/cover/over), then Platt (logistic on logit) fit on prior seasons."""
import pandas as pd, numpy as np, sys
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression
def lg(p): p=np.clip(p,1e-4,1-1e-4); return np.log(p/(1-p))
def calibrate(P):
    out=[]
    seasons=sorted(P.season.unique())
    for S in seasons[1:]:
        tr=P[(P.season<S)&P.result.notna()]; te=P[P.season==S].copy()
        a,b=np.polyfit(tr.sim_margin,tr.result,1); c,d=np.polyfit(tr.sim_total,tr.total,1)
        sdm=np.std(tr.result-(a*tr.sim_margin+b)); sdt=np.std(tr.total-(c*tr.sim_total+d))
        for X in (tr,te):
            X['m2']=a*X.sim_margin+b; X['t2']=c*X.sim_total+d
            X['p_wp']=1-norm.cdf((0-X.m2)/sdm); X['p_cov']=1-norm.cdf((X.spread_line-X.m2)/sdm); X['p_ov']=1-norm.cdf((X.total_line-X.t2)/sdt)
        for raw,y in (('p_wp',tr.result>0),('p_cov',tr.result>tr.spread_line),('p_ov',tr.total>tr.total_line)):
            ok=(tr.result!=0) if raw=='p_wp' else (tr.result!=tr.spread_line) if raw=='p_cov' else (tr.total!=tr.total_line)
            m=LogisticRegression(C=1e6).fit(lg(tr[raw][ok]).values.reshape(-1,1),y[ok].astype(int))
            te[raw+'_cal']=m.predict_proba(lg(te[raw]).values.reshape(-1,1))[:,1]
        te['cal_fit']=f'{a:.2f}x+{b:.1f} / tot {c:.2f}x+{d:.1f}'
        out.append(te)
    C=pd.concat(out)
    C['sim_margin']=C.m2; C['sim_total']=C.t2; C['sim_wp']=C.p_wp_cal; C['sim_cover']=C.p_cov_cal; C['sim_over']=C.p_ov_cal
    return C
if __name__=='__main__':
    P=pd.read_parquet(sys.argv[1]); C=calibrate(P); C.to_parquet(sys.argv[2]); print(C.groupby('season').cal_fit.first())
