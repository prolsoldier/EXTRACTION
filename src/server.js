import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

import { openDatabase } from './db.js';
import {
  renderBoardIndex,
  renderBoard,
  renderWall,
  renderThread,
  renderManage,
  renderLogin,
  renderError,
} from './views.js';
import {
  posterToken,
  safeEqual,
  signCookie,
  verifyCookie,
  parseCookies,
  clientIp,
  slugify,
} from './util.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MAX_BODY_BYTES = 64 * 1024;
const MAX_MESSAGE_LENGTH = 10_000;
const MAX_TITLE_LENGTH = 200;
const MAX_BOARD_NAME_LENGTH = 60;
const MAX_BOARD_DESC_LENGTH = 200;
const MAX_NOTE_LENGTH = 1000;

/**
 * Seeded only when the boards table is empty. Everything here is editable and
 * deletable from /manage, so these are a starting point, not a fixture.
 */
const DEFAULT_BOARDS = [
  { slug: 'organizing', name: 'Organizing', description: 'Workplace and tenant organizing. Tactics, wins, losses.', position: 1 },
  { slug: 'theory', name: 'Theory', description: 'Reading, study groups, and argument.', position: 2 },
  { slug: 'news', name: 'News & Analysis', description: 'What happened, and what it means.', position: 3 },
  { slug: 'femboys', name: 'Femboy Fan Club', description: 'Be decent to each other in here.', position: 4 },
  { slug: 'general', name: 'General', description: 'Everything else.', position: 5 },
  {
    slug: 'kind-words',
    name: 'Kind Words',
    description: 'Leave an anonymous note for someone. Nothing cruel.',
    kind: 'wall',
    position: 6,
  },
];

const SECURITY_HEADERS = {
  'Content-Security-Policy':
    "default-src 'none'; style-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'no-referrer',
  'Permissions-Policy': 'geolocation=(), microphone=(), camera=(), interest-cohort=()',
  'Cache-Control': 'no-store',
};

/** Read a urlencoded request body, refusing anything oversized. */
function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new Error('request body too large'));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => {
      const params = new URLSearchParams(Buffer.concat(chunks).toString('utf8'));
      resolve(Object.fromEntries(params));
    });
    req.on('error', reject);
  });
}

