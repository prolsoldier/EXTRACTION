import { DatabaseSync } from 'node:sqlite';
import path from 'node:path';
import fs from 'node:fs';

const SCHEMA = `
CREATE TABLE IF NOT EXISTS threads (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
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
CREATE INDEX IF NOT EXISTS idx_threads_bumped  ON threads(pinned DESC, bumped_at DESC);
`;

export function openDatabase(dbPath) {
  if (dbPath !== ':memory:') {
    fs.mkdirSync(path.dirname(path.resolve(dbPath)), { recursive: true });
  }
  const db = new DatabaseSync(dbPath);
  db.exec('PRAGMA journal_mode = WAL');
  db.exec('PRAGMA foreign_keys = ON');
  db.exec(SCHEMA);
  return new Board(db);
}

export class Board {
  constructor(db) {
    this.db = db;
  }

  close() {
    this.db.close();
  }

  // ---- threads -------------------------------------------------------

  createThread({ title, body = '', now = Date.now() }) {
    const info = this.db
      .prepare(
        'INSERT INTO threads (title, body, created_at, bumped_at) VALUES (?, ?, ?, ?)',
      )
      .run(title, body, now, now);
    return Number(info.lastInsertRowid);
  }

  listThreads({ limit = 50, offset = 0 } = {}) {
    return this.db
      .prepare(
        `SELECT t.id, t.title, t.body, t.created_at, t.bumped_at, t.pinned, t.locked,
                (SELECT COUNT(*) FROM messages m
                  WHERE m.thread_id = t.id AND m.deleted = 0) AS reply_count
           FROM threads t
          WHERE t.deleted = 0
          ORDER BY t.pinned DESC, t.bumped_at DESC
          LIMIT ? OFFSET ?`,
      )
      .all(limit, offset);
  }

  getThread(id) {
    return this.db
      .prepare('SELECT * FROM threads WHERE id = ? AND deleted = 0')
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
    const threads = this.db
      .prepare('SELECT COUNT(*) AS n FROM threads WHERE deleted = 0')
      .get().n;
    const messages = this.db
      .prepare('SELECT COUNT(*) AS n FROM messages WHERE deleted = 0')
      .get().n;
    return { threads, messages };
  }
}
