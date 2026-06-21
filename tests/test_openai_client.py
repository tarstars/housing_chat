from types import SimpleNamespace
from bot import openai_client

class FakeClient:
    def __init__(self):
        self.audio = SimpleNamespace(transcriptions=self)
        self.tr_args = {}
    def create(self, *, model, file):
        self.tr_args = {"model": model, "has_file": file is not None}
        return SimpleNamespace(text="hello world")

def test_transcribe(tmp_path):
    p = tmp_path / "a.oga"; p.write_bytes(b"x")
    client = FakeClient()
    text = openai_client.transcribe(str(p), client, "whisper-1")
    assert text == "hello world"
    assert client.tr_args == {"model": "whisper-1", "has_file": True}
