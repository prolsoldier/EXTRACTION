// ==UserScript==
// @name         Deal Hunter — KSL + FB Marketplace
// @namespace    https://github.com/prolsoldier/extraction
// @version      3.0.0
// @description  Ranks KSL + FB Marketplace listings while you browse: learns local prices, catches misspelled and motivated-seller listings, tracks drops, and pools the best finds from every tab.
// @match        https://classifieds.ksl.com/*
// @match        https://www.facebook.com/marketplace/*
// @updateURL    https://raw.githubusercontent.com/prolsoldier/EXTRACTION/main/deal-hunter.user.js
// @downloadURL  https://raw.githubusercontent.com/prolsoldier/EXTRACTION/main/deal-hunter.user.js
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_addValueChangeListener
// @grant        GM_notification
// @grant        GM_openInTab
// @grant        GM_setClipboard
// @grant        GM_registerMenuCommand
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  // ===========================================================================
  // Core — pure functions, no DOM. Loaded by the tests via require().
  // ===========================================================================

  const DEFAULTS = {
    home: 'West Jordan',
    kslZip: '84084',
    kslMiles: 25,
    fbDays: 7,            // FB "listed in the last N days"
    maxMiles: 30,         // listings past this sink in the ranking
    offerPct: 0.75,       // opening offer as a fraction of asking
    pruneDays: 21,        // forget unwatched finds not seen for this long
    notify: true,
    huntDelayMs: 4000,    // gap between tabs opened by "Hunt all"
    huntSites: ['KSL', 'FB'],
    // Categories you still need rank higher. Remove one once you've bought it.
    needs: ['Center', 'Subwoofer', 'Surround/Bookshelf', 'Hard drive', 'Camera'],
    searches: [
      // speakers to finish a 7.1 receiver setup
      'center channel speaker', 'subwoofer', 'surround speakers', 'bookshelf speakers',
      'home theater speakers', '5.1 speakers', 'tower speakers', 'speaker stands',
      'klipsch', 'polk audio', 'free speakers', 'receiver and speakers',
      // common misspellings: fewer buyers find these
      'subwofer', 'klipsh', 'speeker',
      // security / home defense
      'security camera', 'poe camera', 'surveillance hard drive', 'video doorbell',
      'floodlight camera', 'motion sensor light', 'smart lock', 'deadbolt', 'safe', 'nvr', 'wd purple',
    ],
  };

  // Approx city centers (lat, lon) for straight-line distance.
  const CITIES = {
    'west jordan': [40.609, -111.939], 'south jordan': [40.562, -111.929], 'riverton': [40.522, -111.939],
    'herriman': [40.514, -112.033], 'bluffdale': [40.489, -111.939], 'kearns': [40.660, -111.996],
    'taylorsville': [40.668, -111.939], 'west valley city': [40.692, -112.001], 'west valley': [40.692, -112.001],
    'magna': [40.709, -112.102], 'copperton': [40.567, -112.093], 'midvale': [40.611, -111.900],
    'murray': [40.667, -111.888], 'sandy': [40.572, -111.860], 'draper': [40.525, -111.864],
    'cottonwood heights': [40.620, -111.810], 'holladay': [40.669, -111.824], 'millcreek': [40.687, -111.875],
    'south salt lake': [40.718, -111.888], 'salt lake city': [40.761, -111.891], 'north salt lake': [40.849, -111.907],
    'bountiful': [40.889, -111.881], 'woods cross': [40.872, -111.892], 'centerville': [40.918, -111.872],
    'farmington': [40.980, -111.887], 'kaysville': [41.035, -111.939], 'layton': [41.060, -111.971],
    'clearfield': [41.110, -112.026], 'ogden': [41.223, -111.974], 'tooele': [40.531, -112.298],
    'lehi': [40.391, -111.851], 'saratoga springs': [40.349, -111.905], 'eagle mountain': [40.314, -112.007],
    'american fork': [40.377, -111.796], 'pleasant grove': [40.364, -111.739], 'alpine': [40.453, -111.778],
    'highland': [40.425, -111.795], 'lindon': [40.343, -111.721], 'orem': [40.297, -111.695],
    'provo': [40.234, -111.659], 'springville': [40.165, -111.611], 'spanish fork': [40.115, -111.655],
    'park city': [40.646, -111.498], 'heber city': [40.507, -111.413], 'kamas': [40.643, -111.280],
  };

  // First match wins. Prices are fair USED prices in the Salt Lake valley.
  // perUnit: price is divided by the parsed quantity before comparing.
  const RULES = [
    { cat: 'System 5.1', re: /\b(5\.1|7\.1|home theat(er|re) (system|speakers?|set|package)|surround sound system)\b/i, steal: 100, fair: 250 },
    { cat: 'Center', re: /\bcent(er|re)\b/i, steal: 30, fair: 70, not: /\b(entertainment|tv|media|command|console|shopping|piece|table|stand|cabinet|wall unit)\b/i },
    { cat: 'Subwoofer', re: /\bsub ?woofer|\bsub\b/i, steal: 50, fair: 110, not: /\b(car|truck|jeep|enclosure|box only|amp kit|marine|kicker|rockford|jl audio|zero|panel|pump|sandwich)\b/i },
    { cat: 'Towers', re: /\b(tower|floor ?stand(ing)?)\b/i, steal: 80, fair: 170, pair: true, not: /\b(fan|pc|computer|gaming|heater|shelf|bookcase|cat|lamp|light|rack)\b/i },
    { cat: 'Stands', re: /\bspeaker stands?\b/i, steal: 15, fair: 40 },
    { cat: 'Surround/Bookshelf', re: /\b(surround|bookshelf|satellite|rear|monitor) speakers?\b/i, steal: 35, fair: 80, pair: true },
    // Catch-all so model-only titles ("Sony SS-CS5 speakers") still get scored.
    { cat: 'Speakers', re: /\bspeakers?\b/i, steal: 30, fair: 70, pair: true, not: /\b(bluetooth|portable|wireless|pa|dj|computer|pc|gaming|usb|car|door|soundbar|sound bar|flip|charge|soundlink|echo|alexa|smart speaker|karaoke|party)\b/i },
    { cat: 'Camera kit', re: /\b(nvr|dvr)\b.*\b(camera|cam)s?\b|\b(camera|cctv|surveillance|security) (system|kit)\b/i, steal: 70, fair: 150 },
    { cat: 'Camera', re: /\b(poe|ip|security|surveillance|outdoor|floodlight|bullet|dome|turret) ?(cam|camera)s?\b|\b(reolink|amcrest|wyze|eufy|arlo|blink|hikvision|dahua|annke)\b/i, steal: 25, fair: 60, perUnit: true },
    { cat: 'Doorbell', re: /\bdoorbell\b/i, steal: 30, fair: 70 },
    { cat: 'Hard drive', re: /\b(hdd|hard drive|wd purple|skyhawk|surveillance drive)\b|\b\d+ ?tb\b/i, steal: 20, fair: 45, perUnit: true },
    { cat: 'Lights', re: /\b(motion|security|flood) ?(sensor )?lights?\b/i, steal: 10, fair: 25, perUnit: true },
    { cat: 'Locks', re: /\b(smart lock|deadbolt|door armor|jamb|keypad lock)\b/i, steal: 20, fair: 50, perUnit: true },
    { cat: 'Safe', re: /\b(gun safe|safe box|biometric safe|fire ?proof safe|lock ?box|pistol safe)\b/i, steal: 40, fair: 120 },
  ];

  // Known models → fair used price (overrides category + brand allowance).
  const MODELS = [
    { name: 'Polk CS1/CS10', re: /\bpolk\b.*\bcs ?(1|10)\b/i, fair: 50 },
    { name: 'Polk PSW10/110', re: /\bpolk\b.*\bpsw ?(10|110|111)\b/i, fair: 70 },
    { name: 'Polk Monitor 70/RTi', re: /\bpolk\b.*\b(monitor ?70|rti ?(a)?[579])\b/i, fair: 200 },
    { name: 'Polk T15', re: /\bpolk\b.*\bt ?15\b/i, fair: 45 },
    { name: 'Polk T30', re: /\bpolk\b.*\bt ?30\b/i, fair: 45 },
    { name: 'Polk T50', re: /\bpolk\b.*\bt ?50\b/i, fair: 110 },
    { name: 'Polk ES10/ES15', re: /\bpolk\b.*\bes ?1[05]\b/i, fair: 90 },
    { name: 'Klipsch R-25C', re: /\bklipsch\b.*\br-?25c\b/i, fair: 70 },
    { name: 'Klipsch R-52C', re: /\bklipsch\b.*\br-?52c\b/i, fair: 90 },
    { name: 'Klipsch RP-450/500C', re: /\bklipsch\b.*\brp-?(450|500|504)c\b/i, fair: 130 },
    { name: 'Klipsch R-10/12SW', re: /\bklipsch\b.*\br-?(10|100|12|120)sw\b/i, fair: 100 },
    { name: 'Klipsch R-41M/51M', re: /\bklipsch\b.*\br-?(41|51)m\b/i, fair: 90 },
    { name: 'Klipsch RP-600M', re: /\bklipsch\b.*\brp-?600m\b/i, fair: 250 },
    { name: 'Klipsch RP-5000F/6000F', re: /\bklipsch\b.*\brp-?(5000|6000)f\b/i, fair: 400 },
    { name: 'Pioneer SP-C22', re: /\bpioneer\b.*\bsp-?c22\b/i, fair: 50 },
    { name: 'Pioneer SP-BS22', re: /\bpioneer\b.*\bsp-?bs22\b/i, fair: 50 },
    { name: 'Pioneer SP-FS52', re: /\bpioneer\b.*\bsp-?fs52\b/i, fair: 120 },
    { name: 'Pioneer SW-8', re: /\bpioneer\b.*\bsw-?8\b/i, fair: 60 },
    { name: 'ELAC Debut B5/B6', re: /\belac\b.*\b(db|b) ?[56]\b/i, fair: 150 },
    { name: 'Sony SS-CS3/CS5', re: /\bsony\b.*\bss-?cs[35]\b/i, fair: 60 },
    { name: 'Sony SS-CS8', re: /\bsony\b.*\bss-?cs8\b/i, fair: 40 },
    { name: 'Yamaha NS-SW100/200', re: /\byamaha\b.*\bns-?sw(050|100|200)\b/i, fair: 70 },
    { name: 'BIC PL-200/300', re: /\bbic\b.*\b(pl-?200|pl-?300)\b/i, fair: 180 },
    { name: 'BIC F12', re: /\bbic\b.*\bf-?12\b/i, fair: 110 },
    { name: 'Dayton SUB-1000', re: /\bdayton\b.*\bsub-?1000\b/i, fair: 50 },
    { name: 'Dayton SUB-1200', re: /\bdayton\b.*\bsub-?1200\b/i, fair: 70 },
    { name: 'Monoprice 8/10in sub', re: /\bmonoprice\b.*\bsub/i, fair: 60 },
    { name: 'SVS SB-1000', re: /\bsvs\b.*\bsb-?1000\b/i, fair: 300 },
    { name: 'SVS PB-1000', re: /\bsvs\b.*\bpb-?1000\b/i, fair: 350 },
    { name: 'Reolink RLC-5xx', re: /\breolink\b.*\brlc-?5\d\d[a-z]?\b/i, fair: 30, perUnit: true },
    { name: 'Reolink RLC-8xx', re: /\breolink\b.*\brlc-?8\d\d[a-z]?\b/i, fair: 45, perUnit: true },
    { name: 'Amcrest IP5M/IP8M', re: /\bamcrest\b.*\bip[58]m\b/i, fair: 35, perUnit: true },
    { name: 'Wyze Cam', re: /\bwyze\b.*\bcam\b/i, fair: 15, perUnit: true },
    { name: 'WD Purple 1-2TB', re: /\b(wd|western digital) purple\b.*\b[12] ?tb\b/i, fair: 30, perUnit: true },
    { name: 'WD Purple 4TB', re: /\b(wd|western digital) purple\b.*\b4 ?tb\b/i, fair: 50, perUnit: true },
    { name: 'Seagate SkyHawk', re: /\bskyhawk\b/i, fair: 35, perUnit: true },
    { name: 'Ring Floodlight Cam', re: /\bring\b.*\bfloodlight\b/i, fair: 80 },
    { name: 'Ring Doorbell', re: /\bring\b.*\bdoorbell\b/i, fair: 40 },
    { name: 'Schlage Encode', re: /\bschlage\b.*\bencode\b/i, fair: 110 },
  ];

  const PREMIUM = /\b(klipsch|polk|definitive|def tech|svs|elac|paradigm|kef|b&w|bowers|pioneer|andrew jones|bic|infinity|energy|psb|monitor audio|jbl studio|q acoustics|wharfedale|sony core|reolink|amcrest|ubiquiti|unifi|schlage|yale|kwikset|stack-?on|liberty)\b/i;
  const BROKEN = /\b(broken|for parts|parts only|not working|doesn'?t work|blown|as[- ]is|needs repair|cracked|untested)\b/i;
  const WANTED = /\b(iso|wanted|looking for|wtb|in search of)\b/i;
  const LIKE_NEW = /\b(new in box|nib|brand new|sealed|like new|mint|barely used|never used|unopened)\b/i;
  const BUNDLE = /\b(lot|bundle|everything|whole (set|system)|(with|and|\+) (a )?receiver|complete (set|system))\b/i;
  const SOLD = /^(sold|pending|sale pending)$/i;
  const SCAMMY = /\b(zelle|cash ?app|venmo only|deposit|ship(ping)? only|will ship|text me at|email me|\d{3}[-. ]\d{3}[-. ]\d{4})\b/i;

  // Common misspellings. Listings with these get fewer buyers, so they often sit cheap.
  // [pattern, replacement, isTypo]. Real misspellings get fewer buyers, so they often sit cheap;
  // the non-typo rows only normalize spelling variants so the rules match.
  const TYPOS = [
    [/\bsub ?w(?:o|oo|ooo)f+e?rs?\b|\bsub ?whoofers?\b/gi, 'subwoofer', true],
    [/\bsp(?:ee|ea|e)k(?:e|a)?rs?\b|\bspeakes\b/gi, m => (/s$/i.test(m) ? 'speakers' : 'speaker'), true],
    [/\bcnter\b|\bcenter ?chanel\b/gi, 'center', true],
    [/\bklip(?:sh|ch|she|shc)\b/gi, 'klipsch', true],
    [/\bsecurty\b|\bsecuirty\b/gi, 'security', true],
    [/\bcamra\b|\bcamer\b/gi, 'camera', true],
    [/\bcentre\b/gi, 'center', false],
    [/\bhome ?theat(?:er|re|or)\b/gi, 'home theater', false],
    [/\bdefinitive technology\b/gi, 'definitive', false],
  ];

  function normalizeTitle(title) {
    let t = String(title || '');
    let typo = false;
    const squash = x => x.toLowerCase().replace(/\s+/g, '');
    for (const [re, to, isTypo] of TYPOS) {
      t = t.replace(re, m => {
        const fixed = typeof to === 'function' ? to(m) : to;
        if (isTypo && squash(fixed) !== squash(m)) typo = true;
        return fixed;
      });
    }
    return { text: t, typo };
  }

  function parsePrice(text) {
    if (!text) return null;
    if (/\bfree\b/i.test(text)) return 0;
    const m = String(text).replace(/,/g, '').match(/\$\s?(\d+(?:\.\d+)?)/);
    return m ? parseFloat(m[1]) : null;
  }

  // "x2", "2x", "set of 4", "4 pack", "(3) cameras", "pair of" → count
  function parseQty(title) {
    const t = title.toLowerCase();
    const m = t.match(/\bx ?(\d{1,2})\b|\b(\d{1,2}) ?x\b|\bset of (\d{1,2})\b|\b(\d{1,2}) ?(?:pack|pk|pcs|pieces)\b|\((\d{1,2})\)|\b(\d{1,2}) (?:cameras|cams|drives|locks|lights)\b/);
    if (m) { const n = parseInt(m.slice(1).find(Boolean), 10); if (n > 0 && n <= 32) return n; }
    if (/\b(pair|two)\b/.test(t)) return 2;
    return 1;
  }

  function haversineMiles([la1, lo1], [la2, lo2]) {
    const r = Math.PI / 180, dLa = (la2 - la1) * r, dLo = (lo2 - lo1) * r;
    const h = Math.sin(dLa / 2) ** 2 + Math.cos(la1 * r) * Math.cos(la2 * r) * Math.sin(dLo / 2) ** 2;
    return 3959 * 2 * Math.asin(Math.sqrt(h));
  }

  function milesFrom(location, home) {
    if (!location) return null;
    const loc = location.toLowerCase().replace(/,.*$/, '').trim();
    const a = CITIES[home.toLowerCase()], b = CITIES[loc];
    return a && b ? Math.round(haversineMiles(a, b)) : null;
  }

  // "3 hours ago", "2d", "Just listed" → hours, when a card shows it
  function parseAgeHours(lines) {
    for (const l of lines) {
      if (/just (now|listed)/i.test(l)) return 0;
      const m = l.match(/(\d+)\s*(min|minute|h|hr|hour|d|day|w|week)s?\b(?: ago)?/i);
      if (m && /ago|^\d+\s*[mhdw]/i.test(l)) {
        const n = +m[1], u = m[2][0].toLowerCase();
        return u === 'm' ? n / 60 : u === 'h' ? n : u === 'd' ? n * 24 : n * 168;
      }
    }
    return null;
  }

  const round5 = n => Math.max(5, Math.round(n / 5) * 5);
  const DAY = 864e5;

  // ---- local market: what things actually list for around here ----------------
  const MARKET_MIN = 5; // samples before the local median is trusted
  const MARKET_CAP = 60; // most recent samples kept per key

  function median(xs) {
    const a = [...xs].sort((x, y) => x - y);
    const m = a.length >> 1;
    return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
  }

  // Record one listing's per-unit asking price under its model (or category) key.
  function recordMarket(market, key, id, unitPrice) {
    if (!key || !(unitPrice > 0)) return;
    const bucket = (market[key] = market[key] || {});
    delete bucket[id];
    bucket[id] = unitPrice;
    const ids = Object.keys(bucket);
    for (let i = 0; i < ids.length - MARKET_CAP; i++) delete bucket[ids[i]];
  }

  function marketMedian(market, key) {
    const xs = market && market[key] ? Object.values(market[key]) : [];
    return xs.length >= MARKET_MIN ? median(xs) : null;
  }

  function classify(title) {
    const { text, typo } = normalizeTitle(title);
    const rule = RULES.find(r => r.re.test(text) && !(r.not && r.not.test(text)));
    const model = rule ? MODELS.find(m => m.re.test(text)) : null;
    return { text, typo, rule, model, key: model ? model.name : rule ? rule.cat : null };
  }

  function score(item, cfg = DEFAULTS, market = null, now = Date.now()) {
    if (!item.title || item.price == null) return null;
    const { text: t, typo, rule, model, key } = classify(item.title);
    if (WANTED.test(t) || !rule) return null;
    const premium = PREMIUM.test(t);
    let fair, steal;
    if (model) {
      fair = model.fair;
      steal = model.fair * 0.5;
    } else {
      const mult = premium ? 1.6 : 1;
      fair = rule.fair * mult;
      steal = rule.steal * mult;
    }
    const perUnit = model ? model.perUnit : rule.perUnit;
    const qty = perUnit ? parseQty(t) : 1;
    // Pair categories are priced per pair; "single" or a singular "speaker" means one unit.
    const single = /\b(single|one|1 speaker)\b/i.test(t) || (/\bspeaker\b/i.test(t) && !/\b(speakers|pair|set)\b/i.test(t));
    const half = rule.pair && single;
    if (half) {
      fair /= 2;
      steal /= 2;
    }
    // Blend in the local median once enough listings have been seen.
    const local = marketMedian(market, key);
    if (local != null) {
      const localUnit = half ? local / 2 : local;
      const ratio = steal / fair;
      fair = (fair + localUnit) / 2;
      steal = fair * ratio;
    }

    const unit = item.price / qty;
    const broken = BROKEN.test(t);
    const scam = SCAMMY.test(t) || (item.price > 0 && unit < fair * 0.12);
    const likeNew = LIKE_NEW.test(t);
    const bundle = BUNDLE.test(t);
    const notes = [];
    if (rule.cat === 'Subwoofer' && /\bpassive\b/i.test(t)) notes.push('passive sub needs an amp');
    if (typo) notes.push('misspelled title');

    // Motivated seller: already cut the price, or it's been sitting a week.
    const drops = item.wasPrice > item.price ? 1 : 0;
    const histDrops = (item.history || []).filter((h, i, a) => i && h[1] < a[i - 1][1]).length;
    const daysListed = item.firstSeen ? (now - item.firstSeen) / DAY : 0;
    const motivated = drops + histDrops > 0 || daysListed >= 7;
    if (motivated) notes.push(drops + histDrops ? 'price already cut' : `listed ${Math.floor(daysListed)}+ days`);

    let tier = unit <= steal ? 'STEAL' : unit <= fair ? 'GOOD' : 'PASS';
    if (item.price === 0) tier = 'FREE';
    if (broken) tier = 'PARTS';
    if (item.sold) tier = 'SOLD';

    const miles = item.miles !== undefined ? item.miles : milesFrom(item.location, cfg.home);
    let value = (fair - unit) / fair;
    if (premium || model) value += 0.1;
    if (miles != null) value += miles <= cfg.maxMiles ? 0.15 * (1 - miles / cfg.maxMiles) : -0.25;
    if (item.ageHours != null && item.ageHours < 24) value += 0.1;
    if ((cfg.needs || []).includes(rule.cat)) value += 0.15;
    if (typo) value += 0.05;
    if (motivated) value += 0.05;
    if (likeNew) value += 0.05;
    if (bundle) value += 0.1;
    if (notes.includes('passive sub needs an amp')) value -= 0.3;
    if (broken) value -= 1;
    if (scam) value -= 0.3;
    if (item.sold) value -= 2;

    const pct = cfg.offerPct - (motivated ? 0.1 : 0);
    const offer =
      tier === 'FREE' ? 0 : unit <= steal ? item.price : Math.min(item.price, Math.max(round5(steal * qty), round5(item.price * pct)));
    return {
      ...item,
      cat: rule.cat,
      modelName: model ? model.name : null,
      model: !!model,
      marketKey: key,
      local: local != null ? Math.round(local) : null,
      premium,
      broken,
      scam,
      likeNew,
      bundle,
      typo,
      motivated,
      notes,
      tier,
      qty,
      miles,
      unit,
      fair: Math.round(fair * qty),
      below: Math.round((1 - unit / fair) * 100),
      value: Math.round(value * 100) / 100,
      offer,
    };
  }

  function offerMessage(rec, cfg = DEFAULTS) {
    if (rec.offer === 0 || rec.offer >= rec.price) return `Hi! Is this still available? I can pick up today in ${cfg.home}.`;
    return `Hi! Is this still available? I can pick up today in ${cfg.home} with cash — would you take $${rec.offer}?`;
  }

  // Normalized title+price, so the same item cross-posted to KSL and FB groups together.
  function dupKey(rec) {
    const words = rec.title.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(w => w.length > 2).sort();
    return words.slice(0, 8).join(' ') + '|' + rec.price;
  }

  // Merge a fresh sighting into the pool. Returns 'new', 'drop', or null.
  function mergeSighting(pool, rec, now = Date.now()) {
    const prev = pool[rec.id];
    if (!prev) {
      pool[rec.id] = { ...rec, firstSeen: now, lastSeen: now, history: [[now, rec.price]], status: 'new' };
      return 'new';
    }
    const history = prev.history || [[prev.firstSeen || now, prev.price]];
    let event = null;
    if (rec.price !== prev.price) {
      history.push([now, rec.price]);
      if (rec.price < prev.price) event = 'drop';
    }
    pool[rec.id] = { ...prev, ...rec, firstSeen: prev.firstSeen || now, lastSeen: now, history, status: prev.status || 'new', dropFrom: event ? prev.price : prev.dropFrom };
    return event;
  }

  function prune(pool, cfg = DEFAULTS, now = Date.now()) {
    const cutoff = now - cfg.pruneDays * 864e5;
    let n = 0;
    for (const [id, r] of Object.entries(pool)) if (r.status !== 'watch' && (r.lastSeen || 0) < cutoff) { delete pool[id]; n++; }
    return n;
  }

  // Collapse cross-posts: keep the best-valued record per dupKey, list other sites.
  function groupDupes(records) {
    const groups = new Map();
    for (const r of records) {
      const k = dupKey(r), g = groups.get(k);
      if (!g) groups.set(k, { ...r, alsoOn: [] });
      else if (r.value > g.value) groups.set(k, { ...r, alsoOn: [...g.alsoOn, { site: g.site, url: g.url }] });
      else g.alsoOn.push({ site: r.site, url: r.url });
    }
    return [...groups.values()];
  }

  function searchUrls(cfg = DEFAULTS) {
    const urls = [];
    const sites = cfg.huntSites || ['KSL', 'FB'];
    cfg.searches.forEach(q => {
      const e = encodeURIComponent(q);
      if (sites.includes('KSL')) urls.push(`https://classifieds.ksl.com/search/keyword/${e}/zip/${cfg.kslZip}/miles/${cfg.kslMiles}`);
      // FB uses the location saved in your Marketplace settings.
      if (sites.includes('FB')) urls.push(`https://www.facebook.com/marketplace/search/?query=${e}&sortBy=creation_time_descend&daysSinceListed=${cfg.fbDays}`);
    });
    return urls;
  }

  function toCSV(rows) {
    const cols = ['tier', 'cat', 'modelName', 'price', 'offer', 'fair', 'below', 'local', 'qty', 'value', 'miles', 'site', 'location', 'status', 'dropFrom', 'notes', 'title', 'url'];
    const q = v => `"${String(Array.isArray(v) ? v.join('; ') : (v ?? '')).replace(/"/g, '""')}"`;
    return [cols.join(',')].concat(rows.map(r => cols.map(c => q(r[c])).join(','))).join('\n');
  }

  const core = {
    DEFAULTS, RULES, MODELS, CITIES, normalizeTitle, classify, parsePrice, parseQty, milesFrom, parseAgeHours, score,
    recordMarket, marketMedian, offerMessage, dupKey, mergeSighting, prune, groupDupes, searchUrls, toCSV,
  };
  if (typeof module !== 'undefined' && module.exports) { module.exports = core; return; }

  // ===========================================================================
  // Browser — site parsers, storage, UI. Reads only what's already rendered.
  // ===========================================================================

  const POOL_KEY = 'dealPool', CFG_KEY = 'dealCfg', UI_KEY = 'dealUi', MARKET_KEY = 'dealMarket';
  const TIER_COLOR = { FREE: '#16a34a', STEAL: '#16a34a', GOOD: '#ca8a04', PASS: '#9ca3af', PARTS: '#dc2626', SOLD: '#6b7280' };
  const gmGet = (k, d) => { try { return GM_getValue(k, d); } catch (e) { return d; } };
  const cfg = () => ({ ...DEFAULTS, ...gmGet(CFG_KEY, {}) });
  const loadPool = () => gmGet(POOL_KEY, {});
  const savePool = p => GM_setValue(POOL_KEY, p);
  const loadMarket = () => gmGet(MARKET_KEY, {});
  const ui = () => ({ tier: 'good', cat: 'all', sort: 'value', q: '', collapsed: false, ...gmGet(UI_KEY, {}) });
  const setUi = patch => GM_setValue(UI_KEY, { ...ui(), ...patch });

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const safeUrl = u => (/^https:\/\/(classifieds\.ksl\.com|www\.facebook\.com)\//.test(u) ? u : '#');

  function cardLines(a) {
    const b = a.querySelector('.dh-badge');
    let text = a.innerText;
    if (b) text = text.replace(b.innerText, '');
    return text.split('\n').map(s => s.trim()).filter(Boolean);
  }

  // First $ line is the asking price; a higher second one is the struck-through original.
  function readPrices(lines) {
    const prices = lines.filter(l => /^(\$|free$)/i.test(l)).map(parsePrice).filter(p => p != null);
    const price = prices.length ? prices[0] : null;
    const wasPrice = prices.length > 1 && prices[1] > price ? prices[1] : null;
    return { price, wasPrice, sold: lines.some(l => SOLD.test(l)) };
  }

  function parseKSL(root) {
    const out = [];
    root.querySelectorAll('a[data-item-id]').forEach(a => {
      if (a.closest('#dh-panel')) return;
      const lines = cardLines(a);
      const locLine = lines.find(l => /,\s*UT\b/.test(l)) || lines.find((l, i) => lines[i + 2] === 'UT');
      out.push({
        el: a, site: 'KSL', id: 'ksl:' + a.dataset.itemId, url: a.href,
        title: a.getAttribute('aria-label') || lines.find(l => !/^\$/.test(l)) || '',
        ...readPrices(lines),
        location: locLine ? locLine.replace(/,\s*UT.*/, '') : '',
        ageHours: parseAgeHours(lines),
      });
    });
    return out;
  }

  function parseFB(root) {
    const out = [];
    root.querySelectorAll('a[href*="/marketplace/item/"]').forEach(a => {
      const id = (a.href.match(/\/item\/(\d+)/) || [])[1];
      if (!id || a.closest('#dh-panel')) return;
      const lines = cardLines(a);
      if (!lines.length) return;
      // FB card text order: price (sometimes old price struck through), title, location[, mileage]
      const rest = lines.filter(l => !/^(\$|free$)/i.test(l) && !SOLD.test(l));
      out.push({
        el: a, site: 'FB', id: 'fb:' + id,
        url: 'https://www.facebook.com/marketplace/item/' + id + '/',
        title: rest[0] || '',
        ...readPrices(lines),
        location: (rest[1] || '').replace(/,\s*UT.*/, ''),
        ageHours: parseAgeHours(lines),
      });
    });
    return out;
  }

  function badge(item) {
    const old = item.el.querySelector('.dh-badge');
    if (old) old.remove();
    const b = document.createElement('div');
    b.className = 'dh-badge';
    const bits = [item.tier, item.cat];
    if (item.tier === 'STEAL' || item.tier === 'GOOD') bits.push(`${item.below}% under`);
    if (item.tier !== 'PASS' && item.tier !== 'SOLD') bits.push(`fair ~$${item.fair}`);
    if (item.qty > 1) bits.push(`×${item.qty}`);
    if (item.miles != null) bits.push(`${item.miles} mi`);
    if (item.scam) bits.push('⚠ scam?');
    if (item.motivated) bits.push('motivated');
    if (item.typo) bits.push('typo');
    b.textContent = bits.join(' · ');
    b.style.cssText = `position:absolute;top:4px;left:4px;z-index:9;padding:2px 6px;border-radius:4px;font:600 11px system-ui;color:#fff;background:${item.scam ? '#7c3aed' : TIER_COLOR[item.tier]}`;
    if (getComputedStyle(item.el).position === 'static') item.el.style.position = 'relative';
    item.el.appendChild(b);
    item.el.style.outline = item.tier === 'STEAL' || item.tier === 'FREE' ? `3px solid ${TIER_COLOR[item.tier]}` : '';
    item.el.style.opacity = ['PASS', 'PARTS', 'SOLD'].includes(item.tier) ? '0.45' : '';
    b.title = item.notes.join(' · ') + (item.local ? ` · local median $${item.local}` : '');
  }

  function notify(title, rec) {
    if (!cfg().notify) return;
    try { GM_notification({ title, text: `${rec.title} — ${rec.location || rec.site}`, onclick: () => GM_openInTab(rec.url, { active: true }) }); } catch (e) { /* no notifications */ }
  }

  function scan() {
    const c = cfg();
    const raw = location.host.includes('ksl.com') ? parseKSL(document) : parseFB(document);
    const pool = loadPool();
    const market = loadMarket();
    const marketBefore = JSON.stringify(market);
    let changed = false;
    raw.forEach(r => {
      const known = pool[r.id];
      // Carry history forward so "sitting a week" and past drops count toward motivation.
      const item = score({ ...r, firstSeen: known && known.firstSeen, history: known && known.history }, c, market);
      if (!item) return;
      if (!item.sold && !item.broken && !item.scam) recordMarket(market, item.marketKey, item.id, item.unit);
      if (known && known.status === 'hidden') {
        item.el.style.opacity = '0.3';
        return;
      }
      badge(item);
      if ((item.tier === 'PASS' || item.tier === 'SOLD') && !known) return;
      const { el, ...rec } = item;
      const before = JSON.stringify(known);
      const event = mergeSighting(pool, rec);
      if (JSON.stringify(pool[rec.id]) !== before) changed = true;
      const hot = rec.tier === 'STEAL' || rec.tier === 'FREE';
      if (event === 'new' && hot && !rec.scam) notify(`${rec.tier}: $${rec.price} ${rec.modelName || rec.cat}`, rec);
      if (event === 'drop' && rec.tier !== 'PASS') notify(`PRICE DROP: $${pool[rec.id].dropFrom} → $${rec.price}`, rec);
    });
    if (changed) savePool(pool);
    if (JSON.stringify(market) !== marketBefore) GM_setValue(MARKET_KEY, market);
    renderPanel();
  }

  // ---- panel ----------------------------------------------------------------
  let panel;
  const TIER_FILTER = { steal: ['FREE', 'STEAL'], good: ['FREE', 'STEAL', 'GOOD'], all: ['FREE', 'STEAL', 'GOOD', 'PASS'], watch: null };
  const SORTS = {
    value: (a, b) => b.value - a.value,
    price: (a, b) => a.price - b.price,
    distance: (a, b) => (a.miles ?? 999) - (b.miles ?? 999),
    newest: (a, b) => (b.firstSeen || 0) - (a.firstSeen || 0),
  };

  function renderPanel() {
    if (!panel) {
      panel = document.createElement('div');
      panel.id = 'dh-panel';
      panel.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:2147483647;width:400px;max-height:70vh;overflow:auto;background:#111;color:#eee;font:12px/1.4 system-ui;border-radius:8px;box-shadow:0 4px 20px #0008;padding:8px';
      document.body.appendChild(panel);
    }
    const u = ui();
    const all = Object.values(loadPool()).filter(r => r.status !== 'hidden' && r.tier !== 'PARTS' && r.tier !== 'SOLD');
    const cats = [...new Set(all.map(r => r.cat))].sort();
    const q = u.q.toLowerCase();
    let items = all.filter(r =>
      (u.tier === 'watch' ? r.status === 'watch' : (TIER_FILTER[u.tier] || TIER_FILTER.good).includes(r.tier)) &&
      (u.cat === 'all' || r.cat === u.cat) &&
      (!q || r.title.toLowerCase().includes(q)));
    items = groupDupes(items).sort(SORTS[u.sort] || SORTS.value);
    const opt = (v, cur, label = v) => `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(label)}</option>`;
    const btn = 'background:#333;color:#eee;border:1px solid #555;border-radius:4px;padding:1px 6px;cursor:pointer';

    // Keep focus/caret in the search box across re-renders.
    const focused = document.activeElement && document.activeElement.dataset && document.activeElement.dataset.f === 'q';
    const caret = focused ? document.activeElement.selectionStart : null;

    panel.innerHTML = `
      <div style="display:flex;gap:4px;align-items:center;flex-wrap:wrap;margin-bottom:6px">
        <b style="flex:1;min-width:120px">Deal Hunter · ${items.length}/${all.length}</b>
        <button style="${btn}" data-a="hunt" title="Open every saved search on KSL + FB in background tabs">Hunt all</button>
        <button style="${btn}" data-a="scroll" title="Scroll this page to load more results">${scrolling ? 'Stop' : 'Auto-scroll'}</button>
        <button style="${btn}" data-a="settings">⚙</button>
        <button style="${btn}" data-a="toggle">${u.collapsed ? '▲' : '▼'}</button>
      </div>
      ${u.collapsed ? '' : `
      <div style="display:flex;gap:4px;margin-bottom:6px;flex-wrap:wrap">
        <select data-f="tier">${opt('steal', u.tier, 'Steals')}${opt('good', u.tier, 'Good+')}${opt('all', u.tier, 'All')}${opt('watch', u.tier, '★ Watching')}</select>
        <select data-f="cat">${opt('all', u.cat, 'All categories')}${cats.map(c => opt(c, u.cat)).join('')}</select>
        <select data-f="sort">${opt('value', u.sort, 'Best value')}${opt('price', u.sort, 'Cheapest')}${opt('distance', u.sort, 'Closest')}${opt('newest', u.sort, 'Newest')}</select>
        <input data-f="q" placeholder="filter…" value="${esc(u.q)}" style="flex:1;min-width:80px">
      </div>
      ${items.slice(0, 80).map(r => `
        <div style="padding:4px;border-left:3px solid ${r.scam ? '#7c3aed' : TIER_COLOR[r.tier]};margin:3px 0;background:#1b1b1b">
          <div style="display:flex;gap:6px;align-items:baseline">
            <a href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener" style="flex:1;color:inherit;text-decoration:none">
              <b>$${esc(r.price)}</b>${r.dropFrom ? ` <s style="opacity:.6">$${esc(r.dropFrom)}</s> <span style="color:#4ade80">▼</span>` : ''}
              · ${esc(r.tier)}${r.below > 0 ? ` −${esc(r.below)}%` : ''} · ${esc(r.modelName || r.cat)}${r.qty > 1 ? ` ×${esc(r.qty)}` : ''}
              <span style="opacity:.6">[${esc(r.site)}${r.alsoOn.map(o => '+' + esc(o.site)).join('')}] ${esc(r.location)}${r.miles != null ? ` · ${esc(r.miles)} mi` : ''}</span>
              ${r.scam ? '<span style="color:#c4b5fd"> ⚠ scam?</span>' : ''}<br>${esc(r.title)}
              ${(r.notes || []).length || r.local ? `<br><span style="opacity:.6;font-size:11px">${esc([...(r.notes || []), r.local ? `local median $${r.local}` : ''].filter(Boolean).join(' · '))}</span>` : ''}
            </a>
            <button style="${btn}" data-a="offer" data-id="${esc(r.id)}" title="Copy a message for the seller and open the listing">${r.offer && r.offer < r.price ? 'Offer $' + esc(r.offer) : 'Msg'}</button>
            <button style="${btn}" data-a="watch" data-id="${esc(r.id)}" title="Watch">${r.status === 'watch' ? '★' : '☆'}</button>
            <button style="${btn}" data-a="hide" data-id="${esc(r.id)}" title="Hide">✕</button>
          </div>
        </div>`).join('')}
      <div style="display:flex;gap:4px;margin-top:6px">
        <button style="${btn}" data-a="csv">CSV</button>
        <button style="${btn}" data-a="backup">Backup</button>
        <button style="${btn}" data-a="restore">Restore</button>
        <button style="${btn}" data-a="unhide">Unhide all</button>
        <button style="${btn}" data-a="clear">Clear</button>
      </div>`}`;

    if (focused) { const i = panel.querySelector('[data-f="q"]'); i.focus(); i.setSelectionRange(caret, caret); }
  }

  function download(name, text, type) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type }));
    a.download = name;
    a.click();
  }

  function setStatus(id, status) {
    const pool = loadPool();
    if (!pool[id]) return;
    pool[id].status = pool[id].status === status ? 'new' : status;
    savePool(pool);
    renderPanel();
  }

  function copy(text) {
    try { GM_setClipboard(text); } catch (e) { navigator.clipboard && navigator.clipboard.writeText(text); }
  }

  // ---- auto-scroll (user-started; paced like a person scrolling) ------------
  let scrolling = null;
  function toggleScroll() {
    if (scrolling) { clearInterval(scrolling); scrolling = null; renderPanel(); return; }
    let steps = 0, lastH = 0, still = 0;
    scrolling = setInterval(() => {
      window.scrollTo(0, document.body.scrollHeight);
      const h = document.body.scrollHeight;
      still = h === lastH ? still + 1 : 0; lastH = h;
      if (++steps >= 15 || still >= 3) toggleScroll();
    }, 2500);
    renderPanel();
  }

  function hunt() {
    const c = cfg();
    const urls = searchUrls(c);
    if (!confirm(`Open ${urls.length} search tabs (one every ${c.huntDelayMs / 1000}s)?`)) return;
    urls.forEach((url, i) => setTimeout(() => GM_openInTab(url, { active: false, insert: true }), i * c.huntDelayMs));
  }

  function openSettings() {
    const text = prompt('Deal Hunter settings (JSON). Clear the box and OK to reset to defaults.', JSON.stringify(cfg(), null, 1));
    if (text === null) return;
    if (!text.trim()) { GM_setValue(CFG_KEY, {}); rescoreAll(); return; }
    try {
      const next = JSON.parse(text);
      if (next.home && !CITIES[String(next.home).toLowerCase()]) alert(`Unknown home city "${next.home}" — distances will be blank. Known: ${Object.keys(CITIES).join(', ')}`);
      GM_setValue(CFG_KEY, next);
      rescoreAll();
    } catch (e) { alert('Invalid JSON: ' + e.message); }
  }

  // Settings changed → recompute tier/value/distance for everything already saved.
  function rescoreAll() {
    const c = cfg(), pool = loadPool(), market = loadMarket();
    for (const [id, r] of Object.entries(pool)) {
      const s = score({ ...r, miles: undefined }, c, market);
      if (s) pool[id] = { ...r, ...s };
    }
    savePool(pool);
    renderPanel();
  }

  function restore() {
    const text = prompt('Paste a Deal Hunter backup (JSON):');
    if (!text) return;
    try {
      const data = JSON.parse(text);
      if (data.pool) savePool({ ...loadPool(), ...data.pool });
      if (data.cfg) GM_setValue(CFG_KEY, data.cfg);
      if (data.market) GM_setValue(MARKET_KEY, { ...loadMarket(), ...data.market });
      renderPanel();
    } catch (e) { alert('Invalid backup: ' + e.message); }
  }

  const ACTIONS = {
    hunt, settings: openSettings, restore,
    scroll: toggleScroll,
    toggle: () => { setUi({ collapsed: !ui().collapsed }); renderPanel(); },
    watch: id => setStatus(id, 'watch'),
    hide: id => setStatus(id, 'hidden'),
    offer: id => { const r = loadPool()[id]; if (r) { copy(offerMessage(r, cfg())); window.open(safeUrl(r.url), '_blank', 'noopener'); } },
    csv: () => download(`deals-${new Date().toISOString().slice(0, 10)}.csv`, toCSV(Object.values(loadPool()).sort(SORTS.value)), 'text/csv'),
    backup: () => download(`deal-hunter-backup-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify({ cfg: gmGet(CFG_KEY, {}), pool: loadPool(), market: loadMarket() }), 'application/json'),
    unhide: () => { const p = loadPool(); Object.values(p).forEach(r => { if (r.status === 'hidden') r.status = 'new'; }); savePool(p); renderPanel(); },
    clear: () => { if (confirm('Clear all saved finds (watched too)?')) { savePool({}); renderPanel(); } },
  };

  document.addEventListener('click', e => {
    const b = e.target.closest && e.target.closest('#dh-panel button');
    if (!b) return;
    e.preventDefault();
    const fn = ACTIONS[b.dataset.a];
    if (fn) fn(b.dataset.id);
  });
  document.addEventListener('change', e => {
    const f = e.target.closest && e.target.closest('#dh-panel select');
    if (f) { setUi({ [f.dataset.f]: f.value }); renderPanel(); }
  });
  document.addEventListener('input', e => {
    const f = e.target.closest && e.target.closest('#dh-panel input[data-f="q"]');
    if (f) { setUi({ q: f.value }); renderPanel(); }
  });
  document.addEventListener('keydown', e => {
    if (e.altKey && e.key.toLowerCase() === 'd') ACTIONS.toggle();
  });

  try {
    GM_registerMenuCommand('Settings', openSettings);
    GM_registerMenuCommand('Hunt all', hunt);
    GM_registerMenuCommand('Export CSV', ACTIONS.csv);
  } catch (e) { /* menu unsupported */ }

  // Prune stale finds once per page load.
  { const p = loadPool(); if (prune(p, cfg())) savePool(p); }

  // Re-scan as infinite scroll adds cards; keep the panel in sync with other tabs.
  let t;
  const ownNode = n => n.nodeType === 1 && (n.id === 'dh-panel' || n.classList.contains('dh-badge') || n.closest('#dh-panel'));
  new MutationObserver(recs => {
    if (recs.every(r => ownNode(r.target) || [...r.addedNodes, ...r.removedNodes].every(ownNode))) return;
    clearTimeout(t); t = setTimeout(scan, 800);
  }).observe(document.body, { childList: true, subtree: true });
  try { GM_addValueChangeListener(POOL_KEY, (k, o, n, remote) => remote && renderPanel()); } catch (e) { /* older managers */ }
  scan();

  window.__dealHunter = { ...core, parseKSL, parseFB, scan };
})();
