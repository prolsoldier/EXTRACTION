# EXTRACTION — Deal Hunter

A userscript that turns KSL Classifieds and Facebook Marketplace into a ranked deal feed while you browse. It scores every listing on the page against used-market prices, flags the steals, and pools the best finds from every open tab into one list.

It runs in **your own browser session** and only reads what the page has already shown you. It doesn't use bots, logins, captcha bypasses or server-side scraping, so it won't get your account flagged.

## Install (2 minutes)
1. Install [Tampermonkey](https://www.tampermonkey.net/) (Chrome, Firefox, Edge; on Android use Firefox or Kiwi).
2. Tampermonkey → *Create new script* → paste `deal-hunter.user.js` → save.
3. On Facebook Marketplace, set your location to **West Jordan, ~20 mi** once (Marketplace remembers it).

## Use
- Open any KSL or Marketplace search. Cards get a badge:
  - **STEAL / FREE** (green outline): buy it now
  - **GOOD** (yellow): fair, so negotiate
  - **PASS** (dimmed): overpriced
  - **PARTS** (red): broken or for parts
- **Hunt all** (panel, bottom-right) opens every saved search on both sites in background tabs, 1.5 s apart. Scroll each tab a bit; every tab feeds the same ranked list.
- You get a desktop notification the first time a new STEAL/FREE item appears.
- **CSV** exports the list; **Clear** resets it.

## Tuning
Edit the top of the script:
- `SEARCHES`: what *Hunt all* opens (currently speakers to finish a 7.1 setup, plus cameras, surveillance drives, doorbells and locks).
- `RULES`: category regex plus `steal`/`fair` prices. Brands in `PREMIUM` get a 1.6× allowance.
- Listings from the southwest valley (West Jordan, South Jordan, Riverton, Kearns, …) get a small ranking boost.

## Hands-off alerts (built into the sites)
- **KSL:** run a search → *Save search* → turn on email/push alerts.
- **Facebook:** search → *Notify me* (bell) on the results page.

Combine them: the alert tells you something new dropped, and the userscript tells you whether it's actually a deal.
