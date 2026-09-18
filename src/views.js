import { escapeHtml, renderBody, timeAgo } from './util.js';

function layout({ title, tagline, isAdmin, body, notice = '' }) {
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
  <nav>
    ${
      isAdmin
        ? '<span class="badge owner">owner mode</span> <form class="inline" method="post" action="/logout"><button class="linkish" type="submit">log out</button></form>'
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

export function renderIndex({ title, tagline, isAdmin, threads, notice }) {
  const newThreadForm = isAdmin
    ? `<section class="card compose">
  <h2>Start a thread</h2>
  <form method="post" action="/threads">
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
    title,
    tagline,
    isAdmin,
    notice,
    body: `${newThreadForm}
<section class="card">
  <h2>Threads</h2>
  <ul class="threads">${list}</ul>
</section>`,
  });
}

export function renderThread({ title, tagline, isAdmin, thread, messages, notice }) {
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

  const replyForm = thread.locked
    ? '<p class="locked-note">This thread is locked. No new replies.</p>'
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

  return layout({
    title: `${thread.title} — ${title}`,
    tagline,
    isAdmin,
    notice,
    body: `<p class="breadcrumb"><a href="/">&larr; all threads</a></p>
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
