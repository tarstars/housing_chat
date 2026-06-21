# Housing Chat — Design Spec

**Date:** 2026-06-21
**Repo:** git@github.com:tarstars/housing_chat.git
**Status:** Approved (brainstorming)

## 1. Goal

A Telegram chatbot that answers natural-language queries (text or voice, in
Russian / English / Armenian) about **apartment rentals in Yerevan**, using a
locally-scraped snapshot of list.am. Replies are text summaries plus listing
photos. Priority: efficient and quick to implement.

## 2. Scope & key decisions

| Decision | Choice |
|---|---|
| Listing type | Rentals (apartments for rent) |
| Search style | Structured filtering (price, rooms, area, district, floor) |
| Geographic scope | Yerevan only |
| Query languages | Russian, English, Armenian (auto-detect) |
| Data freshness | One-time snapshot (re-runnable manually; no scheduler) |
| AI services | All OpenAI — GPT for query understanding + replies, Whisper for STT |
| Data store | SQLite (single file) |
| Bot framework | python-telegram-bot v21 (async, long polling) |
| Scraper | Playwright (headless Chromium) |
| Hosting | All local for now; bot host-agnostic via `.env` for easy VPS move later |
| Language/runtime | Python 3.10+ (deploy machine runs 3.10.12) |

### Out of scope (YAGNI)

Semantic / vector search, scheduled refresh, web UI, map rendering, sale
listings, regions outside Yerevan. All deferrable.

## 3. Why these choices

- **list.am is behind Cloudflare's JS challenge** (verified: plain
  `requests`/`curl` returns 403 with a "Just a moment..." page). A plain
  HTTP + BeautifulSoup scraper will not work. Playwright drives a real browser
  that solves the challenge and renders JS content. Running it **locally** also
  matters: Cloudflare is far more hostile to datacenter IPs than residential
  ones, so a local run is more likely to pass than a VPS run.
- **One-time snapshot** makes SQLite ideal: a single queryable file, no server.
- **Structured filtering** means we do not need embeddings/RAG. GPT structured
  output maps a multilingual NL query to a typed filter object; a small
  hand-written SQL builder turns that into a parameterized query (no
  LLM-generated SQL — safer).
- **Long polling** means the bot needs no public IP, open ports, or webhook/TLS,
  so it runs anywhere including behind NAT.

## 4. Architecture

Three independent, separately-runnable stages joined by one SQLite file:

```
┌─────────────┐     ┌─────────────┐     ┌──────────────────┐
│  1. SCRAPE  │ ──> │ 2. PROCESS  │ ──> │  housing.db      │
│ Playwright  │     │ normalize/  │     │  (SQLite)        │
│ → raw HTML/ │     │ extract →   │     │  listings +      │
│   JSON      │     │ structured  │     │  photos          │
└─────────────┘     └─────────────┘     └────────┬─────────┘
                                                  │
                          ┌───────────────────────┘
                          ▼
                 ┌──────────────────┐   text ──────────────┐
                 │  3. TELEGRAM BOT │   voice ─> Whisper ──>│ NL query
                 │ python-telegram- │   GPT structured ────> filters
                 │      bot         │   SQL on housing.db ─> matches
                 │  (long polling)  │   reply: text + photo media group
                 └──────────────────┘
```

## 5. Components

### `scraper/` — Playwright crawler (local, one-time)

- Open a browser context, pass the Cloudflare challenge once, reuse the context.
- Walk the Yerevan rental category pages (pagination), collect listing URLs.
- Visit each detail page; save **raw** output to `data/raw/<id>.json`
  (extracted fields + photo URLs) and optionally raw HTML for re-parsing.
- **Download up to ~5 photos per listing** to `data/raw/photos/<id>/` while the
  browser context already holds a valid Cloudflare cookie. The bot later sends
  these local files — it never hotlinks list.am image URLs (those sit behind the
  same Cloudflare/CDN and are unreliable for Telegram to fetch).
- Politeness & robustness: 1–2 concurrency, throttled delay between requests,
  resumable (skip already-fetched IDs), checkpointed so a crash resumes rather
  than restarts, and a configurable cap on total listings.
