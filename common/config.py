import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    openai_api_key: str
    telegram_bot_token: str
    chat_model: str
    stt_model: str
    db_path: str
    raw_dir: str
    photos_dir: str
    result_limit: int
    log_dir: str
    agent_max_iters: int
    history_max_turns: int


def load_config() -> Config:
    return Config(
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        chat_model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        stt_model=os.environ.get("OPENAI_STT_MODEL", "whisper-1"),
        db_path=os.environ.get("HOUSING_DB_PATH", "data/housing.db"),
        raw_dir=os.environ.get("RAW_DIR", "data/raw"),
        photos_dir=os.environ.get("PHOTOS_DIR", "data/raw/photos"),
        result_limit=int(os.environ.get("RESULT_LIMIT", "5")),
        log_dir=os.environ.get("LOG_DIR", "data/logs"),
        agent_max_iters=int(os.environ.get("AGENT_MAX_ITERS", "4")),
        history_max_turns=int(os.environ.get("HISTORY_MAX_TURNS", "6")),
    )
