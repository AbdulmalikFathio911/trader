// Smoke test of the built page in jsdom, with stand-ins for the Claude page capabilities.
// Optional: needs jsdom (npm i --no-save jsdom@24.1.0). Run: node ui/tests/smoke.js
const fs = require('fs');
const path = require('path');
const UI = path.join(__dirname, '..');
const ROOT = path.join(UI, '..') + path.sep;
const { JSDOM } = require('jsdom');
const html = fs.readFileSync(path.join(UI, 'index.html'), 'utf8');

const writes = [];
const errors = [];
let sampleReply = null;
let sampleCalls = 0;
let lastPrompt = '';

function fakeDb() {
  const snap = (exists, data) => ({ exists, data: () => data, id: 'x', metadata: {} });
  return {
    doc: (p) => ({
      get: async () => snap(false, undefined),
      set: async (body) => { writes.push(['set', p, body]); },
      delete: async () => { writes.push(['delete', p]); },
    }),
    collection: () => ({ limit: () => ({ get: async () => ({ docs: [], size: 0, empty: true }) }) }),
  };
}
function fakeSample() {
  const fn = async () => ({ text: '{}', truncated: false });
  fn.json = async (input, opts) => {
    sampleCalls++;
    lastPrompt = input;
    if (!Array.isArray(opts.images) || !opts.images.length) throw { code: 'invalid_request', message: 'no images' };
    if (opts.onText) opts.onText({ text: 'x', delta: 'x' });
    return JSON.parse(JSON.stringify(sampleReply));
  };
  fn.limits = async () => ({ maxPromptBytes: 262144, images: { maxCount: 4, maxInputBytes: 2e7, mediaTypes: ['image/png', 'image/jpeg'] } });
  return fn;
}

const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'https://example.invalid/',
  beforeParse(window) {
    window.HTMLElement.prototype.scrollIntoView = function () {};
    window.claude = { use: async (name) => (name === 'sample' ? fakeSample() : name === 'db' ? fakeDb() : null) };
    window.addEventListener('error', (e) => errors.push(String(e.error || e.message)));
    window.addEventListener('unhandledrejection', (e) => errors.push('unhandled: ' + JSON.stringify(e.reason)));
  },
});
const { window } = dom;
const doc = window.document;
const $ = (id) => doc.getElementById(id);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const text = () => $('result').textContent;
const checks = [];
const check = (name, ok, detail) => { checks.push([name, !!ok]); if (!ok) console.log('FAIL', name, String(detail || '').slice(0, 400)); };
function type(id, value) { $(id).value = value; $(id).dispatchEvent(new window.Event('input', { bubbles: true })); }
function pickFiles(n) {
  const files = Array.from({ length: n }, (_, i) => new window.File(['x'], 'shot' + i + '.png', { type: 'image/png' }));
  Object.defineProperty($('files'), 'files', { value: files, configurable: true });
  $('files').dispatchEvent(new window.Event('change', { bubbles: true }));
}
const ticket = () => ($('ticket-text') ? $('ticket-text').textContent : '');

