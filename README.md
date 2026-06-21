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
# 1. Scrape a snapshot (run on your own machine — residential IP passes Cloudflare)
MAX_LISTINGS=200 python3 -m scraper.crawl

# 2. Normalize raw JSON into data/housing.db
python3 -m processor.process

# 3. Run the bot (long polling — no public IP needed)
python3 -m bot.main
```

Then message the bot in Telegram, e.g. "2-room flat in Kentron under 800$",
or send a voice message.

## Tests

```bash
python3 -m pytest tests/test_integration.py -v
python3 -m pytest -q
```

Tests can run without an editable install because pytest is configured with `pythonpath=["."]`.

## Notes

- list.am is behind Cloudflare; the scraper uses a real Chromium via Playwright.
- All AI is OpenAI: a chat model for query understanding, Whisper for STT.
- Scraper is card-level: it scrapes category pages (detail pages are Cloudflare-blocked).
- Thumbnails are converted webp→JPEG (Pillow).
- Re-running the scraper resumes (skips already-saved listing IDs).
