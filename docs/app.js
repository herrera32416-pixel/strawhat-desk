const $ = (s, el = document) => el.querySelector(s);
const pct = x => x == null ? '' : (100 * x).toFixed(1) + '%';
const am = a => a == null ? '' : (a > 0 ? '+' + a : '' + a);
const sgn = x => x == null ? '' : ((x >= 0 ? '+' : '') + (100 * x).toFixed(1));
const ln = (x, signed = true) => x == null ? '' : (signed && x > 0 ? '+' + x : '' + x);
async function J(n) { const r = await fetch('data/' + n + '.json?' + Date.now()); return r.json(); }
function tab(id) {
  document.querySelectorAll('nav button').forEach(b => b.classList.toggle('on', b.dataset.t === id));
  document.querySelectorAll('section.tab').forEach(s => s.hidden = s.id !== id);
  location.hash = id;
}
function head(meta, key) {
  const h = meta.headline[key] || {};
  let s = `<div class="hl"><b>${h.record || '0-0-0'}</b> · ${h.units >= 0 ? '+' : ''}${(h.units || 0).toFixed(2)}u ($${(h.dollars || 0).toFixed(0)}) · ${h.open || 0} open${h.void ? ' · ' + h.void + ' void' : ''}`;
  if (h.ticket1) s += ` · ticket #1: ${h.ticket1.record}, ${h.ticket1.units}u · PLAY only: ${h.play_only.record}, ${h.play_only.units}u`;
  return s + `<span class="sub">1u = $20 · updated ${meta.generated_ct}</span></div>`;
}
function recheckBox(m) {
  const r = m.recheck; if (!r || !r.ran_ct) return '';
  let h = `<div class="note warn"><b>Pre-kick recheck ${r.ran_ct}</b> · ${Object.entries(r.sports).map(([k, v]) => k.toUpperCase() + ': ' + v).join(' · ')} · ledger VOIDs: ${r.ledger_voided}`;
  for (const c of r.board_changes) h += `<br>${c.action === 'DROPPED' ? '❌' : '✓'} ${c.pick} ${c.market} ${c.line_9am != null ? ln(c.line_9am) : ''} ${am(c.price_9am)} (EV ${sgn(c.ev_9am)}%) → ${c.line_now != null ? ln(c.line_now) : ''} ${am(c.price_now)} (EV ${sgn(c.ev_now)}%): <b>${c.action}</b> – ${c.reason}`;
  for (const c of r.teaser_changes) h += `<br>❌ ${c.set} teaser #${c.n} VOID: ${c.dropped.join('; ')}`;
  if (!r.board_changes.length && !r.teaser_changes.length) h += '<br>No changes: all picks and teaser legs held.';
  return h + '</div>';
}
function bestPer(sides) { const b = {}; for (const s of sides) if (!b[s.side] || s.ev > b[s.side].ev) b[s.side] = s; return b; }
function renderBoard(d) {
  const el = $('#board'); const m = d.meta;
  let h = head(m, 'board') + `<p class="note">Odds as of: NFL ${m.odds_asof.nfl || '—'} · CFB ${m.odds_asof.cfb || '—'}. Model % = KEYS fair (consensus of other books incl. Pinnacle, priced through historical margin/total distributions) at the DK/Bovada line. PICK only if EV ≥ 3% at a real DK/Bovada price, and never on a spread/total when the game's |spread| ≥ 30. <b>ML is reference-only</b> (model % and EV shown, never a pick: ML backtest at EV ≥ 2% was 253 bets, −22.3u). An ~11:30am CT recheck on Sat (CFB)/Sun (NFL) drops picks whose EV fell below 3% or whose line moved through a key number.</p>` + recheckBox(m);
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
          out += `<tr class="${isPick ? 'pk' : ''}">${i === 0 ? `<td rowspan=2>${lab}</td>` : ''}<td>${nm}</td><td>${am(s.price)} <small>${s.book}</small></td><td>${pct(s.market_pct)}</td><td>${pct(s.model_pct)}</td><td>${sgn(s.model_pct - s.market_pct)}</td><td>${sgn(s.ev)}%</td>${i === 0 ? `<td rowspan=2><span class="dec ${x.decision}" title="${x.reason}">${x.decision === 'REF' ? 'REF only' : x.decision}</span>${x.recheck ? `<br><small>11:30: ${x.recheck.action}</small>` : ''}</td>` : ''}</tr>`; });
      }
      out += `</table></div>`;
    }
    $('#games').innerHTML = out || '<p class="mut">No games in window.</p>';
  };
  $('#onlyPicks').onchange = draw; $('#spf').onchange = draw; draw();
}
function renderProps(d) {
  const el = $('#props'); let h = head(d.meta, 'props');
  h += `<p class="note">Top 5 per NFL game by model edge (model % − market %). Market % = median no-vig across every US book quoting that exact line (anytime TD: median implied, vig included, one-sided). <b>Backtest: the props model does NOT beat the market (fitted weight 0, 90% CI 0–0.23) — these are tracked paper leans, not validated picks.</b> Model % = market + 0.2 × (raw model − market); 0.2 is the top of the fitted weight's 90% CI. Ranking is by raw edge (same order). Proj = mean projection.</p>`;
  for (const g of d.games) {
    h += `<div class="card"><div class="gh"><b>${g.game}</b><span class="k">${g.kick_ct}</span></div><div class="mut small">markets pulled: ${g.markets_pulled.map(x => x.replace('player_', '')).join(', ') || '—'} · ${g.n_candidates} priced sides</div><table><tr><th>Player</th><th>Prop</th><th>Price</th><th>Proj</th><th>Model raw</th><th>Model %</th><th>Mkt %</th><th>Edge</th><th>EV</th></tr>`;
    for (const r of g.top) h += `<tr><td>${r.player} <small>${r.team}</small></td><td>${r.market} ${r.side}${r.line != null ? ' ' + r.line : ''}</td><td>${am(r.price)} <small>${r.book}</small></td><td>${r.projection}</td><td class="mut">${pct(r.model_raw_pct)}</td><td>${pct(r.model_pct)}</td><td title="${r.market_basis}">${pct(r.market_pct)}</td><td>${sgn(r.edge)}</td><td>${sgn(r.ev_model)}%</td></tr>`;
    if (!g.top.length) h += `<tr><td colspan=9 class="mut">no matched props yet</td></tr>`;
    h += `</table></div>`;
  }
  if (!d.games.length) h += '<p class="mut">No NFL games within the props window (54h) or no props pulled yet.</p>';
  el.innerHTML = h;
}
function btLine(b) {
  if (!b || !b.ticket1) return '<span class="mut">No backtest available.</span>';
  const f = (x, lab) => x && x.tickets ? `${lab}: ${x.cashed}-${x.tickets - x.cashed} (${x.tickets} tickets), <b>${x.units >= 0 ? '+' : ''}${x.units}u</b>, ROI ${x.roi >= 0 ? '+' : ''}${(100 * x.roi).toFixed(0)}%, 90% CI [${x.ci90[0]}, ${x.ci90[1]}]` : `${lab}: 0 tickets qualified`;
  return `Backtest, ${b.day}-only games, ${b.seasons} (${b.weeks} slates), closing lines, walk-forward:<br>${f(b.ticket1, 'Ticket #1')}<br>${f(b.all5, 'All 5 tickets')}<br>${f(b.play, 'PLAY-labeled only')}`;
}
function setHead(meta, sk) {
  const h = meta.headline['teasers_' + sk] || {}; const r = x => x ? `${x.record}, ${x.units >= 0 ? '+' : ''}${(x.units || 0).toFixed(2)}u` : '0-0-0, +0.00u';
  return `<div class="hl"><b>Live ledger: ${h.record || '0-0-0'}</b> · ${h.units >= 0 ? '+' : ''}${(h.units || 0).toFixed(2)}u ($${(h.dollars || 0).toFixed(0)}) · ${h.open || 0} open · ticket #1: ${r(h.ticket1)} · PLAY only: ${r(h.play_only)}</div>`;
}
function renderTeasers(d) {
  const el = $('#teasers'); let h = head(d.meta, 'teasers') + recheckBox(d.meta);
  const order = ['cfb_sat', 'nfl_sun'];
  h += `<div class="subnav">` + order.map(k => d.sets[k] ? `<button data-s="${k}">${d.sets[k].label} <small>${d.sets[k].date}</small></button>` : '').join('') + `</div>`;
  h += `<p class="note">Each day: 5 teasers × 6 legs × 6 points, spreads and/or totals, one leg per game per ticket, each leg used at most 2× across the day's 5. Payout +600 (DraftKings/Bovada 6-team 6-pt; ties reduce the ticket). Break-even: ticket <b>14.29%</b>, per leg 72.3%. Leg % = KEYS distribution at the teased line, shrunk toward the leg's historical band rate. <b>PLAY</b> = model EV &gt; 0 at +600; otherwise <b>PASS</b>. Saturday CFB uses only Saturday CFB games; Sunday NFL uses only Sunday NFL games (Thursday/Monday excluded).</p>`;
  for (const k of order) {
    const S = d.sets[k]; if (!S) continue;
    const np = S.tickets.filter(t => t.decision === 'PLAY').length;
    h += `<div class="tset" id="set-${k}"><h2>${S.label} · ${S.date}</h2>${setHead(d.meta, k)}
      <p class="small">${S.n_games} games, ${S.n_candidate_legs} candidate legs · <b>${np} of ${S.tickets.length} PLAY</b></p>
      <div class="note ${S.sport === 'cfb' ? 'warn' : ''}">${S.sport === 'cfb' ? '<b>CFB teasers lost in the backtest.</b> These are the best 5 CFB tickets as requested; any ticket the model rates −EV is PASS. ' : ''}${btLine(S.backtest)}</div>`;
    for (const t of S.tickets) {
      h += `<div class="card"><div class="gh"><b>${S.label} #${t.n}</b> <span class="dec ${t.decision === 'PLAY' ? 'PICK' : t.decision}">${t.decision}${t.decision_9am ? ' (9am ' + t.decision_9am + ')' : ''}</span><span class="k">${t.name}</span></div>
      <div class="small">Combined (all 6) <b>${pct(t.p_all_six)}</b> vs break-even ${pct(t.breakeven_ticket)} (+600) · cash prob incl. push reduction ${pct(t.p_cash_incl_push)} · EV ${sgn(t.ev_per_unit)}% per 1u</div><table><tr><th>Leg</th><th>Line → teased</th><th>Leg %</th></tr>`;
      for (const l of t.legs) h += `<tr><td style="white-space:normal"><b>${l.pick}</b><br><small>${l.sport.toUpperCase()} · ${l.game} · ${l.kick_ct} · ${l.book}${l.band ? '<br>' + l.band : ''}${l.p_band ? ' (hist ' + pct(l.p_band) + ')' : ''}</small></td><td>${l.market === 'spread' ? ln(l.orig_line) + ' → <b>' + ln(l.teased_line) + '</b>' : (String(l.side).toLowerCase() === 'over' ? 'O ' : 'U ') + l.orig_line + ' → <b>' + l.teased_line + '</b>'}</td><td>${pct(l.p_cond)}${l.recheck ? `<br><small>11:30: ${l.recheck.action}${l.recheck.p_now != null ? ' ' + pct(l.recheck.p_now) : ''}${l.recheck.reason ? ' – ' + l.recheck.reason : ''}</small>` : ''}</td></tr>`;
      h += `</table></div>`;
    }
    if (!S.tickets.length) h += `<p class="mut">Not enough ${S.label} games with current lines for a 6-leg teaser yet. ${S.sport === 'cfb' ? 'CFB odds are pulled only once a game is within 36h (credit cap), so this fills in Friday/Saturday morning.' : ''}</p>`;
    h += `</div>`;
  }
  el.innerHTML = h;
  el.querySelectorAll('.subnav button').forEach(b => b.onclick = () => $('#set-' + b.dataset.s).scrollIntoView({behavior: 'smooth'}));
}
function renderLedger(d) {
  const el = $('#ledger'); const L = d.ledger.items.slice().sort((a, b) => (b.kick_iso || '').localeCompare(a.kick_iso || ''));
  let h = '<div class="hls">' + ['board', 'props', 'teasers_cfb_sat', 'teasers_nfl_sun'].map(k => `<div><div class="cap">${({board: 'Board picks', props: 'NFL props (paper leans)', teasers_cfb_sat: 'Teasers · Saturday CFB', teasers_nfl_sun: 'Teasers · Sunday NFL'})[k]}</div>${head(d.meta, k)}</div>`).join('') + '</div>';
  h += `<table class="ledger"><tr><th>Tab</th><th>Kick</th><th>Bet</th><th>Price</th><th>Status</th><th>Units</th></tr>`;
  for (const i of L) {
    let bet = '';
    if (i.tab === 'board') bet = `${i.away} @ ${i.home}: ${i.market.toUpperCase()} ${i.pick}${i.line != null ? ' ' + ln(i.line, i.market !== 'total') : ''} <small>${i.book}</small>`;
    else if (i.tab === 'props') bet = `${i.player} ${i.market} ${i.side}${i.line != null ? ' ' + i.line : ''} <small>${i.book}</small>${i.actual != null ? ' <small>(actual ' + i.actual + ')</small>' : ''}`;
    else bet = `${i.set_label || 'Teaser'} #${i.n} (${i.decision}): ` + i.legs.map(l => `${l.pick} ${l.market === 'spread' ? ln(l.teased_line) : l.teased_line}${l.status !== 'open' ? '[' + l.status + ']' : ''}`).join(', ');
    h += `<tr><td>${i.tab}</td><td class="small">${(i.kick_ct || i.set_key || '')}</td><td>${bet}</td><td>${am(i.price)}</td><td><span class="st ${i.status}" title="${i.void_reason || ''}">${i.status}</span>${i.void_reason ? '<br><small>' + i.void_reason + '</small>' : ''}</td><td>${i.units != null ? i.units.toFixed(2) : ''}</td></tr>`;
  }
  if (!L.length) h += `<tr><td colspan=6 class="mut">No logged picks yet. Board picks are logged when first shown; props lock when kick is within 24h, teaser sets on the morning run of their day (Saturday CFB on Saturday, Sunday NFL on Sunday).</td></tr>`;
  el.innerHTML = h + '</table>';
}
(async () => {
  const [b, p, t, l] = await Promise.all(['board', 'props', 'teasers', 'ledger'].map(J));
  renderBoard(b); renderProps(p); renderTeasers(t); renderLedger(l);
  const c = b.meta.credits; $('#foot').innerHTML = `Generated ${b.meta.generated_ct} · Odds API credits today ${c.spent_today}/${c.daily_cap} · remaining ${c.remaining} · picks only, never bets placed`;
  document.querySelectorAll('nav button').forEach(x => x.onclick = () => tab(x.dataset.t));
  tab((location.hash || '#board').slice(1));
})();