- Output is **raw** — no normalization here. Keeps scraping and parsing
  independently testable.

### `processor/` — normalize raw → structured rows (local, one-time)

- Parse from raw: price + currency, rooms, area (m²), floor / total floors,
  district, address, title, description, posted date, photo URLs.
- Normalize currency labels (AMD / USD) and numeric fields.
- Write to SQLite. Idempotent / re-runnable (upsert by id). Drop or flag records
  missing essential fields (price or rooms or area).

### `bot/` — Telegram front-end (local, long polling)

- **text handler:** transcript = message text.
- **voice handler:** download `.ogg` → Whisper (`whisper-1`) → transcript.
- **Query understanding:** GPT structured output → typed `Filters` object.
- **SQL builder:** hand-written, converts `Filters` → parameterized
  `SELECT ... WHERE ... ORDER BY ... LIMIT N`.
- **Reply:** for up to N (default 5) matches, a formatted text summary
  (price / rooms / area / district + source URL) and a Telegram media group of
  up to ~3 photos per listing. On zero matches, a friendly "no results, try
  relaxing X" message in the user's language.

### `db/` — schema + thin data-access layer

Shared by processor (writes) and bot (reads).

## 6. Data model (SQLite)

```sql
listings(
  id            TEXT PRIMARY KEY,   -- list.am listing id
  url           TEXT,
  title         TEXT,
  price         INTEGER,            -- normalized amount
  currency      TEXT,               -- 'AMD' | 'USD'
  rooms         INTEGER,
  area_sqm      REAL,
  floor         INTEGER,
  total_floors  INTEGER,
  district      TEXT,
  address       TEXT,
  description   TEXT,
  posted_at     TEXT,
  scraped_at    TEXT
);
photos(
  listing_id    TEXT,               -- FK -> listings.id
  url           TEXT,               -- original list.am url (provenance)
  local_path    TEXT,               -- path under data/raw/photos/<id>/
  position      INTEGER
);
```

Indexes on the filterable columns: `price`, `rooms`, `area_sqm`, `district`.

## 7. Query data flow

1. User sends text or voice.
2. Voice → Whisper → transcript.
3. Transcript → GPT structured output → `Filters`:
   `{ min_price?, max_price?, currency?, min_rooms?, max_rooms?, min_area?,
      max_area?, district?, sort? }` — every field optional; the model also
   chooses a sort (e.g. cheapest-first).
4. SQL builder → parameterized query, `LIMIT 5`.
5. Reply: per-listing text summary + up to ~3 **locally-stored** photos as a
   media group, plus the listing URL. Zero matches → guidance message in the
   user's language.

## 8. Error handling

- **Scraper:** retry with backoff on challenge/timeout; checkpoint + resume; log
  and skip unparseable listings; cap total to avoid runaway.
- **Bot:** Whisper/GPT failure → friendly fallback message; query with no usable
  filters → ask a clarifying question; SQL always parameterized.
- **Secrets:** `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN` from `.env` (git-ignored);
  `.env.example` committed.

## 9. Testing

- **Processor (highest value):** unit tests over saved raw fixtures → assert
  correct parsed/normalized fields. Fully offline.
- **Query understanding:** example multilingual queries → expected `Filters`
  (OpenAI mocked); `Filters` → expected SQL.
- **Bot handlers:** mocked Telegram + mocked OpenAI/Whisper.
- **Scraper:** thin smoke test that one real page can be fetched; core logic
  kept separate from network so it is testable offline.

## 10. Project layout

```
housing_chat/
  scraper/        # Playwright crawler
  processor/      # raw -> structured
  bot/            # telegram + STT + query understanding
  db/             # schema + data access
  data/
    raw/          # scraped raw json/html (git-ignored)
    housing.db    # SQLite snapshot (git-ignored)
  tests/
  docs/superpowers/specs/
  .env.example
  pyproject.toml
  README.md
```

## 11. Hosting

- Scraper + processor: run locally, one-time. Produce `housing.db`.
- Bot: run locally on the user's Linux box via long polling (no public IP /
  ports). Zero cost. Config entirely via `.env` so it can later be moved to a
  cheap VPS (systemd) with no code changes.
