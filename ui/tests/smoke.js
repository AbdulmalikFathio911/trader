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
let sampleQueue = [];
let extraCalls = 0, extraImages = 0, lastImages = 0, extraReply = null, appliedTier = '';
let reviewReply = null;
let sampleCalls = 0;
let reviewCalls = 0;
let lastPrompt = '';
const tiers = [];

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
  const fn = async (input, opts) => {
    if (!Array.isArray(opts.images) || !opts.images.length) throw { code: 'invalid_request', message: 'no images' };
    if (input.startsWith('You read extra screenshots')) {
      extraCalls++;
      extraImages = opts.images.length;
      if (extraReply && extraReply.__error) throw extraReply.__error;
      return { text: 'Here it is:\n```json\n' + JSON.stringify(extraReply) + '\n```', truncated: false, modelTierApplied: opts.modelTier };
    }
    sampleCalls++;
    lastPrompt = input;
    lastImages = opts.images.length;
    tiers.push(opts.modelTier);
    if (opts.onText) opts.onText({ text: 'x', delta: 'x' });
    const reply = sampleQueue.length ? sampleQueue.shift() : sampleReply;
    if (reply && reply.__error) throw reply.__error;
    return { text: JSON.stringify(reply), truncated: false, modelTierApplied: appliedTier || opts.modelTier };
  };
  fn.json = async (input, opts) => {
    if (!Array.isArray(opts.images) || !opts.images.length) throw { code: 'invalid_request', message: 'no images' };
    if (input.startsWith('You review one CLOSED')) { reviewCalls++; return JSON.parse(JSON.stringify(reviewReply)); }
    throw { code: 'invalid_request', message: 'unexpected json call' };
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
const stamp = () => $('result').querySelector('.stamp').textContent;
const ticket = () => ($('ticket-text') ? $('ticket-text').textContent : '');
const checks = [];
const check = (name, ok, detail) => { checks.push([name, !!ok]); if (!ok) console.log('FAIL', name, String(detail === undefined ? '' : detail).slice(0, 500)); };
function type(id, value) { $(id).value = value; $(id).dispatchEvent(new window.Event('input', { bubbles: true })); }
function pickFiles(n, id) {
  const files = Array.from({ length: n }, (_, i) => new window.File(['x'], 'shot' + i + '.png', { type: 'image/png' }));
  Object.defineProperty($(id || 'files'), 'files', { value: files, configurable: true });
  $(id || 'files').dispatchEvent(new window.Event('change', { bubbles: true }));
}
async function analyse() { pickFiles(1); await wait(20); $('btn-run').click(); await wait(120); }
const card = (id) => doc.querySelector('#journal-list .jcard[data-id="' + id + '"]');

// One analysed EURUSD H4 chart: a sell at resistance 1.1098, invalidation 1.1105, stop 1.1108, target 1.1078.
function eurusd(overrides) {
  const base = {
    images: [
      { n: 1, kind: 'chart', symbol: 'EURUSD', timeframe: 'H4', bid: '1.1057', ask: null, visible_high: '1.1108', visible_low: '1.0990', order_lines: [], shown_time: null },
      { n: 2, kind: 'trade_tab' },
    ],
    account: { balance: '102.00', equity: '102.00', margin: '0.00', free_margin: '102.00', positions: [] },
    specification: null,
    charts: [{ symbol: 'EURUSD', timeframe: 'H4', weaker_evidence: true, trend: 'down', strength: 'strong', trend_ar: 'قمم وقيعان هابطة',
      supports: [{ price: '1.1078', why_ar: 'قاع سابق' }], resistances: [{ price: '1.1098', why_ar: 'مستوى مكسور' }],
      moving_averages_ar: 'غير ظاهرة', volume_ar: 'غير ظاهر', patterns_ar: [], assessment_ar: 'الاتجاه هابط',
      scenarios: [{ name_ar: 'استمرار الهبوط', direction: 'down', estimate_pct: 55, targets: ['1.1078'], invalidation: '1.1105' },
                  { name_ar: 'ارتداد', direction: 'up', estimate_pct: 45, targets: ['1.1150'], invalidation: '1.0990' }] }],
    setup: { symbol: 'EURUSD', highest_timeframe: 'H4', decision: 'candidate', failed_gate: null, reason_ar: '', side: 'sell',
             stop: '1.1108', candidates: [{ entry: '1.1098', target: '1.1078', why_ar: 'مقاومة' }], base_estimate_pct: 55, warnings_ar: [] },
    opinion_ar: 'الاتجاه هابط على الفريم المتاح.',
  };
  const copy = JSON.parse(JSON.stringify(base));
  if (overrides) overrides(copy);
  return copy;
}

(async () => {
  await wait(300);
  // 1. at rest
  check('starts on the desk in photo mode', !$('view-desk').hidden && $('view-journal').hidden && !$('panel-ai').hidden && $('panel-manual').hidden);
  check('rest shows no-trade stamp', stamp() === 'لا صفقة' && text().includes('MARGIN_EXCEEDS_FREE_MARGIN'), text());
  check('rest marked example', text().includes('مثال'));
  check('run button says what is missing', $('btn-run').disabled && $('btn-run').textContent === 'اختر صورة أولاً', $('btn-run').textContent);
  check('status chips', $('status').textContent.includes('التحليل بالصور: متاح') && $('status').textContent.includes('الحفظ: سحابي'), $('status').textContent);
  check('first-use banner shown', !$('intro').hidden);

  // 2. setup: validation and the account pill
  $('acct-pill').click();
  check('pill opens setup', !$('view-setup').hidden && $('view-desk').hidden);
  type('acc-balance', 'x');
  check('setup marks a bad number', $('acc-balance').getAttribute('aria-invalid') === 'true' && !$('acc-errors').hidden);
  type('acc-balance', '102');
  check('setup clears the mark', $('acc-balance').getAttribute('aria-invalid') === 'false' && $('acc-errors').hidden);
  type('acc-free', '102');
  check('pill follows the account', $('pill-free').textContent === '102');

  // 3. manual mode: incomplete, invalid, blocked, fixed
  $('nav-desk').click();
  $('tab-manual').click();
  type('man-entry', '');
  check('incomplete numbers are not an error', stamp() === 'أكمل الأرقام' && $('man-errors').hidden, stamp());
  type('man-entry', '1.1100');
  type('man-stop', 'abc');
  check('bad field is pointed at', $('man-stop').getAttribute('aria-invalid') === 'true' && !$('man-errors').hidden && stamp() === 'أرقام ناقصة', stamp());
  type('man-stop', '1.1090');
  check('wrong-side stop is pointed at', $('man-stop').getAttribute('aria-invalid') === 'true' && $('man-errors').textContent.includes('الجهة الخطأ'), $('man-errors').textContent);
  type('man-stop', '1.1110');
  check('unknown open risk blocks', text().includes('OPEN_RISK_UNKNOWN') && !!$('fix-nopos'), text());
  $('fix-nopos').click();
  check('one-tap fix gives a ticket', stamp() === 'تذكرة جاهزة' && ticket().includes('Type:        Sell Limit') && ticket().includes('Volume:      0.01'), text());
  check('ticket rows', Array.from($('result').querySelectorAll('.lines dd')).map((d) => d.textContent).join('|') === '0.01|1.1100|1.1110|1.1080');
  check('stub numbers', text().includes('28.00 USD') && text().includes('of 6.12 USD allowed'));
  check('unconfirmed spec warning', text().includes('غير مؤكدة'));
  check('manual ticket has no age', !$('ticket-age'));

  // 4. news lock
  $('news-lock').click();
  check('news lock blocks', stamp() === 'لا صفقة' && text().includes('NEWS_LOCK') && $('news-lock').getAttribute('aria-pressed') === 'true' && $('news-left').textContent === '120', text());
  $('news-lock').click();
  check('news lock off again', stamp() === 'تذكرة جاهزة' && $('news-lock').getAttribute('aria-pressed') === 'false');
  $('btn-journal').click();
  check('manual ticket journaled', !!card(1) && $('nav-count').textContent === '1');

  // 5. gates of the calculator
  type('man-target', '1.1090');
  check('rr gate blocks', text().includes('REWARD_RISK') && text().includes('1.0000'), text());
  doc.querySelector('#sym-chips [data-sym="XAUUSD"]').click();
  type('man-entry', '3900'); type('man-stop', '3930'); type('man-target', '3850'); type('man-current', '3874.70');
  check('gold no trade', text().includes('LOTS_BELOW_MIN') && text().includes('3901.02') && text().includes('30.00'), text());
  doc.querySelector('#sym-chips [data-sym="F"]').click();
  $('side-buy').click();
  type('man-entry', '11.93'); type('man-stop', '11.42'); type('man-target', '12.95'); type('man-current', '11.93');
  check('stock OK 2 shares', ticket().includes('Volume:      2') && ticket().includes('Buy Market'), text());

  // 6. photos: a symbol without a specification offers the setup shortcut (one reading only)
  $('tab-ai').click();
  sampleReply = eurusd((d) => {
    d.images = [{ n: 1, kind: 'chart', symbol: 'GBPUSD', timeframe: 'H4', bid: '1.2500', ask: null, visible_high: '1.26', visible_low: '1.24', order_lines: [], shown_time: null }];
    d.account = null;
    d.charts[0].symbol = 'GBPUSD';
    d.charts[0].supports = [{ price: '1.2500', why_ar: 'قاع' }];
    d.charts[0].resistances = [{ price: '1.2550', why_ar: 'قمة' }];
    d.charts[0].scenarios[0].invalidation = '1.2560';
    d.setup.symbol = 'GBPUSD'; d.setup.stop = '1.2570';
    d.setup.candidates = [{ entry: '1.2550', target: '1.2500', why_ar: 'مقاومة' }];
  });
  await analyse();
  check('missing spec offers a shortcut', text().includes('مواصفات هذا الرمز غير موجودة') && !!$('fix-spec'), text());
  check('no second reading without a ticket', sampleCalls === 1, sampleCalls);
  $('fix-spec').click();
  check('shortcut opens the symbol setup', !$('view-setup').hidden && $('fold-symbols').open && $('sym-new').value === 'GBPUSD');
  $('nav-desk').click();

  // 7. photos: ticket through the second candidate, second reading agrees
  sampleReply = eurusd((d) => {
    d.images[0].order_lines = ['SELL LIMIT 0.02 at 4015.00'];
    d.setup.candidates = [{ entry: '1.1099', target: '1.1078', why_ar: 'ليس مستوى' }, { entry: '1.1098', target: '1.1078', why_ar: 'مقاومة' }];
  });
  await analyse();
  check('photo OK ticket', stamp() === 'تذكرة جاهزة' && ticket().includes('Price:       1.1098') && ticket().includes('Sell Limit'), text());
  check('two readings were made, strongest tier first', sampleCalls === 3 && tiers[1] === 'complex' && tiers[2] === 'default', sampleCalls + ' ' + tiers.join(','));
  check('photo margin 73.99', text().includes('73.99'));
  check('photo evidence and opinion', text().includes('دليل: ما قُرئ من الصور') && text().includes('رأي: تقدير وليس قياساً') && text().includes('an estimate, not a statistic'));
  check('weekly warning', text().includes('لا يوجد شارت أسبوعي'));
  check('order line warning', text().includes('يوجد على الشارت أمر') && text().includes('SELL LIMIT 0.02 at 4015.00'));
  check('skipped candidate warning', text().includes('المستوى التالي'));
  check('coverage chips', Array.from($('result').querySelectorAll('.cover span')).map((s) => s.className).join(',') === 'missing,yes,missing,yes,missing');
  check('news not checked is said', text().includes('لم تُفحص الأخبار') && text().includes('دليل: سياق السوق') && text().includes('no calendar screenshot'), text());
  check('ticket age shown', $('ticket-age') && $('ticket-age').textContent === '0' && !$('btn-copy').disabled);
  check('journal card with report', !!card(3) && card(3).textContent.includes('EURUSD Sell Limit') && card(3).textContent.includes('تقرير التحليل'));
  check('db journal write', writes.some((w) => w[0] === 'set' && w[1] === 'journal/3' && w[2].verdict === 'OK' && w[2].report && w[2].source === 'photos'));
  check('working panel hidden again', $('working').hidden && !$('btn-run').hidden);

  // 8. the ticket ages: after ten minutes it must be checked against the price again
  const realNow = window.Date.now.bind(window.Date);
  let shift = 11 * 60000;
  window.Date.now = () => realNow() + shift;
  type('acc-risk', '1');
  check('stale ticket asks for the price', stamp() === 'تحتاج تحققاً' && !!$('recheck-price') && $('btn-copy').disabled, stamp());
  $('recheck-price').value = 'abc'; $('btn-recheck').click();
  check('recheck validates its input', text().includes('اكتب السعر الحالي كرقم'));
  $('recheck-price').value = '1.1060'; $('btn-recheck').click();
  check('recheck keeps a valid ticket', stamp() === 'تذكرة جاهزة' && !$('btn-copy').disabled && $('ticket-age').textContent === '0' && !$('toast').hidden, stamp());
  shift = 22 * 60000;
  type('acc-risk', '1');
  $('recheck-price').value = '1.1102'; $('btn-recheck').click();
  check('recheck voids a crossed ticket', stamp() === 'لا صفقة' && text().includes('STALE_PRICE') && text().includes('Sell Stop'), text());
  window.Date.now = realNow;

  // 9. photos: the second reading disagrees
  sampleQueue = [eurusd(), eurusd((d) => { d.setup.decision = 'no_trade'; d.setup.failed_gate = 2; })];
  await analyse();
  check('disagreeing second reading blocks', stamp() === 'لا صفقة' && text().includes('SECOND_OPINION') && text().includes('no trade, gate 2'), text());
  check('journal keeps the reason', card(4) && card(4).textContent.includes('SECOND_OPINION'));

  // 10. photos: the second reading fails, then succeeds on the one-tap retry
  sampleQueue = [eurusd(), { __error: { code: 'rate_limited', message: 'x' } }];
  await analyse();
  check('failed second reading blocks', text().includes('SECOND_FAILED') && !!$('fix-second'), text());
  sampleReply = eurusd();
  $('fix-second').click();
  await wait(120);
  check('retrying the second reading gives the ticket', stamp() === 'تذكرة جاهزة', text());

  // 11. photos: the page re-checks the gates itself
  sampleReply = eurusd((d) => { d.setup.side = 'buy'; });
  await analyse();
  check('mechanical gate 1', stamp() === 'لا صفقة' && text().includes('GATE 1') && text().includes('Base direction'), text());
  sampleReply = eurusd((d) => { d.setup.stop = '1.1105'; });
  await analyse();
  check('mechanical gate 4', text().includes('GATE 4') && text().includes('Invalidation'), text());
  sampleReply = eurusd((d) => { d.setup.decision = 'no_trade'; d.setup.failed_gate = 1; d.setup.reason_ar = 'الفريم الأعلى عرضي.'; });
  await analyse();
  check('model gate no trade', text().includes('GATE 1') && text().includes('الفريم الأعلى عرضي'), text());

  // 11b. photos: the news analyst (calendar screenshot) can only block or warn
  const pad = (n) => String(n).padStart(2, '0');
  const at = (minutes) => { const d = new Date(Date.now() + minutes * 60000); return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes()); };
  const withNews = (events, extra) => eurusd((d) => {
    d.images.push({ n: d.images.length + 1, kind: 'calendar' });
    d.news = Object.assign({ checked: true, source_image: d.images.length, events: events, context_ar: 'تقويم اليوم.', against_trade: false }, extra || {});
  });
  let callsBefore = sampleCalls;
  sampleReply = withNews([{ when: at(45), kind: 'release', currency: 'USD', symbol: null, impact: 'high', title_ar: 'بيانات التضخم' }]);
  await analyse();
  check('near high-impact news blocks the ticket', stamp() === 'لا صفقة' && text().includes('NEWS_EVENT') && text().includes('within two hours') && text().includes('بيانات التضخم'), text());
  check('no second reading is spent on a blocked ticket', sampleCalls === callsBefore + 1, sampleCalls - callsBefore);
  check('journal keeps the news reason', Array.from(doc.querySelectorAll('#journal-list .jcard')).some((c) => c.textContent.includes('NEWS_EVENT')));
  check('calendar chip is on', Array.from($('result').querySelectorAll('.cover span')).map((s) => s.className).join(',') === 'missing,yes,missing,yes,yes');
  sampleReply = withNews([{ when: null, kind: 'release', currency: 'EUR', symbol: null, impact: 'high', title_ar: 'قرار الفائدة' }]);
  await analyse();
  check('high-impact news without a time blocks', text().includes('NEWS_EVENT') && text().includes('time missing'), text());
  sampleReply = withNews([{ when: at(30), kind: 'release', currency: 'JPY', symbol: null, impact: 'high', title_ar: 'خبر ياباني' },
                          { when: at(30), kind: 'release', currency: 'USD', symbol: null, impact: 'low', title_ar: 'خبر ضعيف' },
                          { when: at(300), kind: 'release', currency: 'USD', symbol: null, impact: 'high', title_ar: 'خبر لاحق' }], { against_trade: true });
  await analyse();
  check('other currencies and low impact do not block; later news warns', stamp() === 'تذكرة جاهزة' && text().includes('خبر مهم لاحقاً') && text().includes('not relevant') && text().includes('not high importance') && text().includes('تعاكس اتجاه الصفقة') && !text().includes('لم تُفحص الأخبار'), text());
  sampleReply = withNews([{ when: at(-200), kind: 'release', currency: 'USD', symbol: null, impact: 'high', title_ar: 'خبر قديم' }]);
  await analyse();
  check('old news does not block', stamp() === 'تذكرة جاهزة' && text().includes('outside the window'), text());
  sampleReply = eurusd((d) => { d.news = { checked: true, events: [], context_ar: '', against_trade: false }; });
  await analyse();
  check('a news claim without a calendar image is not trusted', stamp() === 'تذكرة جاهزة' && text().includes('لم تُفحص الأخبار'), text());
  sampleReply = withNews([{ when: at(20), kind: 'release', currency: 'USD', symbol: null, impact: 'high', title_ar: 'خبر' }], {});
  sampleReply.setup.decision = 'no_trade'; sampleReply.setup.failed_gate = 2;
  await analyse();
  check('news never turns a no trade into a ticket', stamp() === 'لا صفقة' && text().includes('GATE 2') && text().includes('خبر مهم قريب'), text());

  // 11c. extra screenshots have their own box and their own reading: more than four images in one run
  const clearThumbs = () => { Array.from(doc.querySelectorAll('#thumbs .thumb button, #thumbs-extra .thumb button')).reverse().forEach((b) => b.click()); };
  clearThumbs();
  pickFiles(4); pickFiles(3, 'files-extra'); await wait(20);
  check('seven images are accepted across the two boxes', doc.querySelectorAll('#thumbs .thumb').length === 4 && doc.querySelectorAll('#thumbs-extra .thumb').length === 3);
  extraReply = { images: [{ n: 1, kind: 'trade_tab' }, { n: 2, kind: 'calendar' }, { n: 3, kind: 'chart' }],
    account: { balance: '3000.48', equity: '3000.48', margin: '0.00', free_margin: '3000.48', positions: [] }, specification: null,
    news: { checked: true, source_image: 2, events: [{ when: at(40), kind: 'release', currency: 'EUR', symbol: null, impact: 'high', title_ar: 'خبر أوروبي' }], context_ar: '', against_trade: false } };
  sampleReply = eurusd((d) => { d.account = null; d.images = [d.images[0]]; });
  appliedTier = 'default';
  let extraBefore = extraCalls; callsBefore = sampleCalls;
  $('btn-run').click(); await wait(200);
  check('extras are read in their own call', extraCalls === extraBefore + 1 && extraImages === 3 && lastImages === 4 && sampleCalls === callsBefore + 1, [extraCalls, extraImages, lastImages, sampleCalls - callsBefore].join(','));
  check('account from the extra box is applied', $('acc-balance') ? $('acc-balance').value === '3000.48' : text().includes('3000.48'), text());
  check('calendar from the extra box blocks', stamp() === 'لا صفقة' && text().includes('NEWS_EVENT') && text().includes('خبر أوروبي'), text());
  check('a chart in the extra box is flagged', text().includes('وُضعت مع الصور الإضافية'));
  check('the tier that answered is shown and a lower tier is flagged', text().includes('Model tier that answered') && text().includes('أتاح نموذجاً أقل'), text());
  appliedTier = '';
  clearThumbs();
  pickFiles(1, 'files-extra'); await wait(20);
  extraReply = { images: [{ n: 1, kind: 'trade_tab' }], account: { balance: '102.00', equity: '102.00', margin: '0.00', free_margin: '102.00', positions: [] }, specification: null, news: { checked: false, events: [] } };
  callsBefore = sampleCalls;
  $('btn-run').click(); await wait(150);
  check('extras alone update the setup without an analysis call', stamp() === 'تم التحديث' && sampleCalls === callsBefore, stamp());
  clearThumbs();
  extraReply = null;

  // 12. photos: an analysis error offers a retry
  sampleReply = { __error: { code: 'upstream_error', message: 'x' } };
  await analyse();
  check('error offers a retry', !$('ai-note').hidden && !$('btn-retry').hidden, $('ai-note').textContent);

  // 13. photos: only the Trade tab updates the setup, nothing is journaled
  const before = doc.querySelectorAll('#journal-list .jcard').length;
  sampleReply = { images: [{ n: 1, kind: 'trade_tab' }], account: { balance: '102.00', equity: '102.00', margin: '0.00', free_margin: '102.00', positions: [] }, specification: null, charts: [], setup: {}, opinion_ar: '' };
  await analyse();
  check('setup-only run', stamp() === 'تم التحديث' && doc.querySelectorAll('#journal-list .jcard').length === before && $('btn-retry').hidden, stamp());

  // 14. journal: results, daily limit, statistics, review, delete
  $('nav-journal').click();
  card(1).querySelector('[data-result="loss"]').click();
  card(3).querySelector('[data-result="loss"]').click();
  $('nav-desk').click();
  $('tab-manual').click();
  check('daily loss limit blocks', stamp() === 'لا صفقة' && text().includes('DAILY_LIMIT') && text().includes('Losses today'), text());
  $('nav-journal').click();
  card(1).querySelector('[data-result="win"]').click();
  let pnl = $('jr-pnl-1'); pnl.value = '2.00'; pnl.dispatchEvent(new window.Event('change', { bubbles: true }));
  pnl = $('jr-pnl-3'); pnl.value = 'x'; pnl.dispatchEvent(new window.Event('change', { bubbles: true }));
  check('journal amount is validated', $('jr-pnl-3').getAttribute('aria-invalid') === 'true');
  pnl = $('jr-pnl-3'); pnl.value = '-1.00'; pnl.dispatchEvent(new window.Event('change', { bubbles: true }));
  check('stats', $('stats').textContent.includes('50.0%') && $('stats').textContent.includes('33.3%') && $('stats').textContent.includes('1.00 USD') && $('stats-note').textContent.includes('ثلاثين'), $('stats').textContent);
  check('performance fold', !$('fold-perf').hidden && !!$('perf').querySelector('svg.spark') && $('perf').textContent.includes('EURUSD') && $('perf').textContent.includes('NO_SPEC'), $('perf').textContent);
  reviewReply = { followed_plan: 'yes', exit: 'stop', summary_ar: 'أُغلقت الصفقة عند وقف الخسارة كما في الخطة.', lessons_ar: ['الالتزام بالخطة كان صحيحاً.'] };
  card(3).querySelector('[data-review]').click();
  pickFiles(1, 'review-file');
  await wait(60);
  check('review saved on the card', reviewCalls === 1 && card(3).textContent.includes('مراجعة الصفقة') && card(3).textContent.includes('أُغلقت عند الوقف'), card(3).textContent);
  const victim = card(2).querySelector('button.link');
  victim.click();
  check('delete asks twice', !!card(2) && victim.textContent.includes('تأكيد'));
  victim.click();
  check('delete removes the card', !card(2));

  // 15. setup: copy the journal out, bring one in
  $('nav-setup').click();
  $('btn-export').click();
  await wait(20);
  check('export shows the text', !$('csv-out').hidden && $('csv-out').value.startsWith('id,time,symbol,side,type,entry,stop,target,lots,risk,reward_risk,scenario_estimate,verdict,result,pnl\n1,'));
  $('csv-in').value = 'wrong,header\n1,2';
  $('btn-import').click();
  check('import rejects a wrong header', $('csv-note').className.includes('warn') && $('csv-note').textContent.includes('أعمدة'));
  $('csv-in').value = 'id,time,symbol,side,type,entry,stop,target,lots,risk,reward_risk,scenario_estimate,verdict,result,pnl\n99,2026-11-01T10:00:00Z,EURUSD,sell,Sell Limit,1.1098,1.1108,1.1078,0.01,1.00,2.00,55,OK,win,2.00\n';
  $('btn-import').click();
  check('import adds the row', $('csv-note').textContent.includes('1 new') && !!card(99), $('csv-note').textContent);

  // 16. the brain: every skill file reaches the model verbatim
  const SKILL_FILES = ['CLAUDE.md', '.claude/skills/trade/SKILL.md', '.claude/skills/account/SKILL.md',
    '.claude/skills/technical-analyst/SKILL.md', '.claude/skills/technical-analyst/references/technical_analysis_framework.md',
    '.claude/skills/technical-analyst/assets/analysis_template.md', '.claude/skills/mt5-lot-calculator/SKILL.md',
    '.claude/skills/position-sizer/SKILL.md', '.claude/skills/position-sizer/references/sizing_methodologies.md'];
  const missing = SKILL_FILES.filter((f) => !lastPrompt.includes(fs.readFileSync(ROOT + f, 'utf8')));
  check('prompt carries all 9 skill files verbatim', missing.length === 0, missing.join(', '));
  check('prompt under the 256 KiB cap', Buffer.byteLength(lastPrompt, 'utf8') < 262144, Buffer.byteLength(lastPrompt, 'utf8'));
  check('skills card lists 9 files', $('skills').querySelectorAll('details').length === 9);

  await wait(900);
  check('db account write', writes.some((w) => w[1] === 'state/account' && w[2].free_margin === '102.00' && Array.isArray(w[2].open_positions)));
  check('saving indicator settles', $('status').textContent.includes('كل التغييرات محفوظة'), $('status').textContent);
  check('no script errors', errors.length === 0, errors.join(' | '));

  const failed = checks.filter((c) => !c[1]);
  console.log(`checks: ${checks.length}  failed: ${failed.length}`);
  process.exit(failed.length ? 1 : 0);
})();
