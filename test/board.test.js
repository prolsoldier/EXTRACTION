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

async function createThread(cookie, title, slug = 'general') {
  const { res } = await req(`/b/${slug}/threads`, {
    method: 'POST',
    form: { title },
    cookie,
  });
  assert.equal(res.status, 303, `thread creation failed for "${title}"`);
  return res.headers.get('location');
}

/** Find a board's id by splitting the manage page into rows first. */
function findBoardId(html, name) {
  for (const row of html.split('class="manage-row"').slice(1)) {
    if (row.includes(`value="${name}"`)) {
      return row.match(/action="\/manage\/(\d+)"/)?.[1] ?? null;
    }
  }
  return null;
}

let ownerCookie = null;

/**
 * Log in once and reuse the session across tests. Logging in per test would
 * trip the login throttle, which has its own dedicated test below.
 */
async function loginAsOwner() {
  if (ownerCookie) return ownerCookie;
  const { res } = await req('/login', { method: 'POST', form: { token: ADMIN_TOKEN } });
  const setCookie = res.headers.get('set-cookie');
  assert.ok(setCookie, 'expected a session cookie');
  ownerCookie = setCookie.split(';')[0];
  return ownerCookie;
}

before(async () => {
  ({ server } = createApp({
    adminToken: ADMIN_TOKEN,
    secretKey: SECRET_KEY,
    dbPath: ':memory:',
    boardTitle: 'Test Board',
    postsPerMinute: 3,
    seedBoards: [
      { slug: 'organizing', name: 'Organizing', description: 'Tactics and wins.', position: 1 },
      { slug: 'general', name: 'General', description: 'Everything else.', position: 2 },
    ],
  }));
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  base = `http://127.0.0.1:${server.address().port}`;
});

after(() => server.close());

describe('public board', () => {
  test('serves the board index', async () => {
    const { res, text } = await req('/');
    assert.equal(res.status, 200);
    assert.match(text, /Test Board/);
    assert.match(text, /Organizing/);
    assert.match(text, /General/);
  });

  test('serves an individual board', async () => {
    const { res, text } = await req('/b/organizing');
    assert.equal(res.status, 200);
    assert.match(text, /Tactics and wins/);
  });

  test('404s an unknown board', async () => {
    const { res } = await req('/b/nonexistent');
    assert.equal(res.status, 404);
  });

  test('rejects a slug carrying path syntax', async () => {
    const { res } = await req('/b/..%2F..%2Fetc');
    assert.equal(res.status, 404);
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
    const { res } = await req('/b/general/threads', {
      method: 'POST',
      form: { title: 'forged' },
      cookie: 'session=owner.99999999999999.deadbeef',
    });
    assert.equal(res.status, 403);
  });

  test('anonymous visitors cannot create threads', async () => {
    const { res } = await req('/b/general/threads', {
      method: 'POST',
      form: { title: 'nope' },
    });
    assert.equal(res.status, 403);
  });
});