export function createApp(config) {
  const {
    adminToken,
    secretKey,
    dbPath = ':memory:',
    boardTitle = 'Anonymous Board',
    boardTagline = 'Say what you need to say.',
    trustProxy = false,
    postsPerMinute = 5,
    loginsPerHour = 10,
    seedBoards = DEFAULT_BOARDS,
  } = config;

  if (!adminToken) throw new Error('ADMIN_TOKEN is required');
  if (!secretKey) throw new Error('SECRET_KEY is required');

  const board = openDatabase(dbPath);
  const css = fs.readFileSync(path.join(HERE, '..', 'public', 'style.css'), 'utf8');

  // Only on a genuinely fresh database, so an owner who deletes a seeded board
  // does not find it resurrected on the next restart.
  if (board.isEmpty()) {
    for (const b of seedBoards) board.createBoard(b);
  }

  // Keep the limiter table from turning into a record of who posted when.
  const pruneTimer = setInterval(() => board.pruneRateLimits(), 10 * 60_000);
  pruneTimer.unref?.();

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, `http://${req.headers.host ?? 'localhost'}`);
    const pathname = url.pathname;
    const cookies = parseCookies(req.headers.cookie);
    const isAdmin = verifyCookie(cookies.session, secretKey) === 'owner';
    const notice = url.searchParams.get('notice') ?? '';

    const send = (status, html, extraHeaders = {}) => {
      res.writeHead(status, {
        'Content-Type': 'text/html; charset=utf-8',
        ...SECURITY_HEADERS,
        ...extraHeaders,
      });
      res.end(html);
    };

    const redirect = (location, extraHeaders = {}) => {
      res.writeHead(303, { Location: location, ...SECURITY_HEADERS, ...extraHeaders });
      res.end();
    };

    const fail = (code, message) =>
      send(code, renderError({ title: boardTitle, tagline: boardTagline, isAdmin, code, message }));

    const requireAdmin = () => {
      if (isAdmin) return true;
      fail(403, 'Only the board owner can do that.');
      return false;
    };

    try {
      // ---- static + health ------------------------------------------
      if (req.method === 'GET' && pathname === '/style.css') {
        res.writeHead(200, {
          'Content-Type': 'text/css; charset=utf-8',
          'Cache-Control': 'public, max-age=3600',
          'X-Content-Type-Options': 'nosniff',
        });
        return res.end(css);
      }

      if (req.method === 'GET' && pathname === '/healthz') {
        res.writeHead(200, { 'Content-Type': 'application/json', ...SECURITY_HEADERS });
        return res.end(JSON.stringify({ ok: true, ...board.stats() }));
      }

      // ---- boards ---------------------------------------------------
      const boards = board.listBoards();

      if (req.method === 'GET' && pathname === '/') {
        return send(
          200,
          renderBoardIndex({
            title: boardTitle,
            tagline: boardTagline,
            isAdmin,
            boards,
            notice,
          }),
        );
      }

      const boardMatch = pathname.match(/^\/b\/([a-z0-9-]{1,32})$/);
      if (req.method === 'GET' && boardMatch) {
        const current = board.getBoardBySlug(boardMatch[1]);
        if (!current) return fail(404, 'That board does not exist.');

        if (current.kind === 'wall') {
          const wall = board.getWallThread(current.id);
          const notes = wall ? board.listMessages(wall.id).reverse() : [];
          return send(
            200,
            renderWall({
              title: boardTitle,
              tagline: boardTagline,
              isAdmin,
              board: current,
              boards,
              messages: notes,
              notice,
            }),
          );
        }

        return send(
          200,
          renderBoard({
            title: boardTitle,
            tagline: boardTagline,
            isAdmin,
            board: current,
            boards,
            threads: board.listThreads({ boardId: current.id }),
            notice,
          }),
        );
      }

      const threadMatch = pathname.match(/^\/threads\/(\d+)$/);
      if (req.method === 'GET' && threadMatch) {
        const thread = board.getThread(Number(threadMatch[1]));
        if (!thread) return fail(404, 'That thread does not exist.');
        return send(
          200,
          renderThread({
            title: boardTitle,
            tagline: boardTagline,
            isAdmin,
            board: thread.board_id ? board.getBoard(thread.board_id) : null,
            boards,
            thread,
            messages: board.listMessages(thread.id),
            notice,
          }),
        );
      }

      // ---- auth -----------------------------------------------------
      if (req.method === 'GET' && pathname === '/login') {
        if (isAdmin) return redirect('/');
        return send(200, renderLogin({ title: boardTitle, tagline: boardTagline, notice }));
      }

      if (req.method === 'POST' && pathname === '/login') {
        const token = posterToken(clientIp(req, trustProxy), secretKey);
        if (!board.checkRateLimit(`login:${token}`, { limit: loginsPerHour, windowMs: 3_600_000 })) {
          return fail(429, 'Too many login attempts. Try again later.');
        }
        const form = await readBody(req);
        if (!safeEqual(form.token ?? '', adminToken)) {
          return send(
            401,
            renderLogin({
              title: boardTitle,
              tagline: boardTagline,
              notice: 'Incorrect token.',
            }),
          );
        }
        return redirect('/', {
          'Set-Cookie': `session=${signCookie('owner', secretKey)}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200`,
        });
      }

      if (req.method === 'POST' && pathname === '/logout') {
        return redirect('/', {
          'Set-Cookie': 'session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0',
        });
      }

      // ---- posting --------------------------------------------------
      const wallPostMatch = pathname.match(/^\/b\/([a-z0-9-]{1,32})\/post$/);
      if (req.method === 'POST' && wallPostMatch) {
        const current = board.getBoardBySlug(wallPostMatch[1]);
        if (!current) return fail(404, 'That board does not exist.');
        if (current.kind !== 'wall') return fail(404, 'That board does not take notes.');
        if (current.locked && !isAdmin) return fail(403, 'This wall is closed.');

        const form = await readBody(req);
        if (form.website) return redirect(`/b/${current.slug}`); // honeypot

        const body = String(form.body ?? '').trim().slice(0, MAX_NOTE_LENGTH);
        if (!body) return fail(400, 'An empty note has nothing to say.');

        if (!isAdmin) {
          const token = posterToken(clientIp(req, trustProxy), secretKey);
          if (!board.checkRateLimit(token, { limit: postsPerMinute, windowMs: 60_000 })) {
            return fail(429, 'You are posting too quickly. Wait a minute and try again.');
          }
        }

        const wall = board.getWallThread(current.id);
        if (!wall) return fail(500, 'That wall is missing its backing thread.');
        board.addMessage({ threadId: wall.id, body, isOwner: isAdmin });
        return redirect(`/b/${current.slug}?notice=Posted.`);
      }

      const newThreadMatch = pathname.match(/^\/b\/([a-z0-9-]{1,32})\/threads$/);
      if (req.method === 'POST' && newThreadMatch) {
        if (!requireAdmin()) return;
        const current = board.getBoardBySlug(newThreadMatch[1]);
        if (!current) return fail(404, 'That board does not exist.');
        if (current.kind === 'wall') return fail(404, 'A wall does not take threads.');
        if (current.locked) return fail(403, 'That board is locked.');

        const form = await readBody(req);
        if (form.website) return redirect(`/b/${current.slug}`); // honeypot
        const title = String(form.title ?? '').trim().slice(0, MAX_TITLE_LENGTH);
        const body = String(form.body ?? '').trim().slice(0, MAX_MESSAGE_LENGTH);
        if (!title) return fail(400, 'A thread needs a title.');

        const id = board.createThread({ boardId: current.id, title, body });
        return redirect(`/threads/${id}`);
      }

      const replyMatch = pathname.match(/^\/threads\/(\d+)\/messages$/);
      if (req.method === 'POST' && replyMatch) {
        const thread = board.getThread(Number(replyMatch[1]));
        if (!thread) return fail(404, 'That thread does not exist.');
        if ((thread.locked || thread.board_locked) && !isAdmin) {
          return fail(403, 'This thread is locked.');
        }

        const form = await readBody(req);
        if (form.website) return redirect(`/threads/${thread.id}`); // honeypot

        const body = String(form.body ?? '').trim().slice(0, MAX_MESSAGE_LENGTH);
        if (!body) return fail(400, 'An empty message has nothing to say.');

        // The raw IP is hashed here and immediately discarded. Owners skip the limit.
        if (!isAdmin) {
          const token = posterToken(clientIp(req, trustProxy), secretKey);
          if (!board.checkRateLimit(token, { limit: postsPerMinute, windowMs: 60_000 })) {
            return fail(429, 'You are posting too quickly. Wait a minute and try again.');
          }
        }

        const id = board.addMessage({ threadId: thread.id, body, isOwner: isAdmin });
        return redirect(`/threads/${thread.id}#m${id}`);
      }

      // ---- board management (owner only) -----------------------------
      if (req.method === 'GET' && pathname === '/manage') {
        if (!requireAdmin()) return;
        return send(
          200,
          renderManage({ title: boardTitle, tagline: boardTagline, boards, notice }),
        );
      }

      if (req.method === 'POST' && pathname === '/manage') {
        if (!requireAdmin()) return;
        const form = await readBody(req);
        const name = String(form.name ?? '').trim().slice(0, MAX_BOARD_NAME_LENGTH);
        const description = String(form.description ?? '')
          .trim()
          .slice(0, MAX_BOARD_DESC_LENGTH);
        if (!name) return fail(400, 'A board needs a name.');

        const slug = slugify(form.slug || name);
        if (!slug) return fail(400, 'That name does not produce a usable slug. Set one manually.');
        if (board.getBoardBySlug(slug)) return fail(409, `A board at /b/${slug} already exists.`);

        const kind = form.kind === 'wall' ? 'wall' : 'forum';
        const position = boards.length ? Math.max(...boards.map((b) => b.position)) + 1 : 1;
        board.createBoard({ slug, name, description, kind, position });
        return redirect(`/b/${slug}`);
      }

      const manageMatch = pathname.match(/^\/manage\/(\d+)(?:\/(lock|delete))?$/);
      if (req.method === 'POST' && manageMatch) {
        if (!requireAdmin()) return;
        const [, rawId, action] = manageMatch;
        const current = board.getBoard(Number(rawId));
        if (!current) return fail(404, 'That board does not exist.');

        if (action === 'delete') {
          board.setBoardFlag(current.id, 'deleted', 1);
          return redirect('/manage?notice=Board+hidden.+Its+threads+are+still+on+disk.');
        }
        if (action === 'lock') {
          board.setBoardFlag(current.id, 'locked', current.locked ? 0 : 1);
          return redirect('/manage');
        }

        const form = await readBody(req);
        const name = String(form.name ?? '').trim().slice(0, MAX_BOARD_NAME_LENGTH);
        const description = String(form.description ?? '')
          .trim()
          .slice(0, MAX_BOARD_DESC_LENGTH);
        if (!name) return fail(400, 'A board needs a name.');

        const parsed = Number.parseInt(form.position, 10);
        const position = Number.isFinite(parsed) ? parsed : current.position;

        board.updateBoard(current.id, { name, description, position });
        return redirect('/manage?notice=Saved.');
      }

      // ---- moderation ------------------------------------------------
      const flagMatch = pathname.match(/^\/threads\/(\d+)\/(pin|lock|delete)$/);
      if (req.method === 'POST' && flagMatch) {
        if (!requireAdmin()) return;
        const [, rawId, action] = flagMatch;
        const thread = board.getThread(Number(rawId));
        if (!thread) return fail(404, 'That thread does not exist.');

        if (action === 'delete') {
          board.setThreadFlag(thread.id, 'deleted', 1);
          const back = thread.board_slug ? `/b/${thread.board_slug}` : '/';
          return redirect(`${back}?notice=Thread+deleted.`);
        }
        const field = action === 'pin' ? 'pinned' : 'locked';
        board.setThreadFlag(thread.id, field, thread[field] ? 0 : 1);
        return redirect(`/threads/${thread.id}`);
      }

      const deleteMatch = pathname.match(/^\/messages\/(\d+)\/delete$/);
      if (req.method === 'POST' && deleteMatch) {
        if (!requireAdmin()) return;
        const message = board.getMessage(Number(deleteMatch[1]));
        if (!message) return fail(404, 'That message does not exist.');
        board.deleteMessage(message.id);
        return redirect(`/threads/${message.thread_id}`);
      }

      return fail(404, 'No such page.');
    } catch (err) {
      if (/too large/.test(err.message)) return fail(413, 'That message is too large.');
      console.error('[error]', err);
      return fail(500, 'Something broke on our end.');
    }
  });

  server.on('close', () => {
    clearInterval(pruneTimer);
    board.close();
  });

  return { server, board };
}

