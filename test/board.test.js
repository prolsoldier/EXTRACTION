import { test, describe, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createApp } from '../src/server.js';

const ADMIN_TOKEN = 'test-admin-token-0123456789';
const SECRET_KEY = 'test-secret-key';

let server;
let base;

/** Minimal fetch wrapper: never follows redirects, so we can assert on them. */
async function req(pathname, { method = 'GET', form, cookie } = {}) {
  const headers = {};
  if (cookie) headers.Cookie = cookie;
  let body;
  if (form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded';
    body = new URLSearchParams(form).toString();
  }
  const res = await fetch(`${base}${pathname}`, { method, headers, body, redirect: 'manual' });
  return { res, text: await res.text() };
}

async function loginAsOwner() {
  const { res } = await req('/login', { method: 'POST', form: { token: ADMIN_TOKEN } });
  const setCookie = res.headers.get('set-cookie');
  assert.ok(setCookie, 'expected a session cookie');
  return setCookie.split(';')[0];
}

before(async () => {
  ({ server } = createApp({
    adminToken: ADMIN_TOKEN,
    secretKey: SECRET_KEY,
    dbPath: ':memory:',
    boardTitle: 'Test Board',
    postsPerMinute: 3,
  }));
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  base = `http://127.0.0.1:${server.address().port}`;
});

after(() => server.close());

describe('public board', () => {
  test('serves the index', async () => {
    const { res, text } = await req('/');
    assert.equal(res.status, 200);
    assert.match(text, /Test Board/);
    assert.match(text, /Nothing here yet/);
  });

  test('serves the stylesheet', async () => {
    const { res } = await req('/style.css');
    assert.equal(res.status, 200);
    assert.match(res.headers.get('content-type'), /text\/css/);
  });

  test('sets hardening headers', async () => {
    const { res } = await req('/');
    assert.match(res.headers.get('content-security-policy'), /frame-ancestors 'none'/);
    assert.equal(res.headers.get('x-frame-options'), 'DENY');
    assert.equal(res.headers.get('referrer-policy'), 'no-referrer');
    assert.equal(res.headers.get('x-content-type-options'), 'nosniff');
  });

  test('404s an unknown thread', async () => {
    const { res } = await req('/threads/9999');
    assert.equal(res.status, 404);
  });
});

describe('owner authentication', () => {
  test('rejects a wrong token', async () => {
    const { res, text } = await req('/login', { method: 'POST', form: { token: 'wrong' } });
    assert.equal(res.status, 401);
    assert.match(text, /Incorrect token/);
    assert.equal(res.headers.get('set-cookie'), null);
  });

  test('accepts the right token and sets a hardened cookie', async () => {
    const { res } = await req('/login', { method: 'POST', form: { token: ADMIN_TOKEN } });
    assert.equal(res.status, 303);
    const cookie = res.headers.get('set-cookie');
    assert.match(cookie, /HttpOnly/);
    assert.match(cookie, /SameSite=Strict/);
  });

  test('rejects a forged session cookie', async () => {
    const { res } = await req('/threads', {
      method: 'POST',
      form: { title: 'forged' },
      cookie: 'session=owner.99999999999999.deadbeef',
    });
    assert.equal(res.status, 403);
  });

  test('anonymous visitors cannot create threads', async () => {
    const { res } = await req('/threads', { method: 'POST', form: { title: 'nope' } });
    assert.equal(res.status, 403);
  });
});

