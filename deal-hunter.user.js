// ==UserScript==
// @name         Deal Hunter — KSL + FB Marketplace
// @namespace    https://github.com/prolsoldier/extraction
// @version      1.0.0
// @description  Scores listings on pages you browse, highlights steals, and pools the best finds from every open tab into one ranked list.
// @match        https://classifieds.ksl.com/*
// @match        https://www.facebook.com/marketplace/*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_addValueChangeListener
// @grant        GM_notification
// @grant        GM_openInTab
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Config — edit these to taste. Prices are what a fair USED deal looks like in
  // the Salt Lake valley; "steal" is the no-brainer threshold.
  // ---------------------------------------------------------------------------
  const HOME = 'West Jordan';

  const SEARCHES = [
    // speakers to finish a 7.1 Sony receiver setup
    'center channel speaker', 'subwoofer', 'surround speakers', 'bookshelf speakers',
    'home theater speakers', '5.1 speakers', 'tower speakers',
    // security / home defense
    'security camera', 'poe camera', 'surveillance hard drive', 'video doorbell',
    'floodlight camera', 'smart lock', 'deadbolt',
  ];

  const RULES = [
    // order matters: first match wins
    { cat: 'System 5.1', re: /\b(5\.1|7\.1|home theat(er|re) (system|speakers?|set)|surround sound system)\b/i, steal: 100, fair: 250 },
    { cat: 'Center', re: /\bcent(er|re)\b/i, steal: 30, fair: 70 },
    { cat: 'Subwoofer', re: /\bsub ?woofer|\bsub\b/i, steal: 50, fair: 110, not: /\b(car|truck|jeep|enclosure|box only|amp kit|marine)\b/i },
    { cat: 'Towers', re: /\b(tower|floor ?stand(ing)?)\b/i, steal: 80, fair: 170 },
    { cat: 'Surround/Bookshelf', re: /\b(surround|bookshelf|satellite|rear) speakers?\b/i, steal: 35, fair: 80 },
    { cat: 'Camera kit', re: /\b(nvr|dvr)\b.*\b(camera|cam)s?\b|\b(camera|cctv|surveillance) (system|kit)\b/i, steal: 70, fair: 150 },
    { cat: 'Camera', re: /\b(poe|ip|security|surveillance|outdoor|floodlight|bullet|dome) ?(cam|camera)s?\b|\b(reolink|amcrest|wyze|eufy|arlo|blink|hikvision|dahua)\b/i, steal: 25, fair: 60 },
    { cat: 'Doorbell', re: /\bdoorbell\b/i, steal: 30, fair: 70 },
    { cat: 'Hard drive', re: /\b(hdd|hard drive|purple|skyhawk|surveillance drive)\b|\b\d+ ?tb\b/i, steal: 20, fair: 45 },
    { cat: 'Locks', re: /\b(smart lock|deadbolt|door armor|jamb|keypad lock)\b/i, steal: 20, fair: 50 },
  ];

  // Brands that sell for more; a listed price on these goes further.
  const PREMIUM = /\b(klipsch|polk|definitive|def tech|svs|elac|paradigm|kef|b&w|bowers|pioneer|andrew jones|bic|infinity|energy|psb|monitor audio|jbl studio|q acoustics|wharfedale|sony core|reolink|amcrest|ubiquiti|unifi|schlage|yale)\b/i;
  const BROKEN = /\b(broken|for parts|parts only|not working|doesn'?t work|blown|as[- ]is|needs repair|cracked)\b/i;
  const WANTED = /\b(iso|wanted|looking for|wtb)\b/i;

  // ---------------------------------------------------------------------------
  // Scoring
  // ---------------------------------------------------------------------------
  function parsePrice(text) {
    if (!text) return null;
    if (/\bfree\b/i.test(text)) return 0;
    const m = text.replace(/,/g, '').match(/\$\s?(\d+(?:\.\d+)?)/);
    return m ? parseFloat(m[1]) : null;
  }

  function score(item) {
    const t = item.title || '';
    if (WANTED.test(t)) return null;
    const rule = RULES.find(r => r.re.test(t) && !(r.not && r.not.test(t)));
    if (!rule || item.price == null) return null;
    const premium = PREMIUM.test(t);
    const mult = premium ? 1.6 : 1;
    const steal = rule.steal * mult, fair = rule.fair * mult;
    const broken = BROKEN.test(t);
    let tier = item.price <= steal ? 'STEAL' : item.price <= fair ? 'GOOD' : 'PASS';
    if (broken) tier = 'PARTS';
    if (item.price === 0 && !broken) tier = 'FREE';
    // 0..1+, higher is better; nearby listings get a small bump
    let value = (fair - item.price) / fair;
    if (premium) value += 0.1;
    if (item.location && new RegExp(`${HOME}|South Jordan|Riverton|Taylorsville|Kearns|Herriman|Midvale|Murray|Sandy|West Valley`, 'i').test(item.location)) value += 0.1;
    if (broken) value -= 1;
    return { ...item, cat: rule.cat, premium, broken, tier, value: Math.round(value * 100) / 100, fair: Math.round(fair) };
  }

  // ---------------------------------------------------------------------------
  // Site parsers — both read only what is already rendered on the page.
  // ---------------------------------------------------------------------------
  // Card text minus our own badge, one trimmed line per entry.
  function cardLines(a) {
    const b = a.querySelector('.dh-badge');
    let text = a.innerText;
    if (b) text = text.replace(b.innerText, '');
    return text.split('\n').map(s => s.trim()).filter(Boolean);
  }

  function parseKSL(root) {
    const out = [];
    root.querySelectorAll('a[data-item-id]').forEach(a => {
      const lines = cardLines(a);
      const priceLine = lines.find(l => /^\$|free/i.test(l));
      const locLine = lines.find(l => /,\s*UT\b/.test(l)) || lines.find((l, i) => lines[i + 2] === 'UT');
      out.push({
        el: a,
        site: 'KSL',
        id: 'ksl:' + a.dataset.itemId,
        url: a.href,
        title: a.getAttribute('aria-label') || lines.find(l => !/^\$/.test(l)) || '',
        price: parsePrice(priceLine),
        location: locLine ? locLine.replace(/,\s*UT.*/, '') : '',
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
      // FB card text order: price(s), title, location[, mileage]
      const priceIdx = lines.findIndex(l => /^(\$|free)/i.test(l));
      const rest = lines.filter((l, i) => i !== priceIdx && !/^\$/.test(l));
      out.push({
        el: a,
        site: 'FB',
        id: 'fb:' + id,
        url: 'https://www.facebook.com/marketplace/item/' + id + '/',
        title: rest[0] || '',
        price: parsePrice(lines[priceIdx]),
        location: rest[1] || '',
      });
    });
    return out;
  }

  // ---------------------------------------------------------------------------
  // Shared pool across tabs (GM storage), highlighting, panel, alerts
  // ---------------------------------------------------------------------------
  const POOL_KEY = 'dealPool';
  const TIER_COLOR = { FREE: '#16a34a', STEAL: '#16a34a', GOOD: '#ca8a04', PASS: '#9ca3af', PARTS: '#dc2626' };

  const loadPool = () => { try { return GM_getValue(POOL_KEY, {}); } catch (e) { return {}; } };
  const savePool = p => GM_setValue(POOL_KEY, p);

  function badge(item) {
    if (item.el.querySelector('.dh-badge')) return;
    const b = document.createElement('div');
    b.className = 'dh-badge';
    b.textContent = `${item.tier} · ${item.cat}${item.tier === 'PASS' ? '' : ` · fair ~$${item.fair}`}`;
    b.style.cssText = `position:absolute;top:4px;left:4px;z-index:9;padding:2px 6px;border-radius:4px;font:600 11px system-ui;color:#fff;background:${TIER_COLOR[item.tier]}`;
    if (getComputedStyle(item.el).position === 'static') item.el.style.position = 'relative';
    item.el.appendChild(b);
    if (item.tier === 'STEAL' || item.tier === 'FREE') item.el.style.outline = `3px solid ${TIER_COLOR[item.tier]}`;
    if (item.tier === 'PASS' || item.tier === 'PARTS') item.el.style.opacity = '0.45';
  }

  function scan() {
    const raw = location.host.includes('ksl.com') ? parseKSL(document) : parseFB(document);
    const pool = loadPool();
    const fresh = [];
    raw.map(score).filter(Boolean).forEach(item => {
      badge(item);
      if (item.tier === 'PASS') return;
      const { el, ...rec } = item;
      if (!pool[rec.id]) { rec.seen = Date.now(); fresh.push(rec); }
      else rec.seen = pool[rec.id].seen;
      pool[rec.id] = rec;
    });
    if (fresh.length) {
      savePool(pool);
      fresh.filter(f => f.tier === 'STEAL' || f.tier === 'FREE').forEach(f =>
        GM_notification({ title: `${f.tier}: $${f.price} ${f.cat}`, text: `${f.title} — ${f.location}`, onclick: () => GM_openInTab(f.url, { active: true }) }));
    }
    renderPanel();
  }

  let panel;
  function renderPanel() {
    if (!panel) {
      panel = document.createElement('div');
      panel.id = 'dh-panel';
      panel.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:2147483647;width:360px;max-height:60vh;overflow:auto;background:#111;color:#eee;font:12px/1.4 system-ui;border-radius:8px;box-shadow:0 4px 20px #0008;padding:8px';
      document.body.appendChild(panel);
    }
    const items = Object.values(loadPool())
      .filter(i => i.tier !== 'PARTS')
      .sort((a, b) => b.value - a.value);
    const collapsed = panel.dataset.collapsed === '1';
    panel.innerHTML = `
      <div style="display:flex;gap:6px;align-items:center;margin-bottom:6px">
        <b style="flex:1">Deal Hunter · ${items.length} finds</b>
        <button data-a="hunt" title="Open every saved search on KSL + FB in background tabs">Hunt all</button>
        <button data-a="csv">CSV</button>
        <button data-a="clear">Clear</button>
        <button data-a="toggle">${collapsed ? '▲' : '▼'}</button>
      </div>
      ${collapsed ? '' : items.slice(0, 60).map(i => `
        <a href="${i.url}" target="_blank" style="display:block;color:inherit;text-decoration:none;padding:4px;border-left:3px solid ${TIER_COLOR[i.tier]};margin:2px 0;background:#1b1b1b">
          <b>$${i.price}</b> · ${i.tier} · ${i.cat} <span style="opacity:.6">[${i.site}] ${i.location}</span><br>${escapeHtml(i.title)}
        </a>`).join('')}`;
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  function searchUrls() {
    const urls = [];
    SEARCHES.forEach(q => {
      const e = encodeURIComponent(q);
      urls.push(`https://classifieds.ksl.com/search/keyword/${e}/zip/84084/miles/25`);
      // FB uses the location saved in your Marketplace settings — set it to West Jordan, ~20 mi.
      urls.push(`https://www.facebook.com/marketplace/search/?query=${e}&sortBy=creation_time_descend&daysSinceListed=7`);
    });
    return urls;
  }

  function exportCSV() {
    const rows = Object.values(loadPool()).sort((a, b) => b.value - a.value);
    const cols = ['tier', 'cat', 'price', 'fair', 'value', 'site', 'location', 'title', 'url'];
    const csv = [cols.join(',')].concat(rows.map(r => cols.map(c => `"${String(r[c] ?? '').replace(/"/g, '""')}"`).join(','))).join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.download = `deals-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
  }

  document.addEventListener('click', e => {
    const a = e.target.closest && e.target.closest('#dh-panel button');
    if (!a) return;
    const act = a.dataset.a;
    if (act === 'hunt') searchUrls().forEach((u, i) => setTimeout(() => GM_openInTab(u, { active: false, insert: true }), i * 1500));
    if (act === 'csv') exportCSV();
    if (act === 'clear' && confirm('Clear all saved finds?')) { savePool({}); renderPanel(); }
    if (act === 'toggle') { panel.dataset.collapsed = panel.dataset.collapsed === '1' ? '0' : '1'; renderPanel(); }
  });

  // Re-scan as infinite scroll adds cards; keep the panel in sync with other tabs.
  let t;
  const ownNode = n => n.nodeType === 1 && (n.id === 'dh-panel' || n.classList.contains('dh-badge') || n.closest('#dh-panel'));
  new MutationObserver(recs => {
    if (recs.every(r => ownNode(r.target) || [...r.addedNodes, ...r.removedNodes].every(ownNode))) return;
    clearTimeout(t); t = setTimeout(scan, 800);
  })
    .observe(document.body, { childList: true, subtree: true });
  try { GM_addValueChangeListener(POOL_KEY, (k, o, n, remote) => remote && renderPanel()); } catch (e) { /* older managers */ }
  scan();

  // exposed for tests
  if (typeof window !== 'undefined') window.__dealHunter = { score, parsePrice, parseKSL, parseFB };
})();
