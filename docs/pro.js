// NBA + NHL tabs (info only). Separate from app.js; reads docs/data/nba.json and docs/data/nhl.json.
(() => {
  const P = x => x == null ? '' : (100 * x).toFixed(1) + '%';
  const D = x => x == null ? '' : ((x >= 0 ? '+' : '') + (100 * x).toFixed(1) + 'pp');
  const S = (x, d = 1) => x == null ? '' : ((x >= 0 ? '+' : '') + Number(x).toFixed(d));
  const A = a => a == null ? '' : (a > 0 ? '+' + a : '' + a);
  const rng = r => r ? `${r[0]}–${r[2]} (median ${r[1]})` : '';
  async function J(n) { const r = await fetch('data/' + n + '.json?' + Date.now()); if (!r.ok) throw new Error(n); return r.json(); }
  const sub = (id, a, b) => `<div class="subnav pro"><button data-p="${id}-m" class="on">Matchups</button><button data-p="${id}-s">Sim</button></div>`;
  function wire(el) {
    el.querySelectorAll('.subnav.pro button').forEach(b => b.onclick = () => {
      el.querySelectorAll('.subnav.pro button').forEach(x => x.classList.toggle('on', x === b));
      el.querySelectorAll('.ppanel').forEach(p => p.hidden = p.id !== b.dataset.p);
    });
  }
  function btBox(sport, bt, status) {
    if (!bt) return '';
    const rows = sport === 'nhl' ? [['ML', 'ml'], ['Puck line', 'puck_line'], ['Total', 'total']] : [['Spread', 'spread'], ['Total', 'total'], ['ML', 'ml']];
    let h = `<div class="card"><b>Backtest vs the closing line</b> (out of sample 2022-23 → 2025-26, pass criteria written before the run) · <span class="dec">${status}</span><table><tr><th>Market</th><th>Games</th><th>Log loss model / market</th><th>Δ 90% CI</th><th>Bets</th><th>Units</th><th>ROI</th><th>Pass?</th></tr>`;
    for (const [l, k] of rows) {
      const r = bt[k]; if (!r) continue; const v = (bt.verdict || {})[k] || {};
      h += `<tr><td>${l}</td><td>${r.n}</td><td>${r.ll_model} / ${r.ll_market}</td><td>${r.ll_improve_ci90 ? r.ll_improve_ci90.join(' … ') : ''}</td><td>${r.bets}${r.win_pct != null ? ' (' + P(r.win_pct) + ')' : ''}</td><td>${S(r.units, 1)}u</td><td>${r.roi != null ? S(100 * r.roi, 1) + '%' : ''}</td><td class="${v.passed ? 'ok' : 'bad'}">${v.passed ? 'yes' : 'no'}</td></tr>`;
    }
    return h + `</table><div class="small">Market = ESPN-listed pregame close (DraftKings / ESPN BET), de-vigged. Info only unless every criterion passes; see Method.</div></div>`;
  }
  function unitTable(g, labels) {
    const H = g.units[g.home], Aw = g.units[g.away];
    return `<table><tr><th>Unit (rank of 32/30; 1 = best)</th><th>${g.away} off · def</th><th>${g.home} off · def</th></tr>` +
      labels.map(([k, l]) => `<tr><td>${l}</td><td>#${Aw[k].o_rank} · #${Aw[k].d_rank}</td><td>#${H[k].o_rank} · #${H[k].d_rank}</td></tr>`).join('') +
      `<tr><td class="mut">games this season</td><td class="mut">${Aw.n_games}</td><td class="mut">${H.n_games}</td></tr></table>`;
  }
  function nhl(d) {
    const el = document.getElementById('nhl'); if (!el) return;
    if (!d) { el.innerHTML = '<div id="nhl-v1"></div><p class="note">NHL sim data not published yet.</p>'; return; }
    let h = `<div class="hl"><b>NHL · INFO ONLY</b> · market-anchored sim (de-vigged ML + total → regulation Poisson + empty net + OT/shootout), 1,000 sims per game. Never a pick.<span class="sub">updated ${d.generated_ct} · odds ${d.odds_asof || '—'} (${d.odds_file || 'none'})</span></div>`;
    h += sub('nhl');
    const games = (d.games || []).filter(g => !g.no_line);
    const labels = [['xgf60_e', '5v5 xG/60 (off = creates, def = allows)'], ['hdf60_e', '5v5 high-danger xG/60'], ['cf60_e', '5v5 shot attempts/60'], ['pp_xg', 'PP xG/game (def = PK)'], ['pp_min', 'PP time drawn (def = taken)'], ['fin', 'finishing vs xG (def = goalie/D)']];
    let m = `<div class="ppanel" id="nhl-m">`, s = `<div class="ppanel" id="nhl-s" hidden>`;
    if (!games.length) m += '<p class="note">No priced NHL games for today/tomorrow yet.</p>';
    for (const g of games) {
      const gh = g.goalies.home, ga = g.goalies.away;
      m += `<div class="card"><div class="gh"><span class="tag nhl">NHL</span> <b>${g.away} @ ${g.home}</b><span class="k">${g.start_ct}</span></div>`;
      m += `<ul class="small">${(g.mismatches.length ? g.mismatches : ['no unit gap big enough to call out (top-8 vs bottom-8)']).map(x => `<li>${x}</li>`).join('')}</ul>`;
      m += unitTable(g, labels);
      m += `<div class="small">Goalies: ${g.away} ${ga.name || '?'} (GSAx/gm ${S(ga.gsax_per_game, 2)}) · ${g.home} ${gh.name || '?'} (${S(gh.gsax_per_game, 2)}) — ${gh.note}. Rest days: ${g.away} ${g.rest.away ?? '?'}${g.rest.b2b_away ? ' (B2B)' : ''}, ${g.home} ${g.rest.home ?? '?'}${g.rest.b2b_home ? ' (B2B)' : ''}. vs similar-style foes (goals vs market): ${g.away} ${S(g.similar_style.away, 2)}, ${g.home} ${S(g.similar_style.home, 2)}. Common opponents: ${g.common_opp.n || 0} (gap ${S(g.common_opp.gap, 2)} goals, ${g.home} minus ${g.away}).</div></div>`;
      const mk = g.market, sm = g.sim, s0 = g.sim_market_only, mc = sm.mc1000;
      s += `<div class="card"><div class="gh"><span class="tag nhl">NHL</span> <b>${g.away} @ ${g.home}</b><span class="k">${g.start_ct}</span></div><table><tr><th></th><th>Market (de-vig)</th><th>Sim</th><th>Δ vs market</th><th>1,000 sims</th></tr>
        <tr><td>${g.home} win (incl. OT/SO)</td><td>${P(mk.home_win)}</td><td>${P(sm.home_win)}</td><td>${D(g.delta.home_win)}</td><td>${P(mc.home_win)}</td></tr>
        <tr><td>${g.home} −1.5</td><td class="mut">${mk.dk && mk.dk.h2h ? 'DK ML ' + A(mk.dk.h2h[0]) + '/' + A(mk.dk.h2h[1]) : ''}</td><td>${P(sm.home_m15)}</td><td>${D(g.delta.home_m15)} vs mkt-only sim ${P(s0.home_m15)}</td><td>${P(mc.home_m15)}</td></tr>
        <tr><td>Over ${mk.total}</td><td>${P(mk.over)}</td><td>${P(sm.over)}</td><td>${D(g.delta.over)}</td><td>${P(mc.over)}</td></tr></table>
        <div class="small">Expected goals ${g.away} ${sm.exp_a.toFixed(2)} – ${g.home} ${sm.exp_h.toFixed(2)} · 80% ranges: ${g.away} ${rng(mc.away_goals)}, ${g.home} ${rng(mc.home_goals)}, total ${rng(mc.total)} · most common: ${sm.top_scores.map(t => t.score + ' ' + P(t.share)).join(', ')} (${g.home}-${g.away}) · matchup lean ${S(g.lean.goal_diff, 3)} goals diff, ${S(g.lean.total, 3)} total (shrunk) · market: ${mk.src_ml}, ${mk.n_books} books</div></div>`;
    }
    for (const g of (d.games || []).filter(g => g.no_line)) m += `<div class="card small">${g.away} @ ${g.home} · ${g.start_ct} · ${g.note}</div>`;
    el.innerHTML = '<div id="nhl-v1"></div>' + h + m + '</div>' + s + '</div>' + btBox('nhl', d.backtest, d.status);
    wire(el);
  }
  function nba(d) {
    const el = document.getElementById('nba'); if (!el) return;
    if (!d) { el.innerHTML = '<p class="note">NBA data not published yet.</p>'; return; }
    let h = `<div class="hl"><b>NBA · INFO ONLY</b> · market-anchored possession sim (de-vigged spread + total), 1,000 sims per game. Never a pick.<span class="sub">updated ${d.generated_ct}${d.odds_asof ? ' · odds ' + d.odds_asof : ''}</span></div>`;
    if (d.season_note) h += `<div class="card"><b>${d.season_note}</b></div>`;
    h += sub('nba');
    const games = (d.games || []).filter(g => !g.no_line);
    const labels = [['ortg', 'pts/100 poss'], ['pace', 'pace'], ['efg', 'eFG%'], ['tov_pct', 'turnover rate'], ['orb_pct', 'off. rebound %'], ['ftr', 'FT rate'], ['tpar', '3PA rate'], ['tp_pct', '3P%'], ['paint', 'paint pts/poss']];
    let m = `<div class="ppanel" id="nba-m">`, s = `<div class="ppanel" id="nba-s" hidden>`;
    if (!games.length) { m += '<p class="note">No priced NBA games yet.</p>'; s += '<p class="note">No priced NBA games yet.</p>'; }
    for (const g of games) {
      m += `<div class="card"><div class="gh"><span class="tag nba">NBA</span> <b>${g.away} @ ${g.home}</b><span class="k">${g.start_ct}</span></div><ul class="small">${(g.mismatches.length ? g.mismatches : ['no unit gap big enough to call out']).map(x => `<li>${x}</li>`).join('')}</ul>${unitTable(g, labels)}
      <div class="small">Rest: ${g.away} ${g.rest.away ?? '?'}${g.rest.b2b_away ? ' (B2B)' : ''}, ${g.home} ${g.rest.home ?? '?'}${g.rest.b2b_home ? ' (B2B)' : ''} · vs similar-style foes (pts vs spread): ${g.away} ${S(g.similar_style.away)}, ${g.home} ${S(g.similar_style.home)} · common opponents ${g.common_opp.n || 0} (gap ${S(g.common_opp.gap)})</div></div>`;
      const mk = g.market, sm = g.sim;
      s += `<div class="card"><div class="gh"><span class="tag nba">NBA</span> <b>${g.away} @ ${g.home}</b><span class="k">${g.start_ct}</span></div><table><tr><th></th><th>Market (de-vig)</th><th>Sim (1,000)</th><th>Δ</th></tr>
      <tr><td>${g.home} ${A(mk.spread_home)} cover</td><td>${P(mk.cover)}</td><td>${P(sm.p_home_cover)}</td><td>${D(g.delta.cover)}</td></tr>
      <tr><td>Over ${mk.total}</td><td>${P(mk.over)}</td><td>${P(sm.p_over)}</td><td>${D(g.delta.over)}</td></tr>
      <tr><td>${g.home} win</td><td class="mut">from spread</td><td>${P(sm.p_home_win)}</td><td>${D(g.delta.home_win)} vs mkt-only sim</td></tr></table>
      <div class="small">80% ranges: ${g.away} ${rng(sm.away_pts)}, ${g.home} ${rng(sm.home_pts)}, margin ${rng(sm.margin)}, total ${rng(sm.total)} · matchup lean ${S(g.lean.spread_pts, 2)} pts spread, ${S(g.lean.total_pts, 2)} total (shrunk)</div></div>`;
    }
    el.innerHTML = h + m + '</div>' + s + '</div>' + btBox('nba', d.backtest, d.status);
    wire(el);
  }
  J('nhl').then(nhl).catch(() => nhl(null));
  J('nba').then(nba).catch(() => nba(null));
})();
