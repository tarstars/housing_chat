# Housing Chat

Telegram bot answering text/voice queries (RU/EN/HY) about Yerevan apartment
rentals, served from a local list.am snapshot in SQLite.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip setuptools
pip install -e ".[dev]"
python3 -m playwright install chromium
cp .env.example .env   # then fill in OPENAI_API_KEY and TELEGRAM_BOT_TOKEN
```

## Pipeline (run locally, in order)

```bash
# 1. Scrape a snapshot
MAX_LISTINGS=1000 python3 -m scraper.crawl

# 2. Normalize raw JSON into data/housing.db
python3 -m processor.process

# 3. Run the bot (long polling — no public IP needed)
python3 -m bot.main
```

The bot is a conversational assistant: ask for listings, stats ("average price
in Kentron"), comparisons, recommendations, or dataset info — text or voice, in
any language. It remembers recent context per chat; `/clear` resets it.
Interaction logs are written to `data/logs/interactions.jsonl` for analysis.

### Scraping volume & Cloudflare (important)

list.am is behind Cloudflare. A **headless** browser passes the challenge on
the **first** category page but is blocked on sequential pagination (and on
individual listing detail pages) — so headless yields only ~20 listings.

To scrape a large snapshot, run on a machine **with a real display** and a
**visible** browser, which passes the challenge on every page:

```bash
HEADLESS=0 MAX_LISTINGS=1000 python3 -m scraper.crawl
python3 -m processor.process
```

A Chromium window opens and solves the challenge per page. Useful env knobs:

| Env | Default | Meaning |
|-----|---------|---------|
| `MAX_LISTINGS` | `200` | how many new listings to scrape |
| `HEADLESS` | `1` | set `0` for a visible browser (needed for >1 page) |
| `SCRAPE_DELAY` | `2.0` | seconds between category pages |

The scraper resumes — re-running skips already-saved listing IDs, so you can
stop and continue. After scraping on your desktop, either run the bot there, or
copy `data/housing.db` (and `data/raw/photos/`) to wherever the bot runs.

## Tests

```bash
python3 -m pytest tests/test_integration.py -v
python3 -m pytest -q
```

Tests can run without an editable install because pytest is configured with `pythonpath=["."]`.

## Notes

- list.am is behind Cloudflare; the scraper uses a real Chromium via Playwright.
- All AI is OpenAI: a tool-calling agent (chat model) for query understanding and reasoning, Whisper for STT.
- Scraper is card-level: it scrapes category pages (detail pages are Cloudflare-blocked).
- Thumbnails are converted webp→JPEG (Pillow).
- Re-running the scraper resumes (skips already-saved listing IDs).
