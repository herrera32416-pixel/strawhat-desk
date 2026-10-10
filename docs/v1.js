// MERGED DESK (Oct 9 2026): Board, NHL headline and the PAPER scorecard come from the one v1 pipeline
// (docs/data/v1/*.json, built by .github/workflows/v1-board.yml + v1-goalies.yml). PAPER ONLY, straight bets only.
(() => {
  const $ = s => document.querySelector(s);
  const P = v => v == null || v === '' ? '—' : (Math.round(Number(v) * 10) / 10) + '%';
  const A = a => a == null || a === '' ? '' : (a > 0 ? '+' + a : '' + a);
  const L = (x, sg = true) => x == null ? '' : (sg && x > 0 ? '+' + x : '' + x);
  const E = v => v == null || v === '' ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(1);
  const last = t => String(t || '').split(' ').slice(-1)[0];
  async function J(n) { const r = await fetch('data/v1/' + n + '.json?' + Date.now(), { cache: 'no-store' }); if (!r.ok) throw new Error(n); return r.json(); }
  const when = (sel, fn, n = 0) => { const e = document.querySelector(sel); if (e) fn(e); else if (n < 100) setTimeout(() => when(sel, fn, n + 1), 100); };
  const rows = d => [...(d.card.clears || []), ...(d.card.fills || []), ...(d.card.holds || [])]
    .filter((r, i, a) => a.findIndex(x => x.event_id === r.event_id) === i)
    .sort((a, b) => String(a.kick_utc).localeCompare(String(b.kick_utc)));
  function mktRows(g) {
    const pm = (g.paper && g.paper.markets) || {}, bm = (g.paper && g.paper.by_market) || {};
    let out = '';
    for (const [k, lab] of [['ml', 'ML'], ['spread', g.sport === 'NHL' ? 'Puck line' : g.sport === 'MLB' ? 'Run line' : 'Spread'], ['total', 'O/U']]) {
      const m = pm[k], st = (bm[k] || {}).status || 'PASS', note = (bm[k] || {}).note || (m && m.note) || '';
      let sides = m && m.sides && m.sides.length ? m.sides : null;
      if (!sides) { // market-only fallback from the row (ESPN/odds consensus)
        sides = k === 'ml' ? [{ label: last(g.away) + ' ML', price_american: g.ml_away_price, book: g.ml_away_book, novig_pct: g.market_away_ml_pct }, { label: last(g.home) + ' ML', price_american: g.ml_home_price, book: g.ml_home_book, novig_pct: g.market_home_ml_pct }]
          : k === 'spread' ? [{ label: last(g.away) + ' ' + L(g.spread_away_line), price_american: g.spread_away_price, book: g.spread_away_book, novig_pct: g.market_away_cover_pct }, { label: last(g.home) + ' ' + L(g.spread_home_line), price_american: g.spread_home_price, book: g.spread_home_book, novig_pct: g.market_home_cover_pct }]
          : [{ label: 'O ' + (g.total_line ?? ''), price_american: g.over_price, book: g.over_book, novig_pct: g.market_over_pct }, { label: 'U ' + (g.total_line ?? ''), price_american: g.under_price, book: g.under_book, novig_pct: g.market_under_pct }];
        if (sides.every(s => s.price_american == null && s.novig_pct == null)) { out += `<tr><td>${lab}</td><td colspan=6 class="mut">no line</td></tr>`; continue; }
      }
      sides.slice(0, 2).forEach((s, i) => {
        const nm = String(s.label || '').replace(g.away, last(g.away)).replace(g.home, last(g.home)).replace(/^Over /, 'O ').replace(/^Under /, 'U ');
        const pick = st === 'PAPER' && g.paper.best && g.paper.best.label === s.label;
        out += `<tr class="${pick ? 'pk' : ''}">${i === 0 ? `<td rowspan=2>${lab}</td>` : ''}<td>${nm}</td><td>${A(s.price_american)} <small>${s.book || ''}</small></td><td>${P(s.novig_pct)}</td><td>${P(s.model_pct)}</td><td>${s.model_pct == null ? '—' : E(s.edge_pp)}</td>${i === 0 ? `<td rowspan=2><span class="dec ${st === 'PAPER' ? 'PICK' : st}" title="${note}">${st}</span></td>` : ''}</tr>`;
      });
    }
    return out;
  }
  function goalieLine(g) {
    const gl = g.paper && g.paper.goalies; if (g.sport !== 'NHL') return '';
    const f = (s, t) => { const x = gl && gl[s]; return `${last(t)}: ${x ? `${x.goalie} (${x.status})` : '—'}`; };
    const conf = gl && gl.home && gl.away && /confirm/i.test(gl.home.status) && /confirm/i.test(gl.away.status);
    let h = `<div class="small">${conf ? '' : '⚠ '}Goalies · ${f('away', g.away)} · ${f('home', g.home)}${conf ? '' : ' · not both confirmed'}</div>`;
    const nm = g.paper.nhl_model, w = g.paper.w || {};
    if (nm) h += `<div class="small mut"><b>Research only · NHL xG model</b> reg goals ${last(g.away)} ${nm.reg_goals_away} – ${last(g.home)} ${nm.reg_goals_home} · reg tie ${nm.reg_tie_pct}% · GSAx/gm ${E(nm.gsax_pg_away)} / ${E(nm.gsax_pg_home)} · w ML ${w.ml ?? 0} PL ${w.pl ?? 0} O/U ${w.tot ?? 0} (0 = shown, not used)</div>`;
    return h;
  }
  function card(g) {
    return `<div class="card"><div class="gh"><span class="tag ${g.sport_raw}">${g.sport}</span> <b>${g.away} @ ${g.home}</b><span class="k">${g.kick_ct}</span></div><table><tr><th>Mkt</th><th>Side</th><th>Price</th><th>Mkt % (no-vig)</th><th>Model %</th><th>Edge pp</th><th></th></tr>${mktRows(g)}</table>${goalieLine(g)}</div>`;
  }
  function board(d, pl) {
    const el = $('#board'), R = rows(d), s = pl.summary || {};
    const nP = R.filter(g => g.paper && g.paper.status === 'PAPER').length;
    let h = `<div class="hl"><b>PAPER ONLY</b> · straight bets only (no teasers, no parlays) · ${R.length} games · ${nP} paper play(s)<span class="sub">1u = $20 · updated ${String(d.generated_at_ct || '').replace('T', ' ').slice(0, 16)} CT</span></div>`;
    h += `<p class="note">One desk: lines from The Odds API free tier (only when a game is within ~36h) with ESPN filling gaps, tagged per line. Every game shows ML / spread / total, each with market no-vig % and its own model % (blank stays blank = no model). Sorted by start time (CT). A play needs ≥ 3pp edge at a real DraftKings / Betr / Bovada price.</p>`;
    h += `<div class="filters"><label><input type="checkbox" id="v1only"> paper plays only (${nP})</label> <select id="v1sp"><option value="">All sports</option>${[...new Set(R.map(g => g.sport))].map(x => `<option>${x}</option>`).join('')}</select></div><div id="v1games"></div>`;
    el.innerHTML = h;
    const draw = () => { const o = $('#v1only').checked, sp = $('#v1sp').value;
      $('#v1games').innerHTML = R.filter(g => (!sp || g.sport === sp) && (!o || (g.paper && g.paper.status === 'PAPER'))).map(card).join('') || '<p class="mut">No games in window.</p>'; };
    $('#v1only').onchange = draw; $('#v1sp').onchange = draw; draw();
  }
  function nhl(d) {
    const R = rows(d).filter(g => g.sport === 'NHL');
    when('#nhl-v1', el => el.innerHTML = `<div class="hl"><b>NHL · market no-vig headline</b> · xG model = research line only (lost to the market in walk-forward tests, w=0) · goalie check via DailyFaceoff, ⚠ until both starters confirmed<span class="sub">${R.length} games</span></div>` + R.map(card).join(''));
  }
  function ledger(pl) {
    const s = pl.summary || {}, P2 = (pl.picks || []).slice().sort((a, b) => String(b.kick_utc).localeCompare(String(a.kick_utc)));
    const t = s.total || s.all || s;
    when('#ledger-v1', el => {
      let h = `<div class="cap">Scorecard (the one grader · PAPER)</div><div class="hl"><b>${t.record || ((t.w ?? t.wins ?? 0) + '-' + (t.l ?? t.losses ?? 0) + '-' + (t.p ?? t.pushes ?? 0))}</b> · ${t.units != null ? (t.units >= 0 ? '+' : '') + Number(t.units).toFixed(2) + 'u' : ''} · ${P2.length} paper pick(s)<span class="sub">updated ${String(pl.updated_at_ct || '').replace('T', ' ').slice(0, 16)} CT</span></div>`;
      h += `<table class="ledger"><tr><th>Sport</th><th>Kick</th><th>Bet</th><th>Price</th><th>Result</th><th>Units</th></tr>` + P2.map(i => `<tr><td>${i.sport}</td><td class="small">${i.kick_ct}</td><td>${i.matchup}: ${i.selection} <small>${i.book}</small></td><td>${A(i.price_american)}</td><td><span class="st ${i.result || i.status || 'open'}">${i.result || i.status || 'open'}</span></td><td>${i.units_won != null ? Number(i.units_won).toFixed(2) : (i.pnl_units != null ? Number(i.pnl_units).toFixed(2) : '')}</td></tr>`).join('') + '</table>';
      h += `<div class="cap" style="margin-top:18px">History · Strawhat ledger through Oct 9 2026 (no new rows; includes the retired teaser record)</div>`;
      el.innerHTML = h;
    });
  }
  Promise.all([J('today'), J('paper_ledger')]).then(([d, pl]) => { board(d, pl); nhl(d); ledger(pl); })
    .catch(e => { const el = $('#board'); if (el) el.innerHTML = '<p class="note">Board data not published yet.</p>'; });
})();
