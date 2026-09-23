// End-to-end: loads fixtures in headless Chromium with GM_* shims and drives the real userscript.
// Run: npm run test:e2e   (needs playwright; uses PLAYWRIGHT_BROWSERS_PATH or a system chromium)
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
let chromium;
try { ({ chromium } = require('playwright')); } catch (e) {
  try { ({ chromium } = require(require('child_process').execSync('npm root -g').toString().trim() + '/playwright')); } catch (e2) {
    console.log('SKIP: playwright not installed'); process.exit(0);
  }
}

const src = fs.readFileSync(path.join(__dirname, '..', 'deal-hunter.user.js'), 'utf8');
const shim = `
  window.__store = {}; window.__notes = []; window.__clip = null; window.__opened = [];
  window.GM_getValue = (k, d) => (k in window.__store ? JSON.parse(window.__store[k]) : d);
  window.GM_setValue = (k, v) => { window.__store[k] = JSON.stringify(v); };
  window.GM_addValueChangeListener = () => {};
  window.GM_notification = o => window.__notes.push(o.title);
  window.GM_openInTab = u => window.__opened.push(u);
  window.GM_setClipboard = t => { window.__clip = t; };
  window.GM_registerMenuCommand = () => {};
  window.open = u => { window.__opened.push(u); };
  window.confirm = () => true;
`;

async function load(browser, fixture, url, preStore) {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.route(url, r => r.fulfill({ body: fs.readFileSync(path.join(__dirname, 'fixtures', fixture), 'utf8'), contentType: 'text/html' }));
  await page.goto(url);
  await page.evaluate(shim);
  if (preStore) await page.evaluate(s => { window.__store = s; }, preStore);
  await page.evaluate(src);
  await page.waitForTimeout(300);
  return { page, errors };
}

const badges = page => page.$$eval('.dh-badge', bs => bs.map(b => b.textContent));

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  let ok = 0;
  const check = async (name, fn) => { await fn(); ok++; console.log('ok -', name); };

  // --- KSL
  const ksl = await load(browser, 'ksl.html', 'https://classifieds.ksl.com/search/keyword/x');
  await check('KSL parses and badges cards', async () => {
    const b = await badges(ksl.page);
    assert.equal(b.length, 4, b.join('\n')); // wanted post skipped
    assert.ok(b.some(x => x.startsWith('GOOD · Center') && x.includes('6 mi')));
    assert.ok(b.some(x => x.startsWith('GOOD · System 5.1')));
    assert.ok(b.some(x => x.includes('×4') && x.includes('fair ~$120'))); // known-model per-unit price
  });
  await check('KSL item age parsed', async () => {
    const r = await ksl.page.evaluate(() => window.__dealHunter.parseKSL(document).find(i => i.id === 'ksl:1001'));
    assert.equal(r.ageHours, 2);
    assert.equal(r.location, 'Riverton');
  });
  const kslStore = await ksl.page.evaluate(() => window.__store);

  // --- FB, sharing the pool from the KSL tab
  const fb = await load(browser, 'fb.html', 'https://www.facebook.com/marketplace/search/', kslStore);
  await check('FB tiers, exclusions, scam flag', async () => {
    const b = await badges(fb.page);
    assert.ok(b.some(x => x.startsWith('FREE · Subwoofer')));
    assert.ok(b.some(x => x.startsWith('PARTS · Center')));
    assert.ok(b.some(x => x.includes('scam?')));
    assert.ok(!b.some(x => /car/i.test(x)));
    assert.equal(b.length, 8); // car sub skipped
  });
  await check('notifications fire for new steals, not scams', async () => {
    const n = await fb.page.evaluate(() => window.__notes);
    assert.ok(n.some(t => t.startsWith('FREE')));
    assert.ok(!n.some(t => t.includes('$15'))); // scammy RP-600M
  });
  await check('panel escapes seller text (no XSS)', async () => {
    await fb.page.evaluate(() => { const s = document.querySelector('#dh-panel select[data-f="tier"]'); s.value = 'all'; s.dispatchEvent(new Event('change', { bubbles: true })); });
    await fb.page.waitForTimeout(200);
    assert.equal(await fb.page.evaluate(() => window.__xss), undefined);
    assert.equal(await fb.page.$$eval('#dh-panel img, #dh-panel b[onmouseover]', n => n.length), 0);
    assert.ok((await fb.page.textContent('#dh-panel')).includes('<img src=x'));
  });
  await check('cross-posts collapse to one row', async () => {
    const txt = await fb.page.textContent('#dh-panel');
    assert.equal((txt.match(/Polk Audio CS10 Center Channel Speaker/g) || []).length, 1, txt);
    assert.match(txt, /\[(FB\+KSL|KSL\+FB)\]/);
  });
  await check('no rescan loop', async () => {
    const n = await fb.page.evaluate(async () => { let c = 0; const o = window.GM_getValue; window.GM_getValue = (...a) => (c++, o(...a)); await new Promise(r => setTimeout(r, 2500)); return c; });
    assert.equal(n, 0);
  });
  await check('rescan after badges keeps parse stable', async () => {
    const items = await fb.page.evaluate(() => window.__dealHunter.parseFB(document).map(i => [i.price, i.title, i.location]));
    assert.equal(items.length, 9);
    assert.deepEqual(items[0], [25, 'Polk Audio CS1 center channel speaker', 'West Jordan']);
  });
  await check('offer button copies a message and opens the listing', async () => {
    await fb.page.evaluate(() => { const s = document.querySelector('#dh-panel select[data-f="tier"]'); s.value = 'good'; s.dispatchEvent(new Event('change', { bubbles: true })); });
    await fb.page.click('#dh-panel button[data-a="offer"]');
    assert.match(await fb.page.evaluate(() => window.__clip), /still available/);
    assert.match((await fb.page.evaluate(() => window.__opened)).pop(), /^https:\/\/(www\.facebook|classifieds\.ksl)\.com\//);
  });
  await check('watch and hide toggle status', async () => {
    const id = await fb.page.getAttribute('#dh-panel button[data-a="watch"]', 'data-id');
    await fb.page.click(`#dh-panel button[data-a="watch"][data-id="${id}"]`);
    await fb.page.click(`#dh-panel button[data-a="hide"][data-id="${id}"]`);
    const st = await fb.page.evaluate(i => JSON.parse(window.__store.dealPool)[i].status, id);
    assert.equal(st, 'hidden');
    assert.equal(await fb.page.$(`#dh-panel button[data-id="${id}"]`), null);
  });
  await check('price drop detected on rescan', async () => {
    await fb.page.evaluate(() => { document.querySelector('a[href*="/item/444/"] div').textContent = '$30'; window.__dealHunter.scan(); });
    const n = await fb.page.evaluate(() => window.__notes);
    assert.ok(n.some(t => t === 'PRICE DROP: $40 → $30'), n.join('|'));
  });
  await check('hunt opens every search', async () => {
    await fb.page.evaluate(() => { window.__opened = []; });
    await fb.page.evaluate(() => { window.__store.dealCfg = JSON.stringify({ huntDelayMs: 0 }); });
    await fb.page.click('#dh-panel button[data-a="hunt"]');
    await fb.page.waitForTimeout(100);
    const n = await fb.page.evaluate(() => window.__dealHunter.DEFAULTS.searches.length);
    assert.equal((await fb.page.evaluate(() => window.__opened)).length, n * 2);
  });
  await check('no page errors', async () => { assert.deepEqual([...ksl.errors, ...fb.errors], []); });

  await browser.close();
  console.log(`\n${ok} checks passed`);
})().catch(e => { console.error(e); process.exit(1); });
