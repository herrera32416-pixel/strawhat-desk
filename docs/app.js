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
  let s = `<div class="hl"><b>${h.record || '0-0-0'}</b> · ${h.units >= 0 ? '+' : ''}${(h.units || 0).toFixed(2)}u ($${(h.dollars || 0).toFixed(0)}) · ${h.open || 0} open`;
  if (key === 'teasers' && h.ticket1_rule) s += ` · ticket #1 rule: ${h.ticket1_rule.record}, ${h.ticket1_rule.units}u`;
  return s + `<span class="sub">1u = $20 · updated ${meta.generated_ct}</span></div>`;
}
function bestPer(sides) { const b = {}; for (const s of sides) if (!b[s.side] || s.ev > b[s.side].ev) b[s.side] = s; return b; }
function renderBoard(d) {
  const el = $('#board'); const m = d.meta;
  let h = head(m, 'board') + `<p class="note">Odds as of: NFL ${m.odds_asof.nfl || '—'} · CFB ${m.odds_asof.cfb || '—'}. Model % = KEYS fair (consensus of other books incl. Pinnacle, priced through historical margin/total distributions) at the DK/Bovada line. PICK only if EV ≥ 2% at a real DK/Bovada price.</p>`;
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
          out += `<tr class="${isPick ? 'pk' : ''}">${i === 0 ? `<td rowspan=2>${lab}</td>` : ''}<td>${nm}</td><td>${am(s.price)} <small>${s.book}</small></td><td>${pct(s.market_pct)}</td><td>${pct(s.model_pct)}</td><td>${sgn(s.model_pct - s.market_pct)}</td><td>${sgn(s.ev)}%</td>${i === 0 ? `<td rowspan=2><span class="dec ${x.decision}" title="${x.reason}">${x.decision}</span></td>` : ''}</tr>`; });
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
function renderTeasers(d) {
  const el = $('#teasers'); let h = head(d.meta, 'teasers');
  h += `<p class="note">6 legs × 6 points. Payout +600 (DraftKings and Bovada NFL regular-season 6-team, 6-pt tables; ties reduce the ticket). Break-even: ticket 14.29%, per leg 72.3%. Leg % = KEYS distribution at the teased line, shrunk toward the leg's historical band rate (nflverse closes 2006–2025). Ticket #1 is the backtested rule; #2–#5 are shown because the desk shows 5, but the backtest says extra tickets built from weaker legs lose.</p>`;
  for (const t of d.tickets) {
    h += `<div class="card"><div class="gh"><b>Teaser ${t.n}</b> <span class="dec ${t.decision.startsWith('PLAY') ? 'PICK' : (t.decision.startsWith('LEAN') ? 'LEAN' : 'PASS')}">${t.decision}</span><span class="k">${t.name}</span></div>
    <div class="small">All-6 prob <b>${pct(t.p_all_six)}</b> vs break-even ${pct(t.breakeven_ticket)} · cash prob incl. push reduction ${pct(t.p_cash_incl_push)} · EV ${sgn(t.ev_per_unit)}% per 1u</div><table><tr><th>Leg</th><th>Line → teased</th><th>Leg %</th></tr>`;
    for (const l of t.legs) h += `<tr><td style="white-space:normal"><b>${l.pick}</b><br><small>${l.sport.toUpperCase()} · ${l.game} · ${l.kick_ct} · ${l.book}<br>${l.band}${l.p_band ? ' (hist ' + pct(l.p_band) + ')' : ''}</small></td><td>${l.market === 'spread' ? ln(l.orig_line) + ' → <b>' + ln(l.teased_line) + '</b>' : (l.side === 'over' ? 'O ' : 'U ') + l.orig_line + ' → <b>' + l.teased_line + '</b>'}</td><td>${pct(l.p_cond)}</td></tr>`;
    h += `</table></div>`;
  }
  if (!d.tickets.length) h += '<p class="mut">Not enough distinct games for a 6-leg teaser in the current window.</p>';
  el.innerHTML = h;
}
function renderLedger(d) {
  const el = $('#ledger'); const L = d.ledger.items.slice().sort((a, b) => (b.kick_iso || '').localeCompare(a.kick_iso || ''));
  let h = '<div class="hls">' + ['board', 'props', 'teasers'].map(k => `<div><div class="cap">${k === 'board' ? 'Board picks' : k === 'props' ? 'NFL props (paper leans)' : 'Teasers'}</div>${head(d.meta, k)}</div>`).join('') + '</div>';
  h += `<table class="ledger"><tr><th>Tab</th><th>Kick</th><th>Bet</th><th>Price</th><th>Status</th><th>Units</th></tr>`;
  for (const i of L) {
    let bet = '';
    if (i.tab === 'board') bet = `${i.away} @ ${i.home}: ${i.market.toUpperCase()} ${i.pick}${i.line != null ? ' ' + ln(i.line, i.market !== 'total') : ''} <small>${i.book}</small>`;
    else if (i.tab === 'props') bet = `${i.player} ${i.market} ${i.side}${i.line != null ? ' ' + i.line : ''} <small>${i.book}</small>${i.actual != null ? ' <small>(actual ' + i.actual + ')</small>' : ''}`;
    else bet = `Teaser ${i.n} (${i.decision}): ` + i.legs.map(l => `${l.pick} ${l.market === 'spread' ? ln(l.teased_line) : l.teased_line}${l.status !== 'open' ? '[' + l.status + ']' : ''}`).join(', ');
    h += `<tr><td>${i.tab}</td><td class="small">${(i.kick_ct || i.set_key || '')}</td><td>${bet}</td><td>${am(i.price)}</td><td><span class="st ${i.status}">${i.status}</span></td><td>${i.units != null ? i.units.toFixed(2) : ''}</td></tr>`;
  }
  if (!L.length) h += `<tr><td colspan=6 class="mut">No logged picks yet. Board picks are logged when first shown; props lock when kick is within 24h, teasers when the first leg is within 14h.</td></tr>`;
  el.innerHTML = h + '</table>';
}
(async () => {
  const [b, p, t, l] = await Promise.all(['board', 'props', 'teasers', 'ledger'].map(J));
  renderBoard(b); renderProps(p); renderTeasers(t); renderLedger(l);
  const c = b.meta.credits; $('#foot').innerHTML = `Generated ${b.meta.generated_ct} · Odds API credits today ${c.spent_today}/${c.daily_cap} · remaining ${c.remaining} · picks only, never bets placed`;
  document.querySelectorAll('nav button').forEach(x => x.onclick = () => tab(x.dataset.t));
  tab((location.hash || '#board').slice(1));
})();
