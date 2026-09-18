# EXTRACTION — anonboard

A self-hosted anonymous message board. You post threads; anyone can reply
anonymously. No accounts, no analytics, no IP addresses on disk.

**Zero dependencies.** Nothing from npm — it runs on the Node standard library
and the built-in `node:sqlite`. There is no install step, no lockfile, no
supply chain to trust.

## Run it

```bash
cp .env.example .env

# generate the two secrets
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"   # -> ADMIN_TOKEN
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"   # -> SECRET_KEY

npm start          # http://127.0.0.1:3000
npm test           # 17 tests, no network needed
npm run dev        # auto-restart on change
```

Requires Node 22.5 or newer (for `node:sqlite`).

## How it works

Two kinds of visitor:

| | Anonymous visitor | Owner |
|---|---|---|
| Read the board | yes | yes |
| Reply to a thread | yes, no login | yes |
| Start a thread | no | yes |
| Pin / lock / delete | no | yes |

The owner logs in at `/login` with `ADMIN_TOKEN`. That is the only login in the
system. Everyone else just types and posts.

## Anonymity

This is the part worth reading carefully, because "anonymous" is a claim most
software makes and few honour.

- **No IP address is ever written to disk.** The client IP is read into memory,
  HMAC'd, and discarded inside a single function (`posterToken` in
  `src/util.js`). Nothing downstream ever sees it.
- **The hash rotates daily.** The HMAC salt is `SECRET_KEY + today's UTC date`,
  so a poster's token on Tuesday cannot be matched to the same poster on
  Wednesday — not even by whoever holds the database *and* the secret key.
- **The hash exists only to rate-limit**, and those rows are pruned every ten
  minutes so the limiter table never accumulates into a usage history.
- **No cookies for readers or posters.** The only cookie in the system is the
  owner's session, and it is `HttpOnly; SameSite=Strict`.
- **No third-party requests.** No fonts, no CDN, no scripts. The CSP is
  `default-src 'none'`, so the browser is instructed to refuse them even if one
  were ever introduced by accident.
- **`Referrer-Policy: no-referrer`**, so clicking out of the board does not tell
  the destination where the visitor came from.

You can check the first claim yourself, on a live database:

```bash
strings data/board.db | grep -E '127\.0\.0\.1|::1'   # returns nothing
```

The privacy guarantee is only as good as the machine it runs on. Run it
somewhere you control. If you put it behind a reverse proxy, that proxy's
access log is the weak link — turn it off.

## Other hardening

- Every piece of user text is HTML-escaped before it reaches a page; the test
  suite asserts that injected `<script>` and `<img onerror>` come back inert.
- Session cookies are HMAC-signed with an expiry, so a forged cookie is
  rejected (tested).
- The admin token is compared in constant time.
- Request bodies are capped at 64 KB; messages at 10,000 characters.
- Login attempts are limited to 10 per hour per rotating token.
- A hidden honeypot field silently swallows the submission when a bot fills it
  in — the bot gets a normal-looking redirect and the post is dropped.
- `X-Forwarded-For` is ignored unless `TRUST_PROXY=1`, so nobody can forge a
  header to escape the rate limiter.

## Configuration

All via `.env` (see `.env.example`):

| Variable | Required | Meaning |
|---|---|---|
| `ADMIN_TOKEN` | yes | Owner login. 16+ characters. |
| `SECRET_KEY` | yes | Signs cookies, salts poster hashes. |
| `PORT` / `HOST` | no | Default `3000` / `127.0.0.1`. |
| `BOARD_TITLE` / `BOARD_TAGLINE` | no | Header text. |
| `DB_PATH` | no | Default `./data/board.db`. |
| `TRUST_PROXY` | no | `1` only behind a proxy you control. |

Changing `SECRET_KEY` logs out the owner and resets rate limits. Nothing else
is affected.

## Layout

```
src/server.js   HTTP routing, auth, moderation, CLI entry point
src/db.js       SQLite schema and queries
src/views.js    HTML rendering
src/util.js     escaping, hashing, cookie signing, rate-limit tokens
public/style.css
test/board.test.js
```

## Formatting

Blank lines make paragraphs. A line starting with `>` renders as a quote. That
is the whole markup language — deliberately, since every additional feature is
another way to smuggle markup into someone else's browser.
