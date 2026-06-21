import os
import tempfile

from openai import OpenAI
from telegram import InputMediaPhoto, Update
from telegram.ext import (
    Application, ContextTypes, MessageHandler, filters as tg_filters,
)

from common.config import load_config
from db import database
from bot.service import answer
from bot.openai_client import transcribe
from bot.format import format_no_results


async def _send_results(update: Update, results: list[dict]) -> None:
    if not results:
        await update.message.reply_text(format_no_results())
        return
    for r in results:
        if r["photos"]:
            handles = [open(p, "rb") for p in r["photos"]]
            try:
                media = [InputMediaPhoto(fh) for fh in handles]
                await update.message.reply_media_group(media=media, caption=r["text"])
            finally:
                for fh in handles:
                    fh.close()
        else:
            await update.message.reply_text(r["text"])


async def handle_text(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.application.bot_data
    results = answer(update.message.text, data["conn"], data["client"],
                     data["cfg"].chat_model, data["cfg"].result_limit)
    await _send_results(update, results)


async def handle_voice(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.application.bot_data
    tg_file = await update.message.voice.get_file()
    fd, path = tempfile.mkstemp(suffix=".oga")
    os.close(fd)
    try:
        await tg_file.download_to_drive(path)
        text = transcribe(path, data["client"], data["cfg"].stt_model)
    finally:
        os.unlink(path)
    results = answer(text, data["conn"], data["client"],
                     data["cfg"].chat_model, data["cfg"].result_limit)
    await _send_results(update, results)


def main() -> None:
    cfg = load_config()
    conn = database.connect(cfg.db_path)
    app = Application.builder().token(cfg.telegram_bot_token).build()
    app.bot_data.update({
        "cfg": cfg, "conn": conn, "client": OpenAI(api_key=cfg.openai_api_key),
    })
    app.add_handler(MessageHandler(tg_filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, handle_text))
    app.run_polling()


if __name__ == "__main__":
    main()
