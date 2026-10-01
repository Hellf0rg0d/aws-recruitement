// Client-side race / responsiveness tests, run against the REAL index.html in jsdom.
// INDEX_HTML=<path> selects the page under test (original vs fixed). Prints PASS/FAIL per test.
const assert = require('assert');
const { boot, sleep } = require('./page');

const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const pick = (w, qid = 'q1') => w.document.querySelector(`input[name="${qid}"]`);
const choose = (w, qid, idx = 0) => { const r = w.document.querySelectorAll(`input[name="${qid}"]`)[idx]; r.checked = true; r.dispatchEvent(new w.Event('change', { bubbles: true })); return r.value; };
const finishCalls = c => c.filter(x => x.url && x.url.includes('/api/finish'));
const saveCalls = c => c.filter(x => x.url && x.url.includes('/api/save'));
const toastCount = w => [...w.document.body.children].filter(e => e.style && e.style.position === 'fixed' && e.style.zIndex === '11000').length;
async function armProctoring(h) {            // click "enter fullscreen" so exits/blur are counted
  h.w.document.getElementById('enterFullscreenBtn').click();
  await sleep(250);
  assert.strictEqual(h.w.document.getElementById('fullscreenModal').style.display, 'none', 'fullscreen modal should be dismissed');
}

test('C1  held Ctrl (600 key-repeats) does not flood DOM/log', async () => {
  const h = await boot();
  for (let i = 0; i < 600; i++) h.w.document.body.dispatchEvent(new h.w.KeyboardEvent('keydown', { key: 'Control', ctrlKey: true, repeat: i > 0, bubbles: true }));
  const logs = h.w.getProctorLogs ? h.w.getProctorLogs() : { events: [] };
  assert(toastCount(h.w) <= 3, `${toastCount(h.w)} toast nodes alive (max 3)`);
  assert(logs.total_ctrl_cmd_attempts <= 2, `a single held key was counted ${logs.total_ctrl_cmd_attempts} times`);
  h.w.close();
});

test('C1b blocked shortcuts stay blocked while the key auto-repeats', async () => {
  const h = await boot();
  let blocked = 0;
  for (let i = 0; i < 5; i++) {
    const ev = new h.w.KeyboardEvent('keydown', { key: 'c', ctrlKey: true, repeat: i > 0, bubbles: true, cancelable: true });
    h.w.document.body.dispatchEvent(ev); if (ev.defaultPrevented) blocked++;
  }
  assert.strictEqual(blocked, 5, `only ${blocked}/5 repeats of Ctrl+C were blocked`);
  h.w.close();
});

test('C2  1000 violations: exact counters, bounded logs, throttled localStorage', async () => {
  const h = await boot();
  let writes = 0; const orig = h.w.Storage.prototype.setItem;
  h.w.Storage.prototype.setItem = function (k, v) { if (String(k).startsWith('telemetry_')) writes++; return orig.call(this, k, v); };
  const t0 = Date.now();
  for (let i = 0; i < 1000; i++) h.w.document.body.dispatchEvent(new h.w.Event('copy', { bubbles: true, cancelable: true }));
  const ms = Date.now() - t0;
  const logs = h.w.getProctorLogs();
  assert.strictEqual(logs.total_copy_attempts, 1000, 'counter must stay exact');
  assert(logs.events.length <= 300, `${logs.events.length} events retained (cap 300)`);
  const per = Object.values(logs.question_violations).reduce((m, q) => Math.max(m, q.violations.length), 0);
  assert(per <= 30, `${per} violations retained for one question (cap 30)`);
  assert(writes <= 4, `${writes} localStorage writes for 1000 events (throttle to <= 4)`);
  console.log(`      (1000 events took ${ms} ms)`);
  h.w.close();
});

test('C3  last answer is saved BEFORE finish (select then submit immediately)', async () => {
  const h = await boot();
  const v = choose(h.w, 'q1', 1);
  h.w.document.getElementById('assessmentForm').dispatchEvent(new h.w.Event('submit', { cancelable: true }));
  await sleep(1800);
  const order = h.calls.map(c => c.url || '').filter(u => /\/api\/(save|finish)/.test(u));
  const s = saveCalls(h.calls)[0];
  assert(s && s.body.selected_option === v, 'last answer was never sent to /api/save');
  assert(order.indexOf('/api/save') < order.indexOf('/api/finish'), `order was ${order.join(' -> ')}`);
  h.w.close();
});

