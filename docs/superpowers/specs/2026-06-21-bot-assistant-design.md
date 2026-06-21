# Housing Chat — Assistant Upgrade Design Spec

**Date:** 2026-06-21
**Repo:** git@github.com:tarstars/housing_chat.git
**Status:** Approved (brainstorming)
**Supersedes the bot's query layer from:** 2026-06-21-housing-chat-design.md

## 1. Goal

Turn the Telegram bot from a fixed search/count responder into a **flexible,
DB-grounded helper** that answers many kinds of questions about the Yerevan
rental listings in SQLite: stats & aggregates, comparisons, recommendations,
and listing details/meta — with multi-turn memory and replies in the user's
language. Add logging so the bot's behavior can be analyzed and improved.

## 2. Scope & key decisions

| Decision | Choice |
|---|---|
| Approach | **Tool-calling agent** (OpenAI function calling over a few audited, read-only tools) |
| Topics | Stats/aggregates, comparisons, recommendations/deals, listing details & meta |
| Memory | Multi-turn, per chat (last ~6 turns, in-memory; `/start` & `/clear` reset) |
| Grounding | DB-grounded; brief general knowledge allowed but **explicitly flagged** as not from the listings |
| Reply language | The user's language (RU/EN/HY) |
| Listings rendering | Search/detail results still sent as cards + thumbnail photos |
| Logging | Operational (stdout, INFO) + structured interaction JSONL for analysis |
| Model | OpenAI `gpt-4o-mini` (configurable), Whisper for voice (unchanged) |

### Out of scope (YAGNI)

Model-generated SQL (text-to-SQL); persistent/cross-restart conversation
storage; full per-chat transcript logging; semantic/vector search; auth/rate
limiting. All deferrable.

## 3. Why these choices

