const test = require('node:test');
const assert = require('node:assert/strict');
const dh = require('../deal-hunter.user.js');

const s = (title, price, location = '', extra = {}) => dh.score({ title, price, location, ...extra });

test('parsePrice', () => {
  assert.equal(dh.parsePrice('$1,299.00'), 1299);
  assert.equal(dh.parsePrice('Free'), 0);
  assert.equal(dh.parsePrice('call me'), null);
  assert.equal(dh.parsePrice(null), null);
});

test('parseQty', () => {
  assert.equal(dh.parseQty('Reolink camera x2'), 2);
  assert.equal(dh.parseQty('4 pack cameras'), 4);
  assert.equal(dh.parseQty('set of 3 locks'), 3);
  assert.equal(dh.parseQty('(6) cameras'), 6);
  assert.equal(dh.parseQty('pair of speakers'), 2);
  assert.equal(dh.parseQty('Sony center speaker'), 1);
});

test('milesFrom', () => {
  assert.equal(dh.milesFrom('West Jordan', 'West Jordan'), 0);
  assert.ok(dh.milesFrom('Riverton, UT', 'West Jordan') <= 7);
  assert.ok(dh.milesFrom('Provo', 'West Jordan') > 25);
  assert.equal(dh.milesFrom('Nowhere', 'West Jordan'), null);
});

test('parseAgeHours', () => {
  assert.equal(dh.parseAgeHours(['2 hours ago']), 2);
  assert.equal(dh.parseAgeHours(['3 days ago']), 72);
  assert.equal(dh.parseAgeHours(['Just listed']), 0);
  assert.equal(dh.parseAgeHours(['Polk 5 speaker']), null);
});

test('tiers', () => {
  assert.equal(s('Pioneer center speaker', 20).tier, 'STEAL');
  assert.equal(s('Generic center speaker', 60).tier, 'GOOD');
  assert.equal(s('Generic center speaker', 150).tier, 'PASS');
  assert.equal(s('Sony subwoofer', 0).tier, 'FREE');
  assert.equal(s('Onkyo center speaker blown', 10).tier, 'PARTS');
  assert.equal(s('Free subwoofer for parts', 0).tier, 'PARTS');
});

test('filters out wanted posts, car subs, and unmatched items', () => {
  assert.equal(s('ISO center speaker', 20), null);
  assert.equal(s('12in car subwoofer', 50), null);
  assert.equal(s('Couch', 20), null);
  assert.equal(s('center speaker', null), null);
});

test('known model overrides category price', () => {
  const r = s('Klipsch RP-600M bookshelf speakers', 150);
  assert.equal(r.model, true);
  assert.equal(r.fair, 250);
  assert.equal(r.tier, 'GOOD');
});

test('per-unit pricing for multi-packs', () => {
  const r = s('Reolink PoE camera 4 pack', 80);
  assert.equal(r.qty, 4);
  assert.equal(r.tier, 'STEAL'); // $20 each
  assert.equal(r.fair, 4 * 60 * 1.6);
});

test('single speaker from a pair category halves the fair price', () => {
  assert.ok(s('single bookshelf speaker', 30).fair < s('bookshelf speakers', 30).fair);
  // singular "Speaker" on a known pair model: $100 for one RP-600M is fair, not a steal
  const one = s('Klipsch RP-600M Bookshelf Speaker', 100);
  assert.equal(one.fair, 125);
  assert.equal(one.tier, 'GOOD');
});

test('scam flags', () => {
  assert.equal(s('Klipsch center speaker zelle only', 40).scam, true);
  assert.equal(s('SVS SB-1000 subwoofer', 20).scam, true); // absurdly cheap
  assert.equal(s('Polk center speaker', 40).scam, false);
});

test('distance and freshness affect ranking', () => {
  const near = s('center speaker', 40, 'Riverton');
  const far = s('center speaker', 40, 'Ogden');
  assert.ok(near.value > far.value);
  const fresh = s('center speaker', 40, 'Riverton', { ageHours: 1 });
  assert.ok(fresh.value > near.value);
});

test('offer suggestion', () => {
  const r = s('Generic center speaker', 60);
  assert.ok(r.offer < 60 && r.offer >= 30);
  assert.match(dh.offerMessage(r), /\$\d+/);
  const steal = s('Generic center speaker', 20);
  assert.equal(steal.offer, 20);
  assert.doesNotMatch(dh.offerMessage(steal), /would you take/);
});

test('mergeSighting tracks new, drops, and preserves status', () => {
  const pool = {};
  const rec = { id: 'fb:1', title: 'center speaker', price: 60 };
  assert.equal(dh.mergeSighting(pool, rec, 1), 'new');
  pool['fb:1'].status = 'watch';
  assert.equal(dh.mergeSighting(pool, { ...rec }, 2), null);
  assert.equal(dh.mergeSighting(pool, { ...rec, price: 40 }, 3), 'drop');
  assert.equal(pool['fb:1'].dropFrom, 60);
  assert.equal(pool['fb:1'].status, 'watch');
  assert.equal(pool['fb:1'].firstSeen, 1);
  assert.deepEqual(pool['fb:1'].history, [[1, 60], [3, 40]]);
  assert.equal(dh.mergeSighting(pool, { ...rec, price: 50 }, 4), null); // raise is not a drop
});

test('prune keeps watched and recent', () => {
  const day = 864e5, now = 100 * day;
  const pool = { a: { lastSeen: now - 30 * day }, b: { lastSeen: now - 30 * day, status: 'watch' }, c: { lastSeen: now - day } };
  assert.equal(dh.prune(pool, dh.DEFAULTS, now), 1);
  assert.deepEqual(Object.keys(pool).sort(), ['b', 'c']);
});

test('groupDupes collapses cross-posts', () => {
  const a = { id: 'ksl:1', site: 'KSL', url: 'k', title: 'Polk Audio CS10 Center Channel Speaker', price: 30, value: 0.5 };
  const b = { id: 'fb:1', site: 'FB', url: 'f', title: 'polk audio cs10 center channel speaker!', price: 30, value: 0.6 };
  const c = { id: 'fb:2', site: 'FB', url: 'g', title: 'Polk Audio CS10 Center Channel Speaker', price: 45, value: 0.3 };
  const g = dh.groupDupes([a, b, c]);
  assert.equal(g.length, 2);
  const top = g.find(x => x.price === 30);
  assert.equal(top.site, 'FB');
  assert.deepEqual(top.alsoOn.map(o => o.site), ['KSL']);
});

test('searchUrls respects config', () => {
  const urls = dh.searchUrls({ ...dh.DEFAULTS, searches: ['sub woofer'], kslZip: '84088', kslMiles: 10, fbDays: 1 });
  assert.equal(urls.length, 2);
  assert.match(urls[0], /keyword\/sub%20woofer\/zip\/84088\/miles\/10$/);
  assert.match(urls[1], /daysSinceListed=1/);
});

test('toCSV escapes quotes', () => {
  const csv = dh.toCSV([{ title: 'a "b" c', price: 5 }]);
  assert.match(csv, /"a ""b"" c"/);
});