describe('threads and anonymous replies', () => {
  test('owner creates a thread, anyone can reply anonymously', async () => {
    const cookie = await loginAsOwner();

    const created = await req('/b/organizing/threads', {
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
    const thread = await createThread(cookie, 'empties');
    const { res } = await req(`${thread}/messages`, { method: 'POST', form: { body: '   ' } });
    assert.equal(res.status, 400);
  });

  test('silently discards honeypot submissions', async () => {
    const cookie = await loginAsOwner();
    const thread = await createThread(cookie, 'honeypot');

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
    const thread = await createThread(cookie, '<img src=x onerror=alert(1)>');

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
    const thread = await createThread(cookie, 'lockable');

    await req(`${thread}/lock`, { method: 'POST', cookie });

    const { res } = await req(`${thread}/messages`, { method: 'POST', form: { body: 'hi' } });
    assert.equal(res.status, 403);
  });

  test('owner can delete a message, leaving a tombstone', async () => {
    const cookie = await loginAsOwner();
    const thread = await createThread(cookie, 'deletable');

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
    const thread = await createThread(cookie, 'flood');

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

describe('board management', () => {
  test('anonymous visitors cannot reach or change boards', async () => {
    const view = await req('/manage');
    assert.equal(view.res.status, 403);

    const create = await req('/manage', { method: 'POST', form: { name: 'Sneaky' } });
    assert.equal(create.res.status, 403);

    const { text } = await req('/');
    assert.doesNotMatch(text, /Sneaky/);
  });

  test('owner creates a board and it appears at its slug', async () => {
    const cookie = await loginAsOwner();
    const { res } = await req('/manage', {
      method: 'POST',
      form: { name: 'Femboy Fan Club', description: 'Be decent to each other.' },
      cookie,
    });
    assert.equal(res.status, 303);
    assert.equal(res.headers.get('location'), '/b/femboy-fan-club');

    const { res: page, text } = await req('/b/femboy-fan-club');
    assert.equal(page.status, 200);
    assert.match(text, /Be decent to each other/);
  });

  test('refuses a duplicate slug', async () => {
    const cookie = await loginAsOwner();
    const { res } = await req('/manage', {
      method: 'POST',
      form: { name: 'General' },
      cookie,
    });
    assert.equal(res.status, 409);
  });

  test('refuses a name that yields no usable slug', async () => {
    const cookie = await loginAsOwner();
    const { res } = await req('/manage', { method: 'POST', form: { name: '!!!' }, cookie });
    assert.equal(res.status, 400);
  });

  test('owner renames a board without breaking its slug', async () => {
    const cookie = await loginAsOwner();
    await req('/manage', { method: 'POST', form: { name: 'Renameable' }, cookie });

    const { text: managePage } = await req('/manage', { cookie });
    const id = findBoardId(managePage, 'Renameable');
    assert.ok(id, 'could not locate the board id on the manage page');

    const { res } = await req(`/manage/${id}`, {
      method: 'POST',
      form: { name: 'Renamed', description: 'now with a description', position: '7' },
      cookie,
    });
    assert.equal(res.status, 303);

    const { text } = await req('/b/renameable');
    assert.match(text, /Renamed/);
    assert.match(text, /now with a description/);
  });

  test('a locked board refuses new threads and anonymous replies', async () => {
    const cookie = await loginAsOwner();
    await req('/manage', { method: 'POST', form: { name: 'Closing Soon' }, cookie });
    const thread = await createThread(cookie, 'last call', 'closing-soon');

    const { text: managePage } = await req('/manage', { cookie });
    const id = findBoardId(managePage, 'Closing Soon');
    assert.ok(id, 'could not locate the board id');

    await req(`/manage/${id}/lock`, { method: 'POST', cookie });

    const reply = await req(`${thread}/messages`, { method: 'POST', form: { body: 'hi' } });
    assert.equal(reply.res.status, 403);

    const newThread = await req('/b/closing-soon/threads', {
      method: 'POST',
      form: { title: 'nope' },
      cookie,
    });
    assert.equal(newThread.res.status, 403);
  });

  test('deleting a board hides it from the index', async () => {
    const cookie = await loginAsOwner();
    await req('/manage', { method: 'POST', form: { name: 'Temporary' }, cookie });

    const { text: managePage } = await req('/manage', { cookie });
    const id = findBoardId(managePage, 'Temporary');
    assert.ok(id, 'could not locate the board id');

    const { res } = await req(`/manage/${id}/delete`, { method: 'POST', cookie });
    assert.equal(res.status, 303);

    const { text } = await req('/');
    assert.doesNotMatch(text, /Temporary/);
    const { res: gone } = await req('/b/temporary');
    assert.equal(gone.status, 404);
  });
});

describe('login throttling', () => {
  test('cuts off repeated wrong-token attempts', async () => {
    const { server: isolated } = createApp({
      adminToken: ADMIN_TOKEN,
      secretKey: SECRET_KEY,
      dbPath: ':memory:',
      loginsPerHour: 3,
      seedBoards: [],
    });
    await new Promise((resolve) => isolated.listen(0, '127.0.0.1', resolve));
    const isolatedBase = `http://127.0.0.1:${isolated.address().port}`;

    try {
      const statuses = [];
      for (let i = 0; i < 6; i++) {
        const res = await fetch(`${isolatedBase}/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({ token: 'guessing' }).toString(),
          redirect: 'manual',
        });
        statuses.push(res.status);
        await res.text();
      }
      assert.ok(statuses.includes(429), `expected a 429 in ${statuses.join(',')}`);
    } finally {
      isolated.close();
    }
  });
});

describe('health', () => {
  test('reports counts', async () => {
    const { res, text } = await req('/healthz');
    assert.equal(res.status, 200);
    const payload = JSON.parse(text);
    assert.equal(payload.ok, true);
    assert.ok(payload.threads > 0);
    assert.ok(payload.boards >= 2);
  });
});
