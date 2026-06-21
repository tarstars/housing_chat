from bot.conversation import Conversation

def test_append_and_history():
    c = Conversation(max_turns=6)
    c.append(1, "hi", "hello")
    assert c.history(1) == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    assert c.history(2) == []          # unknown chat

def test_history_trims_to_max_turns():
    c = Conversation(max_turns=4)      # keep last 4 messages = 2 turns
    for i in range(5):
        c.append(1, f"u{i}", f"a{i}")
    h = c.history(1)
    assert len(h) == 4
    assert h[0] == {"role": "user", "content": "u3"}
    assert h[-1] == {"role": "assistant", "content": "a4"}

def test_history_returns_copy():
    c = Conversation()
    c.append(1, "u", "a")
    c.history(1).append({"role": "user", "content": "x"})
    assert len(c.history(1)) == 2      # internal store unaffected

def test_clear():
    c = Conversation()
    c.append(1, "u", "a")
    c.clear(1)
    assert c.history(1) == []
