import { escapeHtml, renderBody, timeAgo } from './util.js';

function layout({ title, tagline, isAdmin, body, boards = [], activeSlug = '', notice = '' }) {
  const boardNav = boards.length
    ? `<nav class="board-nav">${boards
        .map(
          (b) =>
            `<a class="board-tab${b.slug === activeSlug ? ' active' : ''}" href="/b/${escapeHtml(b.slug)}">${escapeHtml(b.name)}</a>`,
        )
        .join('')}</nav>`
    : '';

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>${escapeHtml(title)}</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<header class="site-header">
  <a class="brand" href="/">${escapeHtml(title)}</a>
  <p class="tagline">${escapeHtml(tagline)}</p>
  ${boardNav}
  <nav class="owner-nav">
    ${
      isAdmin
        ? '<span class="badge owner">owner mode</span> <a class="linkish" href="/manage">manage boards</a> <form class="inline" method="post" action="/logout"><button class="linkish" type="submit">log out</button></form>'
        : '<a class="linkish" href="/login">owner login</a>'
    }
  </nav>
</header>
${notice ? `<div class="notice">${escapeHtml(notice)}</div>` : ''}
<main>
${body}
</main>
<footer>
  <p>No accounts. No tracking. No IP addresses stored.</p>
</footer>
</body>
</html>`;
}

/** Front page: the list of boards on this instance. */
export function renderBoardIndex({ title, tagline, isAdmin, boards, notice }) {
  const list = boards.length
    ? boards
        .map(
          (b) => `<li class="board-row">
  <a class="board-link" href="/b/${escapeHtml(b.slug)}">${escapeHtml(b.name)}</a>
  ${b.description ? `<p class="board-desc">${escapeHtml(b.description)}</p>` : ''}
  <div class="meta">
    ${b.locked ? '<span class="badge locked">locked</span>' : ''}
    <span>${
      b.kind === 'wall'
        ? `${b.message_count} ${b.message_count === 1 ? 'note' : 'notes'}`
        : `${b.thread_count} ${b.thread_count === 1 ? 'thread' : 'threads'}`
    }</span>
    ${b.last_active ? `<span>&middot;</span><span>active ${escapeHtml(timeAgo(b.last_active))}</span>` : ''}
  </div>
</li>`,
        )
        .join('')
    : '<li class="empty">No boards yet.</li>';

  return layout({
    title,
    tagline,
    isAdmin,
    boards,
    notice,
    body: `<section class="card">
  <h2>Boards</h2>
  <ul class="boards">${list}</ul>
</section>`,
  });
}

/** One board: its threads, plus the owner's new-thread form. */
export function renderBoard({ title, tagline, isAdmin, board, boards, threads, notice }) {
  const newThreadForm =
    isAdmin && !board.locked
      ? `<section class="card compose">
  <h2>Start a thread in ${escapeHtml(board.name)}</h2>
  <form method="post" action="/b/${escapeHtml(board.slug)}/threads">
    <label>Title
      <input type="text" name="title" maxlength="200" required autocomplete="off">
    </label>
    <label>Opening post <span class="hint">optional</span>
      <textarea name="body" rows="5" maxlength="10000"></textarea>
    </label>
    <input type="text" name="website" class="honeypot" tabindex="-1" autocomplete="off" aria-hidden="true">
    <button type="submit">Post thread</button>
  </form>
</section>`
      : '';

  const list = threads.length
    ? threads
        .map(
          (t) => `<li class="thread-row${t.pinned ? ' pinned' : ''}">
  <a class="thread-link" href="/threads/${t.id}">${escapeHtml(t.title)}</a>
  <div class="meta">
    ${t.pinned ? '<span class="badge">pinned</span>' : ''}
    ${t.locked ? '<span class="badge locked">locked</span>' : ''}
    <span>${t.reply_count} ${t.reply_count === 1 ? 'reply' : 'replies'}</span>
    <span>&middot;</span>
    <span>active ${escapeHtml(timeAgo(t.bumped_at))}</span>
  </div>
</li>`,
        )
        .join('')
    : '<li class="empty">Nothing here yet.</li>';

  return layout({
    title: `${board.name} — ${title}`,
    tagline,
    isAdmin,
    boards,
    activeSlug: board.slug,
    notice,
    body: `<p class="breadcrumb"><a href="/">&larr; all boards</a></p>
${newThreadForm}
<section class="card">
  <h2>${escapeHtml(board.name)}</h2>
  ${board.description ? `<p class="board-desc">${escapeHtml(board.description)}</p>` : ''}
  ${board.locked ? '<p class="locked-note">This board is locked. No new threads or replies.</p>' : ''}
  <ul class="threads">${list}</ul>
</section>`,
  });
}

/**
 * A wall board: one continuous stream of anonymous notes, newest first.
 * Unlike a forum board, anyone can post here without being the owner — that
 * is the whole point of it.
 */
export function renderWall({ title, tagline, isAdmin, board, boards, messages, notice }) {
  const form = board.locked
    ? '<p class="locked-note">This wall is closed. No new notes.</p>'
    : `<form method="post" action="/b/${escapeHtml(board.slug)}/post">
  <label>Leave a note <span class="hint">anonymous, and it stays anonymous</span>
    <textarea name="body" rows="4" maxlength="1000" required placeholder="Say something kind."></textarea>
  </label>
  <input type="text" name="website" class="honeypot" tabindex="-1" autocomplete="off" aria-hidden="true">
  <button type="submit">Post it</button>
</form>`;

  const notes = messages.length
    ? messages
        .map((m) => {
          if (m.deleted) return '';
          const del = isAdmin
            ? `<form class="inline" method="post" action="/messages/${m.id}/delete">
                 <button class="danger linkish" type="submit">delete</button>
               </form>`
            : '';
          return `<li class="note">
  <div class="post-body">${renderBody(m.body)}</div>
  <div class="post-meta">
    <span>${escapeHtml(timeAgo(m.created_at))}</span>
    ${del}
  </div>
</li>`;
        })
        .join('')
    : '<li class="empty">No notes yet.</li>';

  return layout({
    title: `${board.name} — ${title}`,
    tagline,
    isAdmin,
    boards,
    activeSlug: board.slug,
    notice,
    body: `<p class="breadcrumb"><a href="/">&larr; all boards</a></p>
<section class="card compose">
  <h2>${escapeHtml(board.name)}</h2>
  ${board.description ? `<p class="board-desc">${escapeHtml(board.description)}</p>` : ''}
  ${form}
</section>
<section class="card">
  <ul class="notes">${notes}</ul>
</section>`,
  });
}

export function renderThread({ title, tagline, isAdmin, board, boards, thread, messages, notice }) {
  const posts = messages
    .map((m) => {
      if (m.deleted) {
        return `<li class="message deleted"><div class="post-meta">#${m.id}</div><p class="removed">[removed by the owner]</p></li>`;
      }
      const del = isAdmin
        ? `<form class="inline" method="post" action="/messages/${m.id}/delete">
             <button class="danger linkish" type="submit">delete</button>
           </form>`
        : '';
      return `<li class="message${m.is_owner ? ' from-owner' : ''}" id="m${m.id}">
  <div class="post-meta">
    <a href="#m${m.id}" class="post-no">#${m.id}</a>
    <span class="badge ${m.is_owner ? 'owner' : 'anon'}">${m.is_owner ? 'owner' : 'anonymous'}</span>
    <span>${escapeHtml(timeAgo(m.created_at))}</span>
    ${del}
  </div>
  <div class="post-body">${renderBody(m.body)}</div>
</li>`;
    })
    .join('');

  const closed = thread.locked || thread.board_locked;
  const replyForm = closed
    ? `<p class="locked-note">${thread.locked ? 'This thread is locked.' : 'This board is locked.'} No new replies.</p>`
    : `<form class="reply" method="post" action="/threads/${thread.id}/messages">
  <label>Your message <span class="hint">posted anonymously</span>
    <textarea name="body" rows="5" maxlength="10000" required placeholder="Say what you need to say."></textarea>
  </label>
  <input type="text" name="website" class="honeypot" tabindex="-1" autocomplete="off" aria-hidden="true">
  <button type="submit">Post anonymously</button>
</form>`;

  const adminBar = isAdmin
    ? `<div class="admin-bar">
  <form class="inline" method="post" action="/threads/${thread.id}/pin">
    <button type="submit">${thread.pinned ? 'unpin' : 'pin'}</button>
  </form>
  <form class="inline" method="post" action="/threads/${thread.id}/lock">
    <button type="submit">${thread.locked ? 'unlock' : 'lock'}</button>
  </form>
  <form class="inline" method="post" action="/threads/${thread.id}/delete">
    <button class="danger" type="submit">delete thread</button>
  </form>
</div>`
    : '';

  const crumb = board
    ? `<p class="breadcrumb"><a href="/">all boards</a> / <a href="/b/${escapeHtml(board.slug)}">${escapeHtml(board.name)}</a></p>`
    : '<p class="breadcrumb"><a href="/">&larr; all boards</a></p>';

  return layout({
    title: `${thread.title} — ${title}`,
    tagline,
    isAdmin,
    boards,
    activeSlug: board?.slug ?? '',
    notice,
    body: `${crumb}
<section class="card">
  <h2>${escapeHtml(thread.title)}</h2>
  <div class="meta">opened ${escapeHtml(timeAgo(thread.created_at))}</div>
  ${thread.body ? `<div class="post-body op">${renderBody(thread.body)}</div>` : ''}
  ${adminBar}
</section>
<section class="card">
  <ul class="messages">${posts || '<li class="empty">No replies yet. Be the first.</li>'}</ul>
</section>
<section class="card compose">
  ${replyForm}
</section>`,
  });
}