describe('threads and anonymous replies', () => {
  test('owner creates a thread, anyone can reply anonymously', async () => {
    const cookie = await loginAsOwner();

    const created = await req('/threads', {
      method: 'POST',
      form: { title: 'Rent is too high', body: 'Discuss.' },
      cookie,
    });
    assert.equal(created.res.status, 303);
    const location = created.res.headers.get('location');
    assert.match(location, /^\/threads\/\d+$/);

    // No cookie at all: a stranger off the street.
    const replied = await req(`${location}/messages`, {
      method: 'POST',
      form: { body: 'Agreed, and the landlord raised it again.' },
    });
    assert.equal(replied.res.status, 303);

    const { text } = await req(location);
    assert.match(text, /Rent is too high/);
    assert.match(text, /landlord raised it again/);
    assert.match(text, /anonymous/);
  });

  test('rejects an empty message', async () => {
    const cookie = await loginAsOwner();
    const { res: made } = await req('/threads', {
      method: 'POST',
      form: { title: 'empties' },
      cookie,
    });
    const thread = made.headers.get('location');
    const { res } = await req(`${thread}/messages`, { method: 'POST', form: { body: '   ' } });
    assert.equal(res.status, 400);
  });

  test('silently discards honeypot submissions', async () => {
    const cookie = await loginAsOwner();
    const { res: made } = await req('/threads', {
      method: 'POST',
      form: { title: 'honeypot' },
      cookie,
    });
    const thread = made.headers.get('location');

    const { res } = await req(`${thread}/messages`, {
      method: 'POST',
      form: { body: 'buy cheap pills', website: 'http://spam.example' },
    });
    assert.equal(res.status, 303);

    const { text } = await req(thread);
    assert.doesNotMatch(text, /cheap pills/);
  });
});

describe('escaping', () => {
  test('neutralises injected markup in bodies and titles', async () => {
    const cookie = await loginAsOwner();
    const { res: made } = await req('/threads', {
      method: 'POST',
      form: { title: '<img src=x onerror=alert(1)>' },
      cookie,
    });
    const thread = made.headers.get('location');

    await req(`${thread}/messages`, {
      method: 'POST',
      form: { body: '<script>alert("pwned")</script>' },
    });

    const { text } = await req(thread);
    assert.doesNotMatch(text, /<script>alert/);
    assert.doesNotMatch(text, /<img src=x/);
    assert.match(text, /&lt;script&gt;/);
    assert.match(text, /&lt;img src=x/);
  });
});

describe('moderation', () => {
  test('owner can lock a thread, which then refuses anonymous replies', async () => {
    const cookie = await loginAsOwner();
    const { res: made } = await req('/threads', {
      method: 'POST',
      form: { title: 'lockable' },
      cookie,
    });
    const thread = made.headers.get('location');

    await req(`${thread}/lock`, { method: 'POST', cookie });

    const { res } = await req(`${thread}/messages`, { method: 'POST', form: { body: 'hi' } });
    assert.equal(res.status, 403);
  });

  test('owner can delete a message, leaving a tombstone', async () => {
    const cookie = await loginAsOwner();
    const { res: made } = await req('/threads', {
      method: 'POST',
      form: { title: 'deletable' },
      cookie,
    });
    const thread = made.headers.get('location');

    const { res: posted } = await req(`${thread}/messages`, {
      method: 'POST',
      form: { body: 'delete me please' },
    });
    const messageId = posted.headers.get('location').split('#m')[1];

    const { res: deleted } = await req(`/messages/${messageId}/delete`, { method: 'POST', cookie });
    assert.equal(deleted.status, 303);

    const { text } = await req(thread);
    assert.doesNotMatch(text, /delete me please/);
    assert.match(text, /\[removed by the owner\]/);
  });

  test('anonymous visitors cannot delete messages', async () => {
    const { res } = await req('/messages/1/delete', { method: 'POST' });
    assert.equal(res.status, 403);
  });
});

describe('rate limiting', () => {
  test('cuts off a flood of anonymous posts', async () => {
    const cookie = await loginAsOwner();
    const { res: made } = await req('/threads', {
      method: 'POST',
      form: { title: 'flood' },
      cookie,
    });
    const thread = made.headers.get('location');

    const statuses = [];
    for (let i = 0; i < 8; i++) {
      const { res } = await req(`${thread}/messages`, {
        method: 'POST',
        form: { body: `spam ${i}` },
      });
      statuses.push(res.status);
    }
    assert.ok(statuses.includes(429), `expected a 429 in ${statuses.join(',')}`);
  });
});

describe('health', () => {
  test('reports counts', async () => {
    const { res, text } = await req('/healthz');
    assert.equal(res.status, 200);
    const payload = JSON.parse(text);
    assert.equal(payload.ok, true);
    assert.ok(payload.threads > 0);
  });
});
