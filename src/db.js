import { DatabaseSync } from 'node:sqlite';
import path from 'node:path';
import fs from 'node:fs';

const SCHEMA = `
CREATE TABLE IF NOT EXISTS boards (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  slug        TEXT    NOT NULL UNIQUE,
  name        TEXT    NOT NULL,
  description TEXT    NOT NULL DEFAULT '',
  kind        TEXT    NOT NULL DEFAULT 'forum',
  position    INTEGER NOT NULL DEFAULT 0,
  locked      INTEGER NOT NULL DEFAULT 0,
  deleted     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS threads (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  board_id    INTEGER REFERENCES boards(id),
  title       TEXT    NOT NULL,
  body        TEXT    NOT NULL DEFAULT '',
  created_at  INTEGER NOT NULL,
  bumped_at   INTEGER NOT NULL,
  pinned      INTEGER NOT NULL DEFAULT 0,
  locked      INTEGER NOT NULL DEFAULT 0,
  deleted     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id   INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
  body        TEXT    NOT NULL,
  created_at  INTEGER NOT NULL,
  is_owner    INTEGER NOT NULL DEFAULT 0,
  deleted     INTEGER NOT NULL DEFAULT 0
);

-- Rate limiting only. Holds a salted, daily-rotating hash, never an IP.
CREATE TABLE IF NOT EXISTS rate_limits (
  token        TEXT    NOT NULL,
  window_start INTEGER NOT NULL,
  count        INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (token, window_start)
);

CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, id);
CREATE INDEX IF NOT EXISTS idx_threads_bumped  ON threads(board_id, pinned DESC, bumped_at DESC);
CREATE INDEX IF NOT EXISTS idx_boards_position ON boards(position, id);
`;

export function openDatabase(dbPath) {
  if (dbPath !== ':memory:') {
    fs.mkdirSync(path.dirname(path.resolve(dbPath)), { recursive: true });
  }
  const db = new DatabaseSync(dbPath);
  db.exec('PRAGMA journal_mode = WAL');
  db.exec('PRAGMA foreign_keys = ON');
  db.exec(SCHEMA);
  migrate(db);
  return new Board(db);
}

/**
 * Bring a database created before boards existed up to the current schema.
 * Safe to run on every start: each step checks before it acts.
 */
function migrate(db) {
  const boardColumns = db.prepare('PRAGMA table_info(boards)').all().map((c) => c.name);
  if (!boardColumns.includes('kind')) {
    db.exec("ALTER TABLE boards ADD COLUMN kind TEXT NOT NULL DEFAULT 'forum'");
  }

  const columns = db.prepare('PRAGMA table_info(threads)').all().map((c) => c.name);

  if (!columns.includes('board_id')) {
    db.exec('ALTER TABLE threads ADD COLUMN board_id INTEGER REFERENCES boards(id)');
  }

  const orphans = db
    .prepare('SELECT COUNT(*) AS n FROM threads WHERE board_id IS NULL')
    .get().n;

  if (orphans > 0) {
    // Park pre-existing threads on a general board rather than dropping them.
    db.prepare(
      `INSERT INTO boards (slug, name, description, position)
       VALUES ('general', 'General', 'Everything else.', 999)
       ON CONFLICT(slug) DO NOTHING`,
    ).run();
    const general = db.prepare("SELECT id FROM boards WHERE slug = 'general'").get();
    db.prepare('UPDATE threads SET board_id = ? WHERE board_id IS NULL').run(general.id);
  }
}

export class Board {
  constructor(db) {
    this.db = db;
  }

  close() {
    this.db.close();
  }

  // ---- boards --------------------------------------------------------

  createBoard({ slug, name, description = '', kind = 'forum', position = 0, now = Date.now() }) {
    if (!['forum', 'wall'].includes(kind)) {
      throw new Error(`unknown board kind: ${kind}`);
    }
    const info = this.db
      .prepare(
        'INSERT INTO boards (slug, name, description, kind, position) VALUES (?, ?, ?, ?, ?)',
      )
      .run(slug, name, description, kind, position);
    const boardId = Number(info.lastInsertRowid);

    // A wall is one continuous stream, so it carries a single backing thread
    // that visitors never see. This reuses the messages table as-is.
    if (kind === 'wall') {
      this.db
        .prepare(
          'INSERT INTO threads (board_id, title, body, created_at, bumped_at) VALUES (?, ?, ?, ?, ?)',
        )
        .run(boardId, name, '', now, now);
    }
    return boardId;
  }

  /** The single backing thread behind a wall board. */
  getWallThread(boardId) {
    return this.db
      .prepare('SELECT * FROM threads WHERE board_id = ? AND deleted = 0 ORDER BY id ASC LIMIT 1')
      .get(boardId);
  }

  listBoards() {
    return this.db
      .prepare(
        `SELECT b.id, b.slug, b.name, b.description, b.kind, b.position, b.locked,
                (SELECT COUNT(*) FROM threads t
                  WHERE t.board_id = b.id AND t.deleted = 0) AS thread_count,
                (SELECT COUNT(*) FROM messages m
                   JOIN threads t ON t.id = m.thread_id
                  WHERE t.board_id = b.id AND m.deleted = 0) AS message_count,
                (SELECT MAX(t.bumped_at) FROM threads t
                  WHERE t.board_id = b.id AND t.deleted = 0) AS last_active
           FROM boards b
          WHERE b.deleted = 0
          ORDER BY b.position ASC, b.id ASC`,
      )
      .all();
  }