/** Owner-only board management. */
export function renderManage({ title, tagline, boards, notice }) {
  const rows = boards
    .map(
      (b) => `<li class="manage-row">
  <form method="post" action="/manage/${b.id}">
    <div class="manage-grid">
      <label>Name
        <input type="text" name="name" value="${escapeHtml(b.name)}" maxlength="60" required>
      </label>
      <label>Order
        <input type="text" name="position" value="${escapeHtml(b.position)}" maxlength="5" inputmode="numeric">
      </label>
    </div>
    <label>Description
      <input type="text" name="description" value="${escapeHtml(b.description)}" maxlength="200">
    </label>
    <div class="admin-bar">
      <span class="slug">/b/${escapeHtml(b.slug)} &middot; ${escapeHtml(b.kind)}</span>
      <button type="submit">save</button>
    </div>
  </form>
  <div class="admin-bar">
    <form class="inline" method="post" action="/manage/${b.id}/lock">
      <button type="submit">${b.locked ? 'unlock' : 'lock'}</button>
    </form>
    <form class="inline" method="post" action="/manage/${b.id}/delete">
      <button class="danger" type="submit">delete board</button>
    </form>
  </div>
</li>`,
    )
    .join('');

  return layout({
    title: `Manage boards — ${title}`,
    tagline,
    isAdmin: true,
    boards,
    notice,
    body: `<p class="breadcrumb"><a href="/">&larr; all boards</a></p>
<section class="card compose">
  <h2>New board</h2>
  <form method="post" action="/manage">
    <label>Name
      <input type="text" name="name" maxlength="60" required autocomplete="off">
    </label>
    <label>Description <span class="hint">optional</span>
      <input type="text" name="description" maxlength="200" autocomplete="off">
    </label>
    <label>Slug <span class="hint">optional, derived from the name if left blank</span>
      <input type="text" name="slug" maxlength="32" autocomplete="off">
    </label>
    <label>Kind
      <select name="kind">
        <option value="forum">Forum — owner starts threads, anyone replies</option>
        <option value="wall">Wall — anyone posts a note, no threads</option>
      </select>
    </label>
    <button type="submit">Create board</button>
  </form>
</section>
<section class="card">
  <h2>Existing boards</h2>
  <ul class="manage">${rows || '<li class="empty">No boards yet.</li>'}</ul>
  <p class="hint">Deleting a board hides it and its threads. Nothing is erased from disk.</p>
</section>`,
  });
}

export function renderLogin({ title, tagline, notice }) {
  return layout({
    title: `Owner login — ${title}`,
    tagline,
    isAdmin: false,
    notice,
    body: `<section class="card compose">
  <h2>Owner login</h2>
  <p class="hint">Only the board owner needs this. Posting is anonymous and needs no login.</p>
  <form method="post" action="/login">
    <label>Admin token
      <input type="password" name="token" required autocomplete="off">
    </label>
    <button type="submit">Log in</button>
  </form>
</section>`,
  });
}

export function renderError({ title, tagline, isAdmin, code, message }) {
  return layout({
    title: `${code} — ${title}`,
    tagline,
    isAdmin,
    body: `<section class="card">
  <h2>${code}</h2>
  <p>${escapeHtml(message)}</p>
  <p><a href="/">Back to the board</a></p>
</section>`,
  });
}
