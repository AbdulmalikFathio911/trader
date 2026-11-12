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
    doc: (path) => ({
      get: async () => snap(false, undefined),
      set: async (body) => { writes.push(['set', path, body]); },
      delete: async () => { writes.push(['delete', path]); },
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
const check = (name, ok, detail) => { checks.push([name, !!ok]); if (!ok) console.log('FAIL', name, detail || ''); };
function type(id, value) { $(id).value = value; $(id).dispatchEvent(new window.Event('input', { bubbles: true })); }
function pickFiles(n) {
  const files = Array.from({ length: n }, (_, i) => new window.File(['x'], 'shot' + i + '.png', { type: 'image/png' }));
  Object.defineProperty($('files'), 'files', { value: files, configurable: true });
  $('files').dispatchEvent(new window.Event('change', { bubbles: true }));
}

(async () => {
  await wait(300);
  // 1. at rest: an example that fails on margin
  check('rest shows no-trade', text().includes('لا صفقة') && text().includes('MARGIN_EXCEEDS_FREE_MARGIN'), text().slice(0, 300));
  check('rest margin numbers', text().includes('74.00') && text().includes('-47.27'));
  check('rest marked example', text().includes('مثال'));
  check('status chips', $('status').textContent.includes('التحليل بالصور: متاح') && $('status').textContent.includes('الحفظ: سحابي'), $('status').textContent);

  // 2. manual: free the margin, but open positions unknown -> still no trade
  type('acc-free', '102');
  $('form-manual').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  check('unknown open risk blocks', text().includes('OPEN_RISK_UNKNOWN'), text().slice(0, 300));
  $('btn-nopos').click();
  $('form-manual').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  check('manual OK ticket', text().includes('توجد صفقة مقترحة') && $('ticket-text') && $('ticket-text').textContent.includes('Type:        Sell Limit') && $('ticket-text').textContent.includes('Volume:      0.01'), text().slice(0, 400));
  check('manual numbers', text().includes('Reward:Risk') && text().includes('2.00') && text().includes('28.00') && text().includes('of 6.12 USD allowed'));
  check('unconfirmed spec warning', text().includes('غير مؤكدة'));

  // 3. reward:risk gate
  type('man-target', '1.1090');
  $('form-manual').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  check('rr gate blocks', text().includes('REWARD_RISK') && text().includes('1.0000'), text().slice(0, 300));

  // 4. gold: minimum lot too big
  type('man-target', '3850'); type('man-entry', '3900'); type('man-stop', '3930'); type('man-current', '3874.70');
  $('sym-select').value = 'XAUUSD'; $('sym-select').dispatchEvent(new window.Event('change', { bubbles: true }));
  $('form-manual').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  check('gold no trade', text().includes('LOTS_BELOW_MIN') && text().includes('3901.02') && text().includes('30.00'), text().slice(0, 400));

  // 5. stock buy: share count
  $('sym-select').value = 'F'; $('sym-select').dispatchEvent(new window.Event('change', { bubbles: true }));
  $('man-side').value = 'buy';
  type('man-entry', '11.93'); type('man-stop', '11.42'); type('man-target', '12.95'); type('man-current', '11.93');
  $('form-manual').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  check('stock OK 2 shares', $('ticket-text') && $('ticket-text').textContent.includes('Volume:      2') && $('ticket-text').textContent.includes('Buy Market'), text().slice(0, 400));

  // 6. image mode: candidate setup, Trade tab read
  $('tab-ai').click();
  pickFiles(2);
  await wait(20);
  check('run enabled', !$('btn-run').disabled);
  sampleReply = {
    images: [
      { n: 1, kind: 'chart', symbol: 'EURUSD', timeframe: 'H4', bid: '1.1057', ask: null, visible_high: '1.1108', visible_low: '1.0990', order_lines: [], shown_time: null },
      { n: 2, kind: 'trade_tab' },
    ],
    account: { balance: '102.00', equity: '102.00', margin: '0.00', free_margin: '102.00', positions: [] },
    specification: null,
    charts: [{ symbol: 'EURUSD', timeframe: 'H4', weaker_evidence: true, trend: 'down', strength: 'strong',
      supports: [{ price: '1.1078', why_ar: 'قاع سابق' }], resistances: [{ price: '1.1098', why_ar: 'مستوى مكسور' }],
      patterns_ar: [], not_visible_ar: ['الحجم غير ظاهر'],
      scenarios: [{ name_ar: 'استمرار الهبوط', direction: 'down', estimate_pct: 55, targets: ['1.1078'], invalidation: '1.1108' },
                  { name_ar: 'ارتداد', direction: 'up', estimate_pct: 45, targets: ['1.1150'], invalidation: '1.0990' }] }],
    setup: { symbol: 'EURUSD', highest_timeframe: 'H4', decision: 'candidate', failed_gate: null, reason_ar: '', side: 'sell',
             entry: '1.1098', stop: '1.1108', target: '1.1078', base_estimate_pct: 55, warnings_ar: [] },
    opinion_ar: 'الاتجاه هابط على الفريم المتاح.',
  };
  $('btn-run').click();
  await wait(100);
  check('ai OK ticket', $('ticket-text') && $('ticket-text').textContent.includes('Price:       1.1098') && $('ticket-text').textContent.includes('Sell Limit'), text().slice(0, 500));
  check('ai margin 73.99', text().includes('73.99'));
  check('ai evidence + opinion', text().includes('دليل: ما قُرئ من الصور') && text().includes('رأي: تقدير وليس قياساً') && text().includes('an estimate, not a statistic'));
  check('ai weekly warning', text().includes('لا يوجد شارت أسبوعي'));
  check('ai one-sided price warning absent (bid present)', !text().includes('غير مقروء، فاستُعمل'));
  check('journal row', $('journal-body').textContent.includes('EURUSD Sell Limit') && text().includes('Ticket id'));
  check('db journal write', writes.some((w) => w[0] === 'set' && w[1].startsWith('journal/') && w[2].verdict === 'OK'), JSON.stringify(writes.map((w) => w[1])));

  // 7. image mode: a gate fails
  sampleReply.setup = { symbol: 'EURUSD', highest_timeframe: 'H4', decision: 'no_trade', failed_gate: 1, reason_ar: 'الفريم الأعلى عرضي.', side: null, entry: null, stop: null, target: null, base_estimate_pct: 40, warnings_ar: [] };
  $('btn-run').click();
  await wait(100);
  check('ai gate no trade', text().includes('لا صفقة') && text().includes('GATE 1') && text().includes('الفريم الأعلى عرضي'), text().slice(0, 300));

  // 8. journal: record a result, statistics appear
  const firstOk = Array.from($('journal-body').querySelectorAll('select')).find((s) => !s.disabled);
  firstOk.value = 'win'; firstOk.dispatchEvent(new window.Event('change', { bubbles: true }));
  check('stats', $('stats').textContent.includes('Win rate') && $('stats').textContent.includes('100.0%') && $('stats').textContent.includes('ثلاثين'), $('stats').textContent);

  // 9. the brain: every skill file reaches the model verbatim
  const SKILL_FILES = ['CLAUDE.md', '.claude/skills/trade/SKILL.md', '.claude/skills/account/SKILL.md',
    '.claude/skills/technical-analyst/SKILL.md', '.claude/skills/technical-analyst/references/technical_analysis_framework.md',
    '.claude/skills/technical-analyst/assets/analysis_template.md', '.claude/skills/mt5-lot-calculator/SKILL.md',
    '.claude/skills/position-sizer/SKILL.md', '.claude/skills/position-sizer/references/sizing_methodologies.md'];
  const missing = SKILL_FILES.filter((f) => !lastPrompt.includes(fs.readFileSync(ROOT + f, 'utf8')));
  check('prompt carries all 9 skill files verbatim', missing.length === 0, missing.join(', '));
  check('prompt under the 256 KiB cap', Buffer.byteLength(lastPrompt, 'utf8') < 262144, Buffer.byteLength(lastPrompt, 'utf8'));
  check('skills card lists 9 files', $('skills').querySelectorAll('details').length === 9 && $('skills').textContent.includes('.claude/skills/trade/SKILL.md'));
  console.log('prompt bytes:', Buffer.byteLength(lastPrompt, 'utf8'));

  await wait(900);
  check('db account write', writes.some((w) => w[1] === 'state/account' && w[2].free_margin === '102.00' && Array.isArray(w[2].open_positions)));
  check('no script errors', errors.length === 0, errors.join(' | '));
  check('sample calls', sampleCalls === 2, sampleCalls);

  const failed = checks.filter((c) => !c[1]);
  console.log(`checks: ${checks.length}  failed: ${failed.length}`);
  process.exit(failed.length ? 1 : 0);
})();
