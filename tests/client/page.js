// Boots the REAL index.html in jsdom with a recording fake backend.
const fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');
const path = require('path');
const ROOT = path.resolve(__dirname, '..', '..');
const HTML = process.env.INDEX_HTML || path.join(ROOT, 'index.html');
const CHALLENGES = JSON.parse(fs.readFileSync(path.join(ROOT, 'challenges.json'), 'utf8'));
const sleep = ms => new Promise(r => setTimeout(r, ms));

const defaultState = () => ({ authenticated: true, session_id: 's1', name: 'T', email: 't@x.edu', usn: '1', branch_sem: 'CS',
  challenge_id: 'set_a', set_name: 'SET A', time_remaining: 1500, duration_seconds: 1500, status: 'in_progress',
  answers: {}, fullscreen_exits: 0, tab_switches: 0, copy_attempts: 0, paste_attempts: 0, ctrl_cmd_attempts: 0,
  text_selection_attempts: 0, integrity_risk: 'LOW / CLEAN', current_question: 'q1' });

function defaultReply(url) {
  if (url.includes('/api/state')) return { status: 200, body: defaultState() };
  if (url.includes('challenges.json')) return { status: 200, body: CHALLENGES };
  if (url.includes('/api/proctoring')) return { status: 200, body: { status: 'telemetry_recorded', locked: false } };
  if (url.includes('/api/save')) return { status: 200, body: { status: 'saved', time_remaining: 1400 } };
  if (url.includes('/api/finish')) return { status: 200, body: { status: 'submitted', score: '5/15', set_name: 'SET A', time_taken_sec: 60 } };
  return { status: 200, body: {} };
}

// opts.handler(rec) may return {status, body, delay} (or a Promise of it) to override the default reply;
// return undefined to fall through to the default. opts.state patches the /api/state payload.
async function boot(opts = {}) {
  const calls = [], errors = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', e => errors.push(String(e.message || e)));
  if (opts.showConsole) vc.sendTo(console);
  let fsEl = null, dom;
  const fire = (w, n) => w.document.dispatchEvent(new w.Event(n));
  dom = new JSDOM(fs.readFileSync(HTML, 'utf8'), {
    url: 'http://localhost:8080/', runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc,
    beforeParse(w) {
      Object.defineProperty(w.document, 'fullscreenElement', { get: () => fsEl, configurable: true });
      w.Element.prototype.requestFullscreen = function () { fsEl = this; fire(w, 'fullscreenchange'); return Promise.resolve(); };
      w.__exitFullscreen = () => { fsEl = null; fire(w, 'fullscreenchange'); };
      w.document.hasFocus = () => true;
      w.alert = m => calls.push({ alert: String(m) }); w.confirm = () => true;
      w.fetch = async (url, init = {}) => {
        const rec = { url: String(url), method: init.method || 'GET', body: init.body ? JSON.parse(init.body) : null, t: Date.now() };
        calls.push(rec);
        let r = (opts.handler && await opts.handler(rec)) || defaultReply(rec.url);
        if (rec.url.includes('/api/state') && opts.state && r.status === 200) r = { status: 200, body: Object.assign(r.body, opts.state) };
        if (r.delay) await sleep(r.delay);
        if (r.reject) throw new Error('network down');
        rec.status = r.status;
        return { ok: r.status >= 200 && r.status < 300, status: r.status, json: async () => r.body };
      };
      w.navigator.sendBeacon = (u, b) => { calls.push({ url: u, beacon: true }); return true; };
    },
  });
  const w = dom.window;
  await sleep(opts.settle || 250);   // DOMContentLoaded + /api/state + challenges.json
  return { w, calls, errors, dom, sleep, CHALLENGES, enterFullscreen: () => w.document.documentElement.requestFullscreen() };
}
module.exports = { boot, sleep };
