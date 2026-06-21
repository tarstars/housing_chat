import json
import os
from datetime import datetime, timezone
from pathlib import Path


def classify_outcome(error, telemetry: dict, surfaced: list) -> str:
    if error:
        return "error"
    if telemetry.get("loop_exhausted"):
        return "loop_exhausted"
    if telemetry.get("empty_search") and not surfaced:
        return "empty"
    return "ok"


def build_record(chat_id, input_type, query, telemetry, surfaced_ids,
                 outcome, error, latency_ms) -> dict:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "chat_id": chat_id,
        "input": input_type,
        "query": query,
        "tool_calls": telemetry.get("tool_calls", []),
        "iterations": telemetry.get("iterations", 0),
        "llm_calls": telemetry.get("llm_calls", 0),
        "outcome": outcome,
        "listing_ids": surfaced_ids,
        "error": error,
        "latency_ms": latency_ms,
        "prompt_tokens": telemetry.get("prompt_tokens", 0),
        "completion_tokens": telemetry.get("completion_tokens", 0),
        "total_tokens": telemetry.get("total_tokens", 0),
    }


def log_interaction(log_dir: str, record: dict) -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    with open(os.path.join(log_dir, "interactions.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