test('C4  expiry timer + auto-submitted save response => exactly one /api/finish', async () => {
  const h = await boot({
    state: { time_remaining: 1 },
    backend: null,
    handler: async rec => {
      if (rec.url.includes('/api/save')) return { status: 200, body: { status: 'submitted', auto_submitted: true, score: '3/15' }, delay: 500 };
      if (rec.url.includes('/api/finish')) return { status: 200, body: { status: 'submitted', score: '3/15', set_name: 'SET A', time_taken_sec: 60 }, delay: 100 };
    } });
  choose(h.w, 'q1', 0);
  await sleep(3500);
  const n = finishCalls(h.calls).length;
  assert.strictEqual(n, 1, `${n} /api/finish calls`);
  h.w.close();
});

test('C5  saves for one question are strictly ordered (<=1 in flight)', async () => {
  let inflight = 0, maxInflight = 0;
  const h = await boot({ handler: async rec => {
    if (!rec.url.includes('/api/save')) return;
    inflight++; maxInflight = Math.max(maxInflight, inflight);
    await sleep(1500); inflight--;
    return { status: 200, body: { status: 'saved', time_remaining: 1400 } };
  } });
  choose(h.w, 'q1', 0); await sleep(1000);   // first save goes out at ~0.8s and takes 1.5s
  choose(h.w, 'q1', 1); await sleep(3500);   // newer answer must wait for it, then be sent
  const saves = saveCalls(h.calls);
  assert.strictEqual(maxInflight, 1, `${maxInflight} saves for q1 were in flight at once`);
  assert.strictEqual(saves[saves.length - 1].body.selected_option, h.w.document.querySelectorAll('input[name="q1"]')[1].value, 'newest answer must be the last one sent');
  h.w.close();
});

test('C6  a failed save is retried until the server accepts it', async () => {
  let n = 0;
  const h = await boot({ handler: async rec => { if (rec.url.includes('/api/save') && ++n <= 2) return { status: 503, body: {} }; } });
  choose(h.w, 'q1', 0);
  await sleep(4500);
  const ok = saveCalls(h.calls).filter(c => c.status === 200).length;
  assert(ok >= 1, `save never succeeded after ${saveCalls(h.calls).length} attempts`);
  h.w.close();
});

test('C7  a lost proctoring sync is retried (strike must reach the server)', async () => {
  let n = 0;
  const h = await boot({ handler: async rec => { if (rec.url.includes('/api/proctoring') && ++n === 1) return { status: 503, body: {} }; } });
  await armProctoring(h);
  h.w.__exitFullscreen();
  await sleep(3500);
  const ps = h.calls.filter(c => c.url && c.url.includes('/api/proctoring'));
  assert(ps.some(c => c.status === 200 && c.body.fullscreen_exits === 1), `strike never acknowledged (${ps.length} attempts: ${ps.map(p => p.status).join(',')})`);
  h.w.close();
});

test('C8  network blip on /api/state does not drop candidate to the login screen', async () => {
  let n = 0;
  const h = await boot({ settle: 150, handler: async rec => { if (rec.url.includes('/api/state') && ++n === 1) return { reject: true }; } });
  await sleep(3500);
  const notice = h.w.document.getElementById('loginStatusNotice').innerHTML;
  assert(/Verified Candidate/.test(notice), `still showing: ${notice.replace(/<[^>]+>/g, '').slice(0, 80)}`);
  h.w.close();
});

test('C9  server busy (503) on /api/state is retried, session restored', async () => {
  let n = 0;
  const h = await boot({ settle: 150, handler: async rec => { if (rec.url.includes('/api/state') && ++n <= 2) return { status: 503, body: {} }; } });
  await sleep(4500);
  const notice = h.w.document.getElementById('loginStatusNotice').innerHTML;
  assert(/Verified Candidate/.test(notice), `still showing: ${notice.replace(/<[^>]+>/g, '').slice(0, 80)}`);
  h.w.close();
});

test('C10 save response "locked" locks the page immediately', async () => {
  const h = await boot({ handler: async rec => { if (rec.url.includes('/api/save')) return { status: 200, body: { status: 'saved', locked: true, time_remaining: 1400 } }; } });
  choose(h.w, 'q1', 0);
  await sleep(1500);
  const overlay = h.w.document.getElementById('securityWarningOverlay');
  assert(/Permanently Locked/.test(overlay.innerHTML), 'page was not locked after server reported locked');
  h.w.close();
});

(async () => {
  const only = process.argv[2];
  let pass = 0, fail = 0;
  for (const [name, fn] of tests) {
    if (only && !name.startsWith(only)) continue;
    try { await fn(); console.log('PASS ' + name); pass++; }
    catch (e) { console.log('FAIL ' + name + '\n      ' + String(e.message).split('\n')[0]); fail++; }
  }
  console.log(`\n${pass} passed, ${fail} failed  [${process.env.INDEX_HTML || 'project index.html'}]`);
  process.exit(0);
})();
