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
    )