  getBoardBySlug(slug) {
    return this.db
      .prepare('SELECT * FROM boards WHERE slug = ? AND deleted = 0')
      .get(slug);
  }

  getBoard(id) {
    return this.db.prepare('SELECT * FROM boards WHERE id = ? AND deleted = 0').get(id);
  }

  updateBoard(id, { name, description, position }) {
    this.db
      .prepare('UPDATE boards SET name = ?, description = ?, position = ? WHERE id = ?')
      .run(name, description, position, id);
  }

  setBoardFlag(id, field, value) {
    if (!['locked', 'deleted'].includes(field)) {
      throw new Error(`refusing to update unknown column: ${field}`);
    }
    this.db.prepare(`UPDATE boards SET ${field} = ? WHERE id = ?`).run(value ? 1 : 0, id);
  }

  /** True when no board exists yet, so the caller knows to seed defaults. */
  isEmpty() {
    return this.db.prepare('SELECT COUNT(*) AS n FROM boards').get().n === 0;
  }

  // ---- threads -------------------------------------------------------

  createThread({ boardId, title, body = '', now = Date.now() }) {
    const info = this.db
      .prepare(
        'INSERT INTO threads (board_id, title, body, created_at, bumped_at) VALUES (?, ?, ?, ?, ?)',
      )
      .run(boardId, title, body, now, now);
    return Number(info.lastInsertRowid);
  }

  listThreads({ boardId, limit = 50, offset = 0 } = {}) {
    return this.db
      .prepare(
        `SELECT t.id, t.board_id, t.title, t.body, t.created_at, t.bumped_at,
                t.pinned, t.locked,
                (SELECT COUNT(*) FROM messages m
                  WHERE m.thread_id = t.id AND m.deleted = 0) AS reply_count
           FROM threads t
          WHERE t.deleted = 0 AND (? IS NULL OR t.board_id = ?)
          ORDER BY t.pinned DESC, t.bumped_at DESC
          LIMIT ? OFFSET ?`,
      )
      .all(boardId ?? null, boardId ?? null, limit, offset);
  }

  getThread(id) {
    return this.db
      .prepare(
        `SELECT t.*, b.slug AS board_slug, b.name AS board_name, b.locked AS board_locked
           FROM threads t
           LEFT JOIN boards b ON b.id = t.board_id
          WHERE t.id = ? AND t.deleted = 0`,
      )
      .get(id);
  }

  setThreadFlag(id, field, value) {
    if (!['pinned', 'locked', 'deleted'].includes(field)) {
      throw new Error(`refusing to update unknown column: ${field}`);
    }
    this.db
      .prepare(`UPDATE threads SET ${field} = ? WHERE id = ?`)
      .run(value ? 1 : 0, id);
  }

  // ---- messages ------------------------------------------------------

  addMessage({ threadId, body, isOwner = false, now = Date.now() }) {
    const info = this.db
      .prepare(
        'INSERT INTO messages (thread_id, body, created_at, is_owner) VALUES (?, ?, ?, ?)',
      )
      .run(threadId, body, now, isOwner ? 1 : 0);
    this.db.prepare('UPDATE threads SET bumped_at = ? WHERE id = ?').run(now, threadId);
    return Number(info.lastInsertRowid);
  }

  listMessages(threadId) {
    return this.db
      .prepare(
        `SELECT id, thread_id, body, created_at, is_owner, deleted
           FROM messages
          WHERE thread_id = ?
          ORDER BY id ASC`,
      )
      .all(threadId);
  }

  deleteMessage(id) {
    this.db.prepare('UPDATE messages SET deleted = 1 WHERE id = ?').run(id);
  }

  getMessage(id) {
    return this.db.prepare('SELECT * FROM messages WHERE id = ?').get(id);
  }

  // ---- rate limiting -------------------------------------------------

  /**
   * Fixed-window limiter keyed on the rotating poster token.
   * Returns true when the post is allowed, false when the caller is over quota.
   */
  checkRateLimit(token, { limit = 10, windowMs = 60_000, now = Date.now() } = {}) {
    const windowStart = Math.floor(now / windowMs) * windowMs;
    const row = this.db
      .prepare('SELECT count FROM rate_limits WHERE token = ? AND window_start = ?')
      .get(token, windowStart);

    if (row && row.count >= limit) return false;

    this.db
      .prepare(
        `INSERT INTO rate_limits (token, window_start, count) VALUES (?, ?, 1)
         ON CONFLICT(token, window_start) DO UPDATE SET count = count + 1`,
      )
      .run(token, windowStart);
    return true;
  }

  /** Drop stale limiter rows so the table never becomes a usage history. */
  pruneRateLimits(olderThanMs = 3_600_000, now = Date.now()) {
    this.db.prepare('DELETE FROM rate_limits WHERE window_start < ?').run(now - olderThanMs);
  }

  stats() {
    const boards = this.db
      .prepare('SELECT COUNT(*) AS n FROM boards WHERE deleted = 0')
      .get().n;
    const threads = this.db
      .prepare('SELECT COUNT(*) AS n FROM threads WHERE deleted = 0')
      .get().n;
    const messages = this.db
      .prepare('SELECT COUNT(*) AS n FROM messages WHERE deleted = 0')
      .get().n;
    return { boards, threads, messages };
  }
}
