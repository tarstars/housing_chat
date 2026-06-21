from common.config import load_config

def test_load_config_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_CHAT_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    cfg = load_config()
    assert cfg.openai_api_key == "k"
    assert cfg.chat_model == "gpt-4o-mini"
    assert cfg.stt_model == "whisper-1"
    assert cfg.result_limit == 5
    assert cfg.log_dir == "data/logs"
    assert cfg.agent_max_iters == 4
    assert cfg.history_max_turns == 6
