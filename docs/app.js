const $ = (s, el = document) => el.querySelector(s);
const pct = x => x == null ? '' : (100 * x).toFixed(1) + '%';
const am = a => a == null ? '' : (a > 0 ? '+' + a : '' + a);
const sgn = x => x == null ? '' : ((x >= 0 ? '+' : '') + (100 * x).toFixed(1));
const ln = (x, signed = true) => x == null ? '' : (signed && x > 0 ? '+' + x : '' + x);
async function J(n) { const r = await fetch('data/' + n + '.json?' + Date.now()); return r.json(); }
function tab(id) {
  id = id.split(':')[0];
  document.querySelectorAll('nav button').forEach(b => b.classList.toggle('on', b.dataset.t === id));
  document.querySelectorAll('section.tab').forEach(s => s.hidden = s.id !== id);
  if (location.hash.slice(1).split(':')[0] !== id) location.hash = id;
}
function head(meta, key) {
  const h = meta.headline[key] || {};
  let s = `<div class="hl"><b>${h.record || '0-0-0'}</b> · ${h.units >= 0 ? '+' : ''}${(h.units || 0).toFixed(2)}u ($${(h.dollars || 0).toFixed(0)}) · ${h.open || 0} open${h.void ? ' · ' + h.void + ' void' : ''}`;
  return s + `<span class="sub">1u = $20 · updated ${meta.generated_ct}</span></div>`;
}
function recheckPass(r) {
  let h = `<b>Pre-kick recheck ${r.ran_ct}</b> · ${Object.entries(r.sports || {}).map(([k, v]) => k.toUpperCase() + ': ' + v).join(' · ') || 'no odds pull'} · ledger VOIDs: ${r.ledger_voided || 0}`;
  const B = r.board_changes || [], P = r.props_changes || [];
  for (const c of B) h += `<br>${c.action === 'DROPPED' ? '❌' : '✓'} ${c.pick} ${c.market} ${c.line_9am != null ? ln(c.line_9am) : ''} ${am(c.price_9am)} (EV ${sgn(c.ev_9am)}%) → ${c.line_now != null ? ln(c.line_now) : ''} ${am(c.price_now)} (EV ${sgn(c.ev_now)}%): <b>${c.action}</b> – ${c.reason}`;
  for (const c of P) h += `<br>❌ prop VOID: ${c.player} ${c.market} ${c.side} – player now ${c.status}`;
  if (!B.length && !P.length) h += '<br>No changes: all picks and props held.';
  return h;
}
function recheckBox(m) {
  const ps = (m.recheck_passes && m.recheck_passes.length) ? m.recheck_passes : (m.recheck && m.recheck.ran_ct ? [m.recheck] : []);
  if (!ps.length) return '';
  return `<div class="note warn">${ps.map(recheckPass).join('<hr>')}</div>`;
}
function splitCards(meta) {
  const c = k => { const h = meta.headline[k] || {}; return `<div><div class="cap">${h.label || k}</div><div class="hl"><b>${h.record || '0-0-0'}</b> · ${h.units >= 0 ? '+' : ''}${(h.units || 0).toFixed(2)}u ($${(h.dollars || 0).toFixed(0)}) · ${h.open || 0} open${h.void ? ' · ' + h.void + ' void' : ''}</div></div>`; };
  return meta.headline.official ? `<div class="hls">${c('official')}${c('research')}</div>` : '';
}
function expLine(e) { return e && e.n ? `Expected wins on ${e.n} settled: model ${e.exp_w_model} · market ${e.exp_w_market} · actual <b>${e.actual_w}</b>` : 'Expected wins: none settled yet'; }
function bestPer(sides) { const b = {}; for (const s of sides) if (!b[s.side] || s.ev > b[s.side].ev) b[s.side] = s; return b; }
function renderBoard(d) {
  const el = $('#board'); const m = d.meta;
  let h = head(m, 'board') + `<p class="note">Odds as of: NFL ${m.odds_asof.nfl || '—'} · CFB ${m.odds_asof.cfb || '—'}. Model % = KEYS fair (consensus of other books incl. Pinnacle, priced through historical margin/total distributions) at the DK/Bovada line. PICK only if EV ≥ 3% at a real DK/Bovada price, and never on a spread/total when the game's |spread| ≥ 30. <b>ML is reference-only</b> (model % and EV shown, never a pick: ML backtest at EV ≥ 2% was 253 bets, −22.3u). No PICK when the fair line and the book's line are more than 3 points apart (spread or total): a gap that big usually means a stale or bad price, not an edge. A recheck ~45 min before each kickoff window drops picks whose EV fell below 3%, whose line moved through a key number, or whose fair-vs-book gap now exceeds 3 points.</p>` + splitCards(m) + recheckBox(m);
  const nP = d.games.reduce((a, g) => a + Object.values(g.markets).filter(x => x.decision === 'PICK').length, 0);
  h += `<div class="filters"><label><input type="checkbox" id="onlyPicks"> picks only (${nP})</label> <select id="spf"><option value="">NFL + FBS</option><option value="nfl">NFL</option><option value="cfb">FBS</option></select></div><div id="games"></div>`;
  el.innerHTML = h;
  const draw = () => {
    const only = $('#onlyPicks').checked, sp = $('#spf').value; let out = '';
    for (const g of d.games) {
      if (sp && g.sport !== sp) continue;
      const hasPick = Object.values(g.markets).some(x => x.decision === 'PICK'); if (only && !hasPick) continue;
      out += `<div class="card"><div class="gh"><span class="tag ${g.sport}">${g.sport.toUpperCase()}</span> <b>${g.away} @ ${g.home}</b><span class="k">${g.kick_ct}</span></div><table><tr><th>Mkt</th><th>Side</th><th>Price</th><th>Mkt %</th><th>Model %</th><th>Edge</th><th>EV</th><th></th></tr>`;
      for (const [mk, lab] of [['ml', 'ML'], ['spread', 'Spread'], ['total', 'O/U']]) {
        const x = g.markets[mk]; if (!x || !x.sides || !x.sides.length) { out += `<tr><td>${lab}</td><td colspan=7 class="mut">no DK/Bovada price</td></tr>`; continue; }
        const b = bestPer(x.sides); const order = mk === 'total' ? ['over', 'under'] : ['away', 'home'];
        order.forEach((sd, i) => { const s = b[sd]; if (!s) return; const isPick = x.decision === 'PICK' && x.best.side === sd;
          const nm = mk === 'total' ? (sd === 'over' ? 'O ' : 'U ') + s.line : (s.team.split(' ').slice(-1)[0] + (mk === 'spread' ? ' ' + ln(s.line) : ''));
          out += `<tr class="${isPick ? 'pk' : ''}">${i === 0 ? `<td rowspan=2>${lab}</td>` : ''}<td>${nm}</td><td>${am(s.price)} <small>${s.book}</small></td><td>${pct(s.market_pct)}</td><td>${pct(s.model_pct)}</td><td>${sgn(s.model_pct - s.market_pct)}</td><td>${sgn(s.ev)}%</td>${i === 0 ? `<td rowspan=2><span class="dec ${x.decision}" title="${x.reason}">${x.decision === 'REF' ? 'REF only' : x.decision}</span>${x.recheck ? `<br><small>recheck: ${x.recheck.action}</small>` : ''}</td>` : ''}</tr>`; });
      }
      out += `</table></div>`;
    }
    $('#games').innerHTML = out || '<p class="mut">No games in window.</p>';
  };
  $('#onlyPicks').onchange = draw; $('#spf').onchange = draw; draw();
}
function renderProps(d) {
  const el = $('#props'); let h = head(d.meta, 'props'); const H = d.meta.headline;
  if (H.props_atd) h += `<div class="hls"><div><div class="cap">${H.props_other.label}</div><div class="hl"><b>${H.props_other.record}</b> · ${H.props_other.units >= 0 ? '+' : ''}${(H.props_other.units || 0).toFixed(2)}u<span class="sub">${expLine(H.props_other.expected)}</span></div></div><div><div class="cap">${H.props_atd.label}</div><div class="hl"><b>${H.props_atd.record}</b> · ${H.props_atd.units >= 0 ? '+' : ''}${(H.props_atd.units || 0).toFixed(2)}u<span class="sub">A few long-odds hits swing this; judge the model on the yards/receptions line.</span></div></div></div>`;
  h += `<p class="note">Players listed Out/Doubtful/IR on ESPN at log time are skipped; a player ruled Out before kick is VOIDed by the recheck. Grading: a player who appears in the box score but has no stat in that category is graded as 0 (not void); only a player missing from the box score entirely (DNP) is VOID. Research only, never official plays. `;
  h += `Top 5 per NFL game by model edge (model % − market %). Market % = median no-vig across every US book quoting that exact line (anytime TD: median implied, vig included, one-sided). <b>Backtest: the props model does NOT beat the market (fitted weight 0, 90% CI 0–0.23) — these are tracked paper leans, not validated picks.</b> Model % = market + 0.2 × (raw model − market); 0.2 is the top of the fitted weight's 90% CI. Ranking is by raw edge (same order). Proj = mean projection.</p>`;
  for (const g of d.games) {
    h += `<div class="card"><div class="gh"><b>${g.game}</b><span class="k">${g.kick_ct}</span></div><div class="mut small">markets pulled: ${g.markets_pulled.map(x => x.replace('player_', '')).join(', ') || '—'} · ${g.n_candidates} priced sides</div><table><tr><th>Player</th><th>Prop</th><th>Price</th><th>Proj</th><th>Model raw</th><th>Model %</th><th>Mkt %</th><th>Edge</th><th>EV</th></tr>`;
    for (const r of g.top) h += `<tr><td>${r.player} <small>${r.team}</small></td><td>${r.market} ${r.side}${r.line != null ? ' ' + r.line : ''}</td><td>${am(r.price)} <small>${r.book}</small></td><td>${r.projection}</td><td class="mut">${pct(r.model_raw_pct)}</td><td>${pct(r.model_pct)}</td><td title="${r.market_basis}">${pct(r.market_pct)}</td><td>${sgn(r.edge)}</td><td>${sgn(r.ev_model)}%</td></tr>`;
    if ((g.skipped_injured || []).length) h += `<tr><td colspan=9 class="mut small">skipped (injury report): ${g.skipped_injured.join(', ')}</td></tr>`;
    if (!g.top.length) h += `<tr><td colspan=9 class="mut">no matched props yet</td></tr>`;
    h += `</table></div>`;
  }
  if (!d.games.length) h += '<p class="mut">No NFL games within the props window (54h) or no props pulled yet.</p>';
  el.innerHTML = h;
}
function mBlock(d, sport) {
  const bt = d.backtest || {};
  let h = `<h2>${sport === 'nfl' ? 'NFL' : 'FBS (college)'}</h2><div class="note ${d.influence ? '' : 'warn'}"><b>${d.status || 'INFO ONLY'}</b>: ${d.influence ? 'passed its pre-registered test and can affect board picks.' : 'did not beat the closing line out of sample, so it never changes a board pick. Leans are shown for transparency only.'}<br><small>Spread: ${bt.spread || '—'}<br>Total: ${bt.total || '—'}</small></div>`;
  h += `<p class="small mut">Data through ${d.data_through || '—'}${d.n_fbs ? ' · ranks among ' + d.n_fbs + ' FBS teams' : ''} · generated ${d.generated_ct || '—'}${sport === 'cfb' ? ' · lines: ESPN scoreboard (DraftKings) · pass rush/protection = sack rate (no pressure data in CFB play-by-play)' : ''}</p>`;
  const rk = (r, k) => r && r[k] ? '#' + r[k] : '—';
  for (const g of d.games || []) {
    const H = g.ranks[g.home], A = g.ranks[g.away];
    h += `<div class="card"><div class="gh"><span class="tag ${sport}">${sport.toUpperCase()}</span> <b>${g.game}</b><span class="k">${g.gameday} ${g.gametime || ''}${g.spread_line != null ? ' · line ' + g.home + ' ' + ln(-g.spread_line) : ''}${g.total_line != null ? ' · total ' + g.total_line : ''}</span></div>`;
    h += `<div class="small">${g.away}: ${g.styles[g.away]} · ${g.home}: ${g.styles[g.home]}</div>`;
    h += `<table><tr><th>Unit</th><th>${g.away}</th><th>${g.home}</th></tr>` + [['Pass offense', 'pass_off'], ['Run offense', 'rush_off'], ['Pass protection', 'pass_prot'], ['Pass defense', 'pass_def'], ['Run defense', 'rush_def'], ['Pass rush', 'pass_rush']].map(([l, k]) => `<tr><td>${l}</td><td>${rk(A, k)}</td><td>${rk(H, k)}</td></tr>`).join('') + `<tr><td class="mut">games this season</td><td class="mut">${A.n_games}</td><td class="mut">${H.n_games}</td></tr></table>`;
    h += '<ul class="small">' + (g.edges.length ? g.edges.map(e => `<li>${e.text}</li>`).join('') : '<li class="mut">No clear unit mismatch (no unit pairing with one side top-tier and the other bottom-tier).</li>');
    h += `<li>Similar foes: ${g.home} ${sgn(g.similar.home / 100)} pts ATS vs teams styled like ${g.away} (weight ${g.similar.n_home}); ${g.away} ${sgn(g.similar.away / 100)} pts vs teams styled like ${g.home} (weight ${g.similar.n_away})</li>`;
    h += `<li>Common opponents (${g.common_opponents.length}): ${g.common_opponents.slice(0, 12).join(', ') || 'none'}${g.common_opponents.length > 12 ? '…' : ''}${g.common_opponents.length ? ' · shrunk ATS gap ' + sgn(Math.abs(g.comopp_gap) / 100) + ' pts toward ' + (g.comopp_gap >= 0 ? g.home : g.away) : ''}</li>`;
    h += `<li><b>${g.lean_text}</b> <span class="mut">(info only)</span></li></ul></div>`;
  }
  if (!(d.games || []).length) h += '<p class="mut">No games with lines in the next 7 days.</p>';
  return h;
}
function renderMatchups(d) {
  const el = $('#matchups');
  if (!d || !d.games) { el.innerHTML = '<p class="mut">Matchup data not generated yet.</p>'; return; }
  let h = `<div class="subnav"><button onclick="document.getElementById('mu-nfl').scrollIntoView({behavior:'smooth'})">NFL</button><button onclick="document.getElementById('mu-cfb').scrollIntoView({behavior:'smooth'})">FBS</button></div>`;
  h += `<p class="note">Opponent-adjusted unit ratings from free play-by-play (nflverse for NFL, cfbfastR for FBS): this season plus last season at 35% weight, games already played only. Ranks: 1 = best. Run and pass units use EPA per play. "Similar foes" = how each team did against the spread vs past opponents whose style resembles this week's opponent (shrunk toward 0). Common opponents = teams both have played this season or last.</p>`;
  h += `<div id="mu-nfl">${mBlock(d, 'nfl')}</div><div id="mu-cfb">${d.cfb ? mBlock(d.cfb, 'cfb') : '<h2>FBS</h2><p class="mut">No FBS matchup data yet.</p>'}</div>`;
  el.innerHTML = h;
}
function renderSim(d) {
  const el = $('#sim');
  if (!d || !d.games) { el.innerHTML = '<p class="mut">Simulator output not generated yet.</p>'; return; }
  const bt = d.backtest || {};
  let h = `<div class="note warn"><b>${d.status}</b>: ${d.n_sims_per_game.toLocaleString()} simulations per game. The sim starts at the de-vigged market spread and total, applies shrunk matchup adjustments, plays each game drive by drive (TD/FG/no score), and is weighted to NFL/CFB key-number frequencies. <b>It never changes a pick</b>; it did not beat the closing line in its pre-registered backtest.<br><small>NFL: ${bt.nfl || '—'}<br>FBS: ${bt.cfb || '—'}</small></div>`;
  h += `<p class="small mut">${d.lines_note} Δ = sim % − market % (de-vigged). With 1,000 sims (weighted n≈700), a Δ under about ±3.5pp is within simulation noise. Cover and over % exclude pushes. Generated ${d.generated_ct}.</p>`;
  h += `<div class="filters"><select id="simsp"><option value="">NFL + FBS</option><option value="nfl">NFL</option><option value="cfb">FBS</option></select> <label>sort <select id="simsort"><option value="gap">biggest |Δ| first</option><option value="when">kickoff</option></select></label></div><div id="simt"></div>`;
  el.innerHTML = h;
  const pp = x => (100 * x).toFixed(1) + '%', dd = x => `<span class="${Math.abs(x) >= 0.035 ? 'b' : 'mut'}">${x >= 0 ? '+' : ''}${(100 * x).toFixed(1)}</span>`;
  const draw = () => {
    const sp = $('#simsp').value; let G = d.games.filter(g => !sp || g.sport === sp);
    const gap = g => Math.max(Math.abs(g.d_cover), Math.abs(g.d_over), Math.abs(g.d_win));
    G = $('#simsort').value === 'gap' ? G.slice().sort((a, b) => gap(b) - gap(a)) : G.slice().sort((a, b) => a.when.localeCompare(b.when));
    let t = `<table class="ledger"><tr><th>Game</th><th>Line</th><th>${'Home win'}<br><small>sim / mkt / Δ</small></th><th>Home cover<br><small>sim / mkt / Δ</small></th><th>Over<br><small>sim / mkt / Δ</small></th><th>Median score<br><small>(10–90%)</small></th></tr>`;
    for (const g of G) t += `<tr><td><span class="tag ${g.sport}">${g.sport.toUpperCase()}</span> ${g.game}<br><small class="mut">${g.when}</small></td><td>${g.home} ${ln(g.home_line)}<br><small>O/U ${g.total_line}</small></td><td>${pp(g.sim_home_win)} / ${pp(g.mkt_home_win)} / ${dd(g.d_win)}</td><td>${pp(g.sim_home_cover)} / ${pp(g.mkt_home_cover)} / ${dd(g.d_cover)}</td><td>${pp(g.sim_over)} / ${pp(g.mkt_over)} / ${dd(g.d_over)}</td><td>${g.away} ${g.away_pts_median} (${g.away_pts_10_90[0]}–${g.away_pts_10_90[1]})<br>${g.home} ${g.home_pts_median} (${g.home_pts_10_90[0]}–${g.home_pts_10_90[1]})</td></tr>`;
    $('#simt').innerHTML = t + '</table>';
  };
  $('#simsp').onchange = draw; $('#simsort').onchange = draw; draw();
}
function renderWatch(w) {
  if (!w || !w.items) return;
  const r = w.record;
  let h = `<div id="watch"><h2>Watch line: ${w.name}</h2><div class="note warn"><b>Not pre-registered and never a pick.</b> This came from one sensitivity cell in the CFB matchup backtest (${w.backtest}). It is tracked forward on paper only, to see if it holds. Rule: ${w.rule}</div>`;
  h += `<div class="hl"><b>Paper record: ${r.w}-${r.l}-${r.p}</b> · ${r.units >= 0 ? '+' : ''}${r.units.toFixed(2)}u at −110 · ${r.open} open</div>`;
  h += `<table class="ledger"><tr><th>Game</th><th>Kick</th><th>Watch</th><th>Lean</th><th>Status</th></tr>` + w.items.map(i => `<tr><td>${i.game}</td><td class="small">${i.gameday}</td><td>${i.side} ${i.line}</td><td>${i.lean > 0 ? '+' : ''}${i.lean}</td><td><span class="st ${i.status}">${i.status}</span>${i.final_total != null ? ' <small>(final ' + i.final_total + ')</small>' : ''}</td></tr>`).join('') + '</table></div>';
  $('#sim').insertAdjacentHTML('beforeend', h);
}
function renderLedger(d) {
  const el = $('#ledger'); const L = d.ledger.items.filter(i => i.tab !== 'teasers' && i.tab !== 'parlays').sort((a, b) => (b.kick_iso || '').localeCompare(a.kick_iso || ''));
  let h = splitCards(d.meta) + '<div class="hls">' + ['board', 'props'].map(k => `<div><div class="cap">${({board: 'Board picks', props: 'NFL props (paper leans)'})[k]}</div>${head(d.meta, k)}</div>`).join('') + '</div>';
  const ret = d.ledger.items.filter(i => i.tab === 'teasers' || i.tab === 'parlays');
  if (ret.length) h += `<p class="small mut">Teasers and parlays were retired on Oct 8 2026 and are no longer produced. ${ret.length} past ticket(s) stay in the data file and in the official/research totals above, but are not listed here.</p>`;
  h += `<div class="filters"><select id="kindf"><option value="">official + research</option><option value="official">official plays only</option><option value="research">research only</option></select></div><table class="ledger"><tr><th>Tab</th><th>Kind</th><th>Kick</th><th>Bet</th><th>Price</th><th>Status</th><th>Units</th></tr>`;
  const kindOf = i => i.kind || (i.tab === 'board' ? 'official' : 'research');
  const kf = (location.hash.split(':')[1] || '');
  for (const i of L) {
    if (kf && kindOf(i) !== kf) continue;
    let bet = '';
    if (i.tab === 'board') bet = `${i.away} @ ${i.home}: ${i.market.toUpperCase()} ${i.pick}${i.line != null ? ' ' + ln(i.line, i.market !== 'total') : ''} <small>${i.book}</small>`;
    else if (i.tab === 'props') bet = `${i.player} ${i.market} ${i.side}${i.line != null ? ' ' + i.line : ''} <small>${i.book}</small>${i.actual != null ? ' <small>(actual ' + i.actual + ')</small>' : ''}`;
    h += `<tr class="${kindOf(i)}"><td>${i.tab}</td><td class="small">${kindOf(i)}</td><td class="small">${(i.kick_ct || i.set_key || '')}</td><td>${bet}</td><td>${am(i.price)}</td><td><span class="st ${i.status}" title="${i.void_reason || ''}">${i.status}</span>${i.void_reason ? '<br><small>' + i.void_reason + '</small>' : ''}</td><td>${i.units != null ? i.units.toFixed(2) : ''}</td></tr>`;
  }
  if (!L.length) h += `<tr><td colspan=7 class="mut">No logged picks yet. Board picks are logged when first shown; props lock when kick is within 24h.</td></tr>`;
  el.innerHTML = h + '</table>';
  $('#kindf').value = kf; $('#kindf').onchange = () => { location.hash = 'ledger' + ($('#kindf').value ? ':' + $('#kindf').value : ''); renderLedger(d); };
}
(async () => {
  const [b, p, l] = await Promise.all(['board', 'props', 'ledger'].map(J));
  renderBoard(b); renderProps(p); renderLedger(l);
  try { renderMatchups(await J('matchups')); } catch (e) { renderMatchups(null); }
  try { renderSim(await J('sim')); } catch (e) { renderSim(null); }
  try { renderWatch(await J('watch')); } catch (e) { }
  const c = b.meta.credits; $('#foot').innerHTML = `Generated ${b.meta.generated_ct} · Odds API credits today ${c.spent_today}/${c.daily_cap} · remaining ${c.remaining} · picks only, never bets placed`;
  document.querySelectorAll('nav button').forEach(x => x.onclick = () => tab(x.dataset.t));
  tab((location.hash || '#board').slice(1));
})();