(async () => {
  await wait(300);
  // 1. at rest: photo mode is the first screen, with an example ticket that fails on margin
  check('starts on the desk in photo mode', !$('view-desk').hidden && $('view-journal').hidden && !$('panel-ai').hidden && $('panel-manual').hidden);
  check('rest shows no-trade stamp', $('result').querySelector('.stamp').textContent === 'لا صفقة' && text().includes('MARGIN_EXCEEDS_FREE_MARGIN'), text());
  check('rest margin numbers', text().includes('74.00') && text().includes('-47.27'));
  check('rest marked example', text().includes('مثال'));
  check('account pill', $('pill-balance').textContent === '102' && $('pill-free').textContent === '26.73');
  check('status chips', $('status').textContent.includes('التحليل بالصور: متاح') && $('status').textContent.includes('الحفظ: سحابي'), $('status').textContent);

  // 2. the account pill opens the setup view; free the margin there
  $('acct-pill').click();
  check('pill opens setup', !$('view-setup').hidden && $('view-desk').hidden);
  type('acc-free', '102');
  check('pill follows the account', $('pill-free').textContent === '102');

  // 3. manual mode: live ticket, unknown open positions block, one tap fixes it
  $('nav-desk').click();
  $('tab-manual').click();
  check('manual panel shown', !$('panel-manual').hidden && $('panel-ai').hidden);
  type('man-entry', '1.1100');
  check('unknown open risk blocks', text().includes('OPEN_RISK_UNKNOWN') && !!$('fix-nopos'), text());
  $('fix-nopos').click();
  check('one-tap fix gives a ticket', $('result').querySelector('.stamp').textContent === 'تذكرة جاهزة' &&
    ticket().includes('Type:        Sell Limit') && ticket().includes('Volume:      0.01'), text());
  check('ticket rows', Array.from($('result').querySelectorAll('.lines dd')).map((d) => d.textContent).join('|') === '0.01|1.1100|1.1110|1.1080');
  check('stub numbers', text().includes('2.00') && text().includes('28.00 USD') && text().includes('of 6.12 USD allowed'));
  check('unconfirmed spec warning', text().includes('غير مؤكدة'));
  check('copy button present', !!$('btn-copy'));

  // 4. reward:risk gate updates as the target is typed
  type('man-target', '1.1090');
  check('rr gate blocks', text().includes('REWARD_RISK') && text().includes('1.0000'), text());

  // 5. gold: the minimum lot is too big
  doc.querySelector('#sym-chips [data-sym="XAUUSD"]').click();
  type('man-entry', '3900'); type('man-stop', '3930'); type('man-target', '3850'); type('man-current', '3874.70');
  check('gold no trade', text().includes('LOTS_BELOW_MIN') && text().includes('3901.02') && text().includes('30.00'), text());

  // 6. stock buy: share count
  doc.querySelector('#sym-chips [data-sym="F"]').click();
  $('side-buy').click();
  type('man-entry', '11.93'); type('man-stop', '11.42'); type('man-target', '12.95'); type('man-current', '11.93');
  check('stock OK 2 shares', ticket().includes('Volume:      2') && ticket().includes('Buy Market'), text());

  // 7. a symbol without a specification offers the setup shortcut
  sampleReply = {
    images: [{ n: 1, kind: 'chart', symbol: 'GBPUSD', timeframe: 'H4', bid: '1.2500', ask: null, visible_high: '1.26', visible_low: '1.24', order_lines: [], shown_time: null }],
    account: null, specification: null, charts: [],
    setup: { symbol: 'GBPUSD', highest_timeframe: 'H4', decision: 'candidate', failed_gate: null, reason_ar: '', side: 'sell', entry: '1.2550', stop: '1.2570', target: '1.2500', base_estimate_pct: 55, warnings_ar: [] },
    opinion_ar: '',
  };
  $('tab-ai').click();
  pickFiles(1);
  await wait(20);
  check('run enabled', !$('btn-run').disabled);
  $('btn-run').click();
  await wait(100);
  check('missing spec offers a shortcut', text().includes('مواصفات هذا الرمز غير موجودة') && !!$('fix-spec'), text());
  $('fix-spec').click();
  check('shortcut opens the symbol setup', !$('view-setup').hidden && $('fold-symbols').open && $('sym-new').value === 'GBPUSD');
  $('nav-desk').click();

  // 8. photo mode: candidate setup with a Trade tab
  sampleReply = {
    images: [
      { n: 1, kind: 'chart', symbol: 'EURUSD', timeframe: 'H4', bid: '1.1057', ask: null, visible_high: '1.1108', visible_low: '1.0990', order_lines: [], shown_time: null },
      { n: 2, kind: 'trade_tab' },
    ],
    account: { balance: '102.00', equity: '102.00', margin: '0.00', free_margin: '102.00', positions: [] },
    specification: null,
    charts: [{ symbol: 'EURUSD', timeframe: 'H4', weaker_evidence: true, trend: 'down', strength: 'strong', trend_ar: 'قمم وقيعان هابطة',
      supports: [{ price: '1.1078', why_ar: 'قاع سابق' }], resistances: [{ price: '1.1098', why_ar: 'مستوى مكسور' }],
      moving_averages_ar: 'غير ظاهرة', volume_ar: 'غير ظاهر', patterns_ar: [], assessment_ar: 'الاتجاه هابط',
      scenarios: [{ name_ar: 'استمرار الهبوط', direction: 'down', estimate_pct: 55, targets: ['1.1078'], invalidation: '1.1108' },
                  { name_ar: 'ارتداد', direction: 'up', estimate_pct: 45, targets: ['1.1150'], invalidation: '1.0990' }] }],
    setup: { symbol: 'EURUSD', highest_timeframe: 'H4', decision: 'candidate', failed_gate: null, reason_ar: '', side: 'sell',
             entry: '1.1098', stop: '1.1108', target: '1.1078', base_estimate_pct: 55, warnings_ar: [] },
    opinion_ar: 'الاتجاه هابط على الفريم المتاح.',
  };
  pickFiles(1);
  await wait(20);
  $('btn-run').click();
  await wait(100);
  check('photo OK ticket', $('result').querySelector('.stamp').textContent === 'تذكرة جاهزة' && ticket().includes('Price:       1.1098') && ticket().includes('Sell Limit'), text());
  check('photo margin 73.99', text().includes('73.99'));
  check('photo evidence and opinion', text().includes('دليل: ما قُرئ من الصور') && text().includes('رأي: تقدير وليس قياساً') && text().includes('an estimate, not a statistic'));
  check('photo weekly warning', text().includes('لا يوجد شارت أسبوعي'));
  check('journal card and ticket id', $('journal-list').textContent.includes('EURUSD Sell Limit') && text().includes('Ticket id'));
  check('journal badge counts open tickets', $('nav-count').textContent === '1', $('nav-count').textContent);
  check('db journal write', writes.some((w) => w[0] === 'set' && w[1].startsWith('journal/') && w[2].verdict === 'OK'));
  check('working panel hidden again', $('working').hidden && !$('btn-run').hidden);

  // 9. photo mode: a gate fails
  sampleReply.setup = { symbol: 'EURUSD', highest_timeframe: 'H4', decision: 'no_trade', failed_gate: 1, reason_ar: 'الفريم الأعلى عرضي.', side: null, entry: null, stop: null, target: null, base_estimate_pct: 40, warnings_ar: [] };
  $('btn-run').click();
  await wait(100);
  check('photo gate no trade', $('result').querySelector('.stamp').textContent === 'لا صفقة' && text().includes('GATE 1') && text().includes('الفريم الأعلى عرضي'), text());

  // 10. journal view: record a result, statistics appear
  $('nav-journal').click();
  check('journal view shown', !$('view-journal').hidden);
  doc.querySelector('#journal-list .jcard.ok [data-result="win"]').click();
  check('stats', $('stats').textContent.includes('100.0%') && $('stats').textContent.includes('33.3%') && $('stats-note').textContent.includes('ثلاثين'), $('stats').textContent);
  check('badge cleared', $('nav-count').textContent === '');

  // 11. the brain: every skill file reaches the model verbatim
  const SKILL_FILES = ['CLAUDE.md', '.claude/skills/trade/SKILL.md', '.claude/skills/account/SKILL.md',
    '.claude/skills/technical-analyst/SKILL.md', '.claude/skills/technical-analyst/references/technical_analysis_framework.md',
    '.claude/skills/technical-analyst/assets/analysis_template.md', '.claude/skills/mt5-lot-calculator/SKILL.md',
    '.claude/skills/position-sizer/SKILL.md', '.claude/skills/position-sizer/references/sizing_methodologies.md'];
  const missing = SKILL_FILES.filter((f) => !lastPrompt.includes(fs.readFileSync(ROOT + f, 'utf8')));
  check('prompt carries all 9 skill files verbatim', missing.length === 0, missing.join(', '));
  check('prompt under the 256 KiB cap', Buffer.byteLength(lastPrompt, 'utf8') < 262144, Buffer.byteLength(lastPrompt, 'utf8'));
  check('skills card lists 9 files', $('skills').querySelectorAll('details').length === 9 && $('skills').textContent.includes('.claude/skills/trade/SKILL.md'));

  await wait(900);
  check('db account write', writes.some((w) => w[1] === 'state/account' && w[2].free_margin === '102.00' && Array.isArray(w[2].open_positions)));
  check('no script errors', errors.length === 0, errors.join(' | '));
  check('sample calls', sampleCalls === 3, sampleCalls);

  const failed = checks.filter((c) => !c[1]);
  console.log(`checks: ${checks.length}  failed: ${failed.length}`);
  process.exit(failed.length ? 1 : 0);
})();
