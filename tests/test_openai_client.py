from types import SimpleNamespace
from bot.filters import Filters
from bot import openai_client

class FakeParse:
    def __init__(self, filters): self._f = filters; self.calls = {}
    def parse(self, *, model, messages, response_format):
        self.calls = {"model": model, "messages": messages, "rf": response_format}
        msg = SimpleNamespace(parsed=self._f)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

class FakeClient:
    def __init__(self, filters):
        self._parser = FakeParse(filters)
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=self._parser))
        self.audio = SimpleNamespace(transcriptions=self)
        self.tr_args = {}
    def create(self, *, model, file):
        self.tr_args = {"model": model, "has_file": file is not None}
        return SimpleNamespace(text="hello world")

def test_parse_query_returns_filters_and_passes_model():
    f = Filters(max_price=800, currency="USD")
    client = FakeClient(f)
    out = openai_client.parse_query("rent under 800$", client, "gpt-4o-mini")
    assert out == f
    assert client._parser.calls["model"] == "gpt-4o-mini"
    assert client._parser.calls["rf"] is Filters
    assert client._parser.calls["messages"][-1]["content"] == "rent under 800$"

def test_transcribe(tmp_path):
    p = tmp_path / "a.oga"; p.write_bytes(b"x")
    client = FakeClient(Filters())
    text = openai_client.transcribe(str(p), client, "whisper-1")
    assert text == "hello world"
    assert client.tr_args == {"model": "whisper-1", "has_file": True}
