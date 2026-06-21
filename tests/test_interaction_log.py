import json
from pathlib import Path
from bot import interaction_log as il

def test_classify_outcome():
    assert il.classify_outcome("boom", {}, []) == "error"
    assert il.classify_outcome(None, {"loop_exhausted": True}, []) == "loop_exhausted"
    assert il.classify_outcome(None, {"empty_search": True}, []) == "empty"
    assert il.classify_outcome(None, {"empty_search": True}, [{"id": "1"}]) == "ok"
    assert il.classify_outcome(None, {}, []) == "ok"

def test_build_record_has_fields():
    tel = {"tool_calls": [{"name": "dataset_info", "args": {}}], "iterations": 1,
           "llm_calls": 1, "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    rec = il.build_record(7, "text", "hi", tel, ["1"], "ok", None, 1234)
    assert rec["chat_id"] == 7 and rec["input"] == "text" and rec["query"] == "hi"
    assert rec["tool_calls"] == tel["tool_calls"]
    assert rec["outcome"] == "ok" and rec["listing_ids"] == ["1"] and rec["error"] is None
    assert rec["latency_ms"] == 1234 and rec["total_tokens"] == 15
    assert "ts" in rec

def test_log_interaction_writes_jsonl(tmp_path):
    d = str(tmp_path / "logs")
    il.log_interaction(d, {"a": 1})
    il.log_interaction(d, {"a": 2})
    lines = Path(d, "interactions.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["a"] for x in lines] == [1, 2]