// ---- CLI entry point --------------------------------------------------

function loadDotEnv(file = '.env') {
  if (!fs.existsSync(file)) return;
  for (const line of fs.readFileSync(file, 'utf8').split('\n')) {
    const match = line.match(/^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)\s*$/i);
    if (!match) continue;
    const [, key, rawValue] = match;
    if (process.env[key] === undefined) {
      process.env[key] = rawValue.replace(/^["']|["']$/g, '');
    }
  }
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (isMain) {
  loadDotEnv();

  const adminToken = process.env.ADMIN_TOKEN;
  const secretKey = process.env.SECRET_KEY;

  if (!adminToken || !secretKey) {
    console.error(
      'Missing ADMIN_TOKEN and/or SECRET_KEY.\n\n' +
        'Copy .env.example to .env and fill them in. Generate values with:\n' +
        `  node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"\n`,
    );
    process.exit(1);
  }

  if (adminToken.length < 16) {
    console.error('ADMIN_TOKEN is too short. Use at least 16 characters.');
    process.exit(1);
  }

  const { server } = createApp({
    adminToken,
    secretKey,
    dbPath: process.env.DB_PATH ?? './data/board.db',
    boardTitle: process.env.BOARD_TITLE,
    boardTagline: process.env.BOARD_TAGLINE,
    trustProxy: process.env.TRUST_PROXY === '1',
  });

  const port = Number(process.env.PORT ?? 3000);
  const host = process.env.HOST ?? '127.0.0.1';

  server.listen(port, host, () => {
    console.log(`anonboard listening on http://${host}:${port}`);
  });

  for (const signal of ['SIGINT', 'SIGTERM']) {
    process.on(signal, () => {
      console.log(`\n${signal} received, shutting down.`);
      server.close(() => process.exit(0));
    });
  }
}