- A **tool-calling agent** is the sweet spot between a rigid intent router
  (can't cover "many topics") and free text-to-SQL (unsafe, hard to test). The
  model is flexible in *what it asks*, but can only *act* through a handful of
  read-only, parameterized tools — safe, grounded, and deterministically
  testable.
- **Multi-turn memory** makes follow-ups ("show cheaper ones", "what about
  Arabkir?") natural. In-memory is enough for a personal bot; persistence is a
  later add.
- **DB-grounded with flagged general help** keeps answers trustworthy: real
  numbers come from tools; any general remark is labeled as such.
- **Logging** is required to analyze user questions/intents, find
  failures/dead-ends, and watch cost/latency — the inputs to improving the bot.

## 4. Architecture

```
Telegram msg ─(voice? Whisper)─> text
      │
      ▼
 load chat history (bot/conversation.py)
      │  messages = [system] + history + [user]
      ▼
 AGENT LOOP (bot/agent.py, ≤4 iterations)
   client.chat.completions.create(model, messages, tools)
     ├─ tool_calls? → tools.dispatch(name,args, ro_conn)  (bot/tools.py)
     │                append tool results; record surfaced listings; loop
     └─ final text? → stop
      │  returns AgentResult{text, listings, telemetry}
      ▼
 reply: send text; send each surfaced listing as card+photo (format_listing)
 append (user, assistant text) to history
 write interaction record (bot/interaction_log.py)
```

The four stages (scrape, process) are unchanged. Only the bot's query layer is
replaced.

## 5. Components

### `bot/tools.py` — the read-only tool layer

Each tool is a pure function `(*, conn, **args) -> dict` plus an OpenAI
function-calling JSON schema. A `TOOLS` list (schemas) and a
`dispatch(name, args, conn) -> dict` entry point. All SQL is parameterized and
read-only; args are validated (caps/whitelists). Filter args reuse the existing
`Filters` fields and `filters._where_clause`.

- `search_listings(filters, sort="price_asc", limit=5) -> {"listings":[...]}`
  - `limit` capped at 10. Rows: id, price, currency, rooms, area_sqm, floor,
    total_floors, district, title, url. Reuses `filters.build_query`.
- `aggregate_stats(filters, metric, group_by=None) -> {"metric":..., "value":..., "groups":[...]}`
  - `metric` ∈ {`count`,`avg_price`,`min_price`,`max_price`,`avg_area`,
    `min_area`,`max_area`} (whitelist). `group_by` ∈ {None,`district`}.
    Reuses `filters._where_clause`. Numbers rounded sensibly.
- `dataset_info() -> {"total":n,"districts":[...],"price_range":{...},
  "currencies":[...],"last_scraped_at":...}`
- `get_listing(listing_id) -> {"listing":{...}|null, "photos":[...]}` — full row
  + photo local_paths.

Validation errors return `{"error":"..."}` (fed back to the model to recover),
never raise into the loop.

### `bot/agent.py` — the tool-calling loop

`run(messages, conn, client, model, max_iters=4) -> AgentResult` where
`AgentResult = {text:str, listings:list[dict], telemetry:dict}`.

- Calls `chat.completions.create(model, messages, tools=tools.TOOLS,
  tool_choice="auto")`.
- On `tool_calls`: execute each via `tools.dispatch`, append an assistant
  tool-call message and `tool` result messages. Track the listings from the
  **most recent** `search_listings`/`get_listing` call — those are the ones the
  model is presenting now (capped at 5 cards). Earlier calls used only for
  reasoning (e.g. a comparison) don't all get rendered.
- On a text response (no tool calls): that's the final answer → stop.
- Accumulates telemetry: `iterations`, `llm_calls`, summed
  `prompt_tokens`/`completion_tokens`/`total_tokens` (from each response's
  `usage`), and `tool_calls` (names+args). If `max_iters` is hit without a final
  text, return the best available text (or a fallback) and mark
  `outcome="loop_exhausted"`.

The system prompt (persona, grounding rule, language rule, tool-usage guidance,
canonical district list) lives here as a constant.

### `bot/conversation.py` — per-chat memory

In-memory `dict[chat_id, list[message]]`. `history(chat_id) -> list`,
`append(chat_id, user_text, assistant_text)`, `clear(chat_id)`. Keeps the last
`MAX_TURNS` (~6) messages (token bound). Only user/assistant **text** is stored
(tool churn is not), keeping context compact.

### `bot/interaction_log.py` — structured analysis log

`log_interaction(record: dict)` appends one JSON line to
`data/logs/interactions.jsonl` (path from config; dir auto-created;
git-ignored). Record fields:

```json
{"ts","chat_id","input":"text|voice","query",
 "tool_calls":[{"name","args"}],"iterations","llm_calls",
 "outcome":"ok|empty|error|loop_exhausted","listing_ids":[...],"error":null,
 "latency_ms","prompt_tokens","completion_tokens","total_tokens"}
```

`outcome="empty"` when the surfaced result set / aggregate is empty (dead-end);
`"error"` when a tool or the LLM call failed.

### `bot/main.py` — Telegram layer (updated)

- Configures Python `logging` (INFO → stdout) at startup.
- `handle_text`/`handle_voice`: resolve `chat_id`; voice → `transcribe`; build
  `messages` from `conversation.history` + system + user; call `agent.run`;
  send `result.text`; send each surfaced listing as a card (`format_listing`) +
  thumbnail media group; `conversation.append(...)`; `interaction_log.log(...)`
  with telemetry + latency.
- `/start` and `/clear` command handlers reset that chat's history.
- On agent/transcribe exception: friendly fallback reply; log `outcome="error"`.

### Reused / retired

- **Reused:** `bot/filters.py` (`Filters`, `_where_clause`, `build_query`),
  `bot/format.py` `format_listing`, `bot/openai_client.py` `transcribe`,
  `db/database.py`.
- **Retired:** `bot/service.py` single-shot `answer`, `openai_client.parse_query`,
  `format_count` / `format_no_results` (the agent's natural-language reply
  replaces them). `Filters.intent` and `build_count_query` are removed (the
  agent + `aggregate_stats` subsume counting).

## 6. Data flow (per message)

1. Message in → (voice → Whisper → text).
2. `messages = [system] + conversation.history(chat_id) + [{"role":"user",...}]`.
3. `agent.run(messages, ro_conn, client, model)` runs the bounded tool loop.
4. Send `result.text`; then for each surfaced listing send card + photo.
5. `conversation.append(chat_id, user_text, result.text)`.
6. `interaction_log.log({...telemetry, latency_ms, outcome...})`.

## 7. Grounding & safety

- **System prompt:** friendly, concise Yerevan-rentals helper; answer using the
  tools and the data they return; never invent listings or numbers; reply in the
  user's language. For questions the data can't answer, give a brief general
  note **explicitly flagged** as general knowledge, not from the listings.
- **Read-only:** the agent opens the DB read-only (`file:<path>?mode=ro` URI);
  tools only `SELECT`. No model-generated SQL.
- **Arg validation:** `limit` capped (≤10); `metric`, `group_by`, `sort`,
  `currency`, `district` whitelisted/typed; invalid → `{"error":...}` back to the
  model. Loop capped at `max_iters`. OpenAI/tool failures → friendly fallback +
  logged.

## 8. Testing

- **Tools (highest value):** in-memory DB seeded with known rows →
  `search_listings` (filters/sort/limit), `aggregate_stats` (count/avg/min/max,
  `group_by=district`), `dataset_info`, `get_listing`, and the `{"error":...}`
  paths. Fully offline.
- **Agent loop:** a scripted fake OpenAI client that emits a tool call, then
  (given the tool result) a final text → assert tools executed, results fed
  back, `AgentResult.text` and surfaced `listings` correct, telemetry summed.
  Deterministic, offline.
- **Conversation:** append/trim to `MAX_TURNS`, `clear`.
- **Interaction log:** record written as valid JSONL with required fields
  (temp dir).
- **Handlers:** mocked Telegram + mocked agent (text reply + cards + log call).

## 9. Config additions

`.env` / `common.config.Config` gains:
- `LOG_DIR` (default `data/logs`)
- `AGENT_MAX_ITERS` (default `4`)
- `HISTORY_MAX_TURNS` (default `6`)
(`OPENAI_CHAT_MODEL`, `OPENAI_STT_MODEL`, paths, `RESULT_LIMIT` unchanged.)

## 10. Project layout (delta)

```
bot/
  agent.py            # NEW — tool-calling loop
  tools.py            # NEW — read-only tools + schemas
  conversation.py     # NEW — per-chat memory
  interaction_log.py  # NEW — JSONL analysis log
  main.py             # UPDATED — agent wiring, logging, /clear
  filters.py          # reused (drop intent/build_count_query)
  format.py           # reused (format_listing); drop count/no_results
  openai_client.py    # reused (transcribe); drop parse_query
  service.py          # REMOVED
data/logs/            # NEW (git-ignored)
```
