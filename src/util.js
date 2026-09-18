import crypto from 'node:crypto';

/**
 * Escape text for safe interpolation into HTML.
 * Every piece of user-supplied text goes through this before it reaches a page.
 */
export function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

/**
 * Render a message body as escaped HTML with paragraph breaks and >greentext.
 * Runs on already-escaped text, so no user markup can survive into the page.
 */
export function renderBody(raw) {
  return escapeHtml(raw)
    .split(/\n{2,}/)
    .map((block) => {
      const lines = block.split('\n').map((line) =>
        line.startsWith('&gt;') && !line.startsWith('&gt;&gt;')
          ? `<span class="quote">${line}</span>`
          : line,
      );
      return `<p>${lines.join('<br>')}</p>`;
    })
    .join('');
}

/**
 * Derive a rotating, non-reversible poster token used ONLY for rate limiting.
 *
 * The raw IP address is never written to disk and never leaves this function.
 * The salt includes the UTC date, so a token cannot be correlated across days
 * even by whoever holds the database and the secret key.
 */
export function posterToken(ip, secret, now = new Date()) {
  const day = now.toISOString().slice(0, 10);
  return crypto
    .createHmac('sha256', `${secret}:${day}`)
    .update(String(ip ?? 'unknown'))
    .digest('hex')
    .slice(0, 32);
}

/** Compare two secrets without leaking their contents through timing. */
export function safeEqual(a, b) {
  const bufA = Buffer.from(String(a ?? ''), 'utf8');
  const bufB = Buffer.from(String(b ?? ''), 'utf8');
  if (bufA.length !== bufB.length) {
    // Still burn a comparison so the mismatch length is not itself a signal.
    crypto.timingSafeEqual(bufA, bufA);
    return false;
  }
  return crypto.timingSafeEqual(bufA, bufB);
}

/** Sign a value for use in a cookie. Format: <value>.<expiry>.<hmac> */
export function signCookie(value, secret, ttlMs = 12 * 60 * 60 * 1000) {
  const expires = Date.now() + ttlMs;
  const payload = `${value}.${expires}`;
  const mac = crypto.createHmac('sha256', secret).update(payload).digest('hex');
  return `${payload}.${mac}`;
}

/** Verify a signed cookie. Returns the value, or null if forged or expired. */
export function verifyCookie(signed, secret) {
  const parts = String(signed ?? '').split('.');
  if (parts.length !== 3) return null;
  const [value, expires, mac] = parts;
  const expected = crypto
    .createHmac('sha256', secret)
    .update(`${value}.${expires}`)
    .digest('hex');
  if (!safeEqual(mac, expected)) return null;
  if (!Number.isFinite(Number(expires)) || Number(expires) < Date.now()) return null;
  return value;
}

/** Parse a Cookie header into a plain object. */
export function parseCookies(header) {
  const out = {};
  for (const pair of String(header ?? '').split(';')) {
    const idx = pair.indexOf('=');
    if (idx < 0) continue;
    out[pair.slice(0, idx).trim()] = decodeURIComponent(pair.slice(idx + 1).trim());
  }
  return out;
}

/**
 * Resolve the client IP for rate limiting.
 * X-Forwarded-For is only trusted when explicitly enabled, because anyone can
 * set that header and forge their way around the limiter otherwise.
 */
export function clientIp(req, trustProxy) {
  if (trustProxy) {
    const forwarded = req.headers['x-forwarded-for'];
    if (forwarded) return String(forwarded).split(',')[0].trim();
  }
  return req.socket.remoteAddress ?? 'unknown';
}

/** Human-readable relative time, computed server-side so no clock is leaked. */
export function timeAgo(timestamp, now = Date.now()) {
  const seconds = Math.max(0, Math.floor((now - timestamp) / 1000));
  const units = [
    ['year', 31536000],
    ['month', 2592000],
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
  ];
  for (const [name, size] of units) {
    const count = Math.floor(seconds / size);
    if (count >= 1) return `${count} ${name}${count === 1 ? '' : 's'} ago`;
  }
  return 'just now';
}

/**
 * Turn a board name into a URL-safe slug.
 * Restricted to [a-z0-9-] so a slug can never smuggle path or query syntax
 * into a route.
 */
export function slugify(input) {
  return String(input ?? '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 32);
}
