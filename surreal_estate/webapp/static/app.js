'use strict';
const $ = id => document.getElementById(id);
try { const theme = localStorage.getItem('surreal-theme'); if (theme) document.documentElement.dataset.theme = theme; } catch (_) {}
$('theme')?.addEventListener('click', () => {
  const dark = document.documentElement.dataset.theme === 'dark' || (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme:dark)').matches);
  const theme = dark ? 'light' : 'dark'; document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('surreal-theme', theme); } catch (_) {}
});
// Open a section (and any nested disclosure) before following a report link.
const rail = [...document.querySelectorAll('.rail a[href^="#"]')];
function markSection(id) {
  rail.forEach(a => {
    const active = a.hash === '#' + id;
    a.classList.toggle('on', active);
    if (active) a.setAttribute('aria-current', 'location');
    else a.removeAttribute('aria-current');
  });
}
function revealSection(hash, focus = false) {
  let id;
  try { id = decodeURIComponent(hash.replace(/^#/, '')); } catch (_) { return; }
  const target = document.getElementById(id);
  if (!target) return;
  for (let ancestor = target; ancestor; ancestor = ancestor.parentElement) {
    if (ancestor.tagName === 'DETAILS') ancestor.open = true;
  }
  const disclosure = target.querySelector(':scope > .report-section');
  if (disclosure) disclosure.open = true;
  markSection(target.closest('section')?.id || id);
  const navLink = rail.find(a => a.hash === '#' + (target.closest('section')?.id || id));
  if (navLink?.parentElement.tagName === 'DETAILS') navLink.parentElement.open = true;
  requestAnimationFrame(() => {
    target.scrollIntoView({block:'start'});
    if (focus && disclosure) disclosure.querySelector('summary').focus({preventScroll:true});
  });
}
document.addEventListener('click', event => {
  const link = event.target.closest('a[href^="#"]');
  if (link && document.querySelector('.report-section')) revealSection(link.hash, true);
});
window.addEventListener('hashchange', () => revealSection(location.hash));
if (location.hash) revealSection(location.hash);
document.querySelectorAll('[data-sections]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.report-section').forEach(section => section.open = button.dataset.sections === 'expand');
}));
if (rail.length && 'IntersectionObserver' in window) {
  const observer = new IntersectionObserver(entries => entries.forEach(entry => {
    if (entry.isIntersecting) markSection(entry.target.id);
  }), {rootMargin:'-15% 0px -65% 0px'});
  document.querySelectorAll('main section').forEach(section => observer.observe(section));
}
document.querySelectorAll('[data-map-select]').forEach(button => button.addEventListener('click', () => {
  const selected = button.dataset.mapSelect;
  const reset = button.getAttribute('aria-pressed') === 'true';
  document.querySelectorAll('[data-map-select]').forEach(b => b.setAttribute('aria-pressed', String(!reset && b.dataset.mapSelect === selected)));
  document.querySelectorAll('[data-map-category]').forEach(g => g.style.opacity = reset || g.dataset.mapCategory === selected ? '1' : '.15');
  document.querySelectorAll('[data-map-list]').forEach(list => list.open = !reset && list.dataset.mapList === selected);
}));
if ($('research-form')) {
  let csrf, timer, current, runs = [], submitting = false;
  const form = $('research-form');
  const prefill = new URLSearchParams(location.search);
  if (prefill.has('address')) $('address').value = prefill.get('address').slice(0, 200);
  if (prefill.has('geography')) $('geography').value = prefill.get('geography').slice(0, 120);
  if (prefill.has('parcel_id')) {
    $('parcel-id').value = prefill.get('parcel_id').slice(0, 40);
    $('parcel-id').closest('details').open = true;
  }
  const error = message => { $('form-error').textContent = message; $('form-error').hidden = !message; };
  function buttons() {
    const busy = submitting || runs.some(run => run.status === 'running');
    $('submit').disabled = busy; $('demo').disabled = busy;
  }
  async function api(path, options = {}) {
    const response = await fetch(path, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'The app could not complete this request.');
    return data;
  }
  function node(tag, text, className) {
    const el = document.createElement(tag); el.textContent = text; if (className) el.className = className; return el;
  }
  function history() {
    $('history-list').replaceChildren();
    if (!runs.length) { $('history-list').append(node('p', 'Your first report starts with an address. Or explore a synthetic demo.', 'empty')); return; }
    for (const run of runs) {
      const article = node('article', '', 'card history-item'), detail = node('div', '');
      detail.append(node('h3', run.address), node('p', `${new Date(run.created_at).toLocaleString()} · ${run.demo ? 'Synthetic demo' : run.channels.map(c => c === 'apis' ? 'Public records' : 'Web research').join(' + ')}`));
      detail.append(node('span', run.status === 'complete' ? (run.partial ? 'Report ready · Includes gaps' : 'Report ready') : run.status === 'failed' ? 'Research interrupted' : 'Researching…', 'status-label'));
      article.append(detail);
      if (run.status === 'complete') { const a = node('a', 'Open report ↗', 'pill'); a.href = `/reports/${run.id}/dashboard`; article.append(a); }
      else { const button = node('button', run.status === 'failed' ? 'View details' : 'View progress'); button.type = 'button'; button.onclick = () => watch(run.id); article.append(button); }
      $('history-list').append(article);
    }
  }
  async function refresh() {
    const data = await api('/api/runs'); csrf = data.csrf; runs = data.runs; history(); buttons();
  }
  async function watch(id, focus = true) {
    clearTimeout(timer); current = id; $('progress').hidden = false;
    if (focus) $('progress').focus();
    try {
      const run = await api(`/api/runs/${id}`);
      if (current !== id) return;
      $('progress-title').textContent = run.status === 'running' ? 'Putting the picture together…' : run.status === 'complete' ? 'Your report is ready.' : 'This run needs another try.';
      $('progress-address').textContent = run.address;
      $('progress-message').textContent = run.message;
      $('progress-line').hidden = run.status !== 'running';
      $('report-link').hidden = run.status !== 'complete';
      $('report-link').href = `/reports/${id}/dashboard`;
      $('retry').hidden = run.status !== 'failed';
      $('retry').onclick = () => { $('address').value = run.demo ? '' : run.address; $('geography').value = run.geography; form.scrollIntoView({block:'center'}); $('address').focus(); };
      await refresh();
      if (run.status === 'running') timer = setTimeout(() => watch(id, false), 1500);
    } catch (_) {
      $('progress-message').textContent = 'Connection interrupted. Reconnecting to the local app…';
      timer = setTimeout(() => watch(id, false), 3000);
    }
  }
  $('web').onchange = () => { $('topics').hidden = !$('web').checked; };
  async function start(demo = false) {
    error(''); submitting = true; buttons();
    try {
      const channels = [...form.querySelectorAll('[name=channels]:checked')].map(el => el.value);
      const topics = [...form.querySelectorAll('[name=topics]:checked')].map(el => el.value);
      if (!demo && !channels.length) throw new Error('Choose at least one research channel.');
      if (!demo && channels.includes('web') && !topics.length) throw new Error('Choose at least one web research topic.');
      if (!csrf) await refresh();
      const run = await api('/api/runs', {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}, body:JSON.stringify({address:demo ? '414 Grant Street' : $('address').value.trim(), geography:demo ? 'Pittsburgh, Pennsylvania' : $('geography').value.trim(), channels:demo ? ['apis','web'] : channels, topics:demo ? ['neighborhood_discussion','restaurant_reviews'] : topics, parcel_id:demo ? null : ($('parcel-id').value.trim() || null), demo})});
      await watch(run.id);
    } catch (err) { error(err.message); }
    finally { submitting = false; buttons(); }
  }
  form.onsubmit = event => { event.preventDefault(); start(); };
  $('demo').onclick = () => start(true);
  refresh().then(() => { const running = runs.find(run => run.status === 'running'); if (running) watch(running.id, false); }).catch(() => error('Cannot reach the local app. Start surreal-estate app, then refresh this page.'));
}
