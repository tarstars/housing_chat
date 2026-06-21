from common.config import load_config

def test_load_config_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_CHAT_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    cfg = load_config()
    assert cfg.openai_api_key == "k"
    assert cfg.chat_model == "gpt-4o-mini"
    assert cfg.stt_model == "whisper-1"
    assert cfg.result_limit == 5
