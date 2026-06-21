import json
from dataclasses import dataclass

from bot import tools
from processor.normalize import YEREVAN_DISTRICTS

SYSTEM_PROMPT = (
    "You are a friendly, concise assistant for apartment rentals in Yerevan. "
    "You help users explore a database of rental listings: searching, statistics "
    "(counts, average/min/max price or area), comparisons across districts, "
    "recommendations, and dataset/listing details. "
    "ALWAYS answer using the provided tools and the data they return — never "
    "invent listings, prices, or counts. Always reply in the SAME language as "
    "the user's most recent message (English in, English out). "
    "Prices are in AMD (֏) or USD ($). Each listing has a rental period — "
    "'monthly' (long-term) or 'daily' (short-term); these prices are NOT "
    "comparable, so when computing price statistics filter by period (default "
    "to monthly unless the user asks about daily/short-term rentals). "
    "The known districts are: "
    + ", ".join(YEREVAN_DISTRICTS) + ". "
    "If a question cannot be answered from the listings data, you may give a "
    "brief general note, but explicitly say it is general knowledge, not from "
    "the listings. When you show specific listings, keep your text short — the "
    "listings are also shown to the user as photo cards."
)


@dataclass
class AgentResult:
    text: str
    listings: list
    telemetry: dict


def _accumulate_usage(tel: dict, resp) -> None:
    u = getattr(resp, "usage", None)
    if u is not None:
        tel["prompt_tokens"] += getattr(u, "prompt_tokens", 0) or 0
        tel["completion_tokens"] += getattr(u, "completion_tokens", 0) or 0
        tel["total_tokens"] += getattr(u, "total_tokens", 0) or 0


def run(messages: list, conn, client, model: str, max_iters: int = 4) -> AgentResult:
    messages = list(messages)
    tel = {"iterations": 0, "llm_calls": 0, "prompt_tokens": 0,
           "completion_tokens": 0, "total_tokens": 0, "tool_calls": [],
           "empty_search": False, "loop_exhausted": False}
    surfaced: list = []
    for i in range(max_iters):
        resp = client.chat.completions.create(
            model=model, messages=messages, tools=tools.TOOLS, tool_choice="auto")
        tel["iterations"] = i + 1
        tel["llm_calls"] += 1
        _accumulate_usage(tel, resp)
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            return AgentResult(msg.content or "", surfaced, tel)
        messages.append(msg)
        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            tel["tool_calls"].append({"name": name, "args": args})
            result = tools.dispatch(name, args, conn)
            if name == "search_listings":
                listings = result.get("listings", [])
                surfaced = listings[:5]
                if not listings:
                    # run-scoped flag: True if ANY search this turn returned nothing
                    tel["empty_search"] = True
            elif name == "get_listing":
                listing = result.get("listing")
                surfaced = [listing] if listing else []
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(result, ensure_ascii=False)})
    tel["loop_exhausted"] = True
    return AgentResult("", surfaced, tel)
