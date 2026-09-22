# EXTRACTION — Deal Hunter

A userscript that turns KSL Classifieds and Facebook Marketplace into a ranked deal feed while you browse. It scores every listing against used-market prices, tracks price drops, merges items cross-posted to both sites, and pools the best finds from every open tab into one list.

It runs in **your own browser session** and only reads what the page has already shown you. It doesn't use bots, logins, captcha bypasses or server-side scraping, so it won't get your account flagged.

## Install
1. Install [Tampermonkey](https://www.tampermonkey.net/) (Chrome, Firefox, Edge; on Android use Firefox or Kiwi).
2. Open the [raw script](https://raw.githubusercontent.com/prolsoldier/EXTRACTION/main/deal-hunter.user.js) and Tampermonkey offers to install it. Updates arrive automatically if the repo is public; otherwise paste `deal-hunter.user.js` into a new script.
3. On Facebook Marketplace, set your location to **West Jordan, ~20 mi** once.

## What you get
**On every listing card** there's a badge:
- **STEAL / FREE** (green outline): buy it now
- **GOOD** (yellow): fair, so negotiate
- **PASS** (dimmed): overpriced
- **PARTS** (red): broken or for parts
- **⚠ scam?** (purple): "Zelle only", "deposit", "shipping only", a phone number in the title, or a price too good to be real

The badge also shows the fair price, quantity and miles from home.

**Pricing brains**
- About 20 known models (Polk CS10, Klipsch RP-600M, BIC PL-200, Reolink RLC-5xx, WD Purple and others) have their own fair used prices.
- Category prices cover everything else, with a higher allowance for good brands.
- Multi-packs ("4 pack", "x2", "set of 3") are priced per unit.
- A single speaker from a pair category gets half the pair price.
- Car subs and "wanted/ISO" posts are left out.

**Ranking** combines how far under fair the price is, the brand, distance from West Jordan (straight-line, from about 45 Wasatch Front cities), and freshness (under 24 hours old ranks higher).

**Panel** (bottom-right, **Alt+D** toggles it):
- Filters: Steals / Good+ / All / ★ Watching, plus category and text search.
- Sorts: best value, cheapest, closest, newest.
- The same item posted on both KSL and FB shows as one row: `[FB+KSL]`.
- Price drops show as ~~$40~~ $30 ▼ and send a notification.
- **Offer $X** copies a ready-to-send message ("Is this still available? …would you take $X cash?") and opens the listing. The offer is 75% of asking, but never below the steal price.
- ☆ watches an item (watched items never expire); ✕ hides it.
- **Hunt all** opens every saved search on both sites in background tabs, one every 4 s.
- **Auto-scroll** loads more results on the current page, paced like a person scrolling.
- **CSV**, **Backup** and **Restore** (JSON).

**Notifications** fire for new STEAL/FREE items (not scam-flagged ones) and for price drops.

Finds not seen for 21 days are pruned automatically, except watched ones.

## Settings
Click **⚙** (or use Tampermonkey menu → Settings) to edit the JSON. Changes re-score everything you've saved.

| key | default | |
|---|---|---|
| `home` | West Jordan | city used for distance |
| `kslZip` / `kslMiles` | 84084 / 25 | KSL search area |
| `fbDays` | 7 | FB "listed in last N days" |
| `maxMiles` | 30 | listings farther than this sink |
| `offerPct` | 0.75 | opening offer as a fraction of asking |
| `pruneDays` | 21 | auto-forget after N days unseen |
| `notify` | true | desktop notifications |
| `huntDelayMs` | 4000 | gap between Hunt-all tabs |
| `searches` | 17 searches | what Hunt all opens |

Category and model prices live in `RULES` and `MODELS` at the top of the script.

## Hands-off alerts (built into the sites)
- **KSL:** run a search → *Save search* → turn on alerts.
- **Facebook:** search → *Notify me* (bell).

Combine them: the alert tells you something new dropped, and the userscript tells you whether it's actually a deal.

## Development
```sh
npm test            # syntax check + unit tests (node:test, no deps)
npm run test:e2e    # drives the real script in headless Chromium against tests/fixtures
```
CI runs both on every push.
