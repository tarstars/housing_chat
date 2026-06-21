class Conversation:
    """In-memory per-chat message history, trimmed to the last max_turns."""

    def __init__(self, max_turns: int = 6):
        self._max = max_turns
        self._store: dict[int, list[dict]] = {}

    def history(self, chat_id: int) -> list[dict]:
        return list(self._store.get(chat_id, []))

    def append(self, chat_id: int, user_text: str, assistant_text: str) -> None:
        msgs = self._store.setdefault(chat_id, [])
        msgs.append({"role": "user", "content": user_text})
        msgs.append({"role": "assistant", "content": assistant_text})
        if len(msgs) > self._max:
            del msgs[: len(msgs) - self._max]

    def clear(self, chat_id: int) -> None:
        self._store.pop(chat_id, None)
