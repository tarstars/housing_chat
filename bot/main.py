import logging
import os
import tempfile
import time

from openai import OpenAI
from telegram import InputMediaPhoto, Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler,
    filters as tg_filters,
)

from common.config import load_config
from db import database
from bot import agent, interaction_log
from bot.conversation import Conversation
from bot.openai_client import transcribe
from bot.format import format_listing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("housing_chat.bot")

WELCOME = ("Hi! I'm your Yerevan rentals helper. Ask me about apartments — "
           "prices, districts, comparisons, stats, or find listings. "
           "Text or voice, in any language.")


async def _send_results(update, conn, result) -> None:
    if result.text:
        await update.message.reply_text(result.text)
    for row in result.listings[:5]:
        if not row:
            continue
        rid = row.get("id")
        paths = []
        if rid:
            paths = [p["local_path"] for p in database.get_photos(conn, rid)
                     if p.get("local_path")][:3]
        caption = format_listing(row)
        if paths:
            handles = [open(p, "rb") for p in paths]
            try:
                media = [InputMediaPhoto(fh) for fh in handles]
                await update.message.reply_media_group(media=media, caption=caption)
            finally:
                for fh in handles:
                    fh.close()
        else:
            await update.message.reply_text(caption)


async def _handle(update, context, text: str, input_type: str) -> None:
    data = context.application.bot_data
    cfg = data["cfg"]
    conn = data["conn"]
    conv = data["conv"]
    chat_id = update.effective_chat.id
    log.info("query chat=%s input=%s text=%r", chat_id, input_type, text)
    messages = ([{"role": "system", "content": agent.SYSTEM_PROMPT}]
                + conv.history(chat_id)
                + [{"role": "user", "content": text}])
    t0 = time.time()
    error = None
    result = None
    try:
        result = agent.run(messages, conn, data["client"], cfg.chat_model, cfg.agent_max_iters)
    except Exception as e:
        log.exception("agent failed")
        error = str(e)
    latency_ms = int((time.time() - t0) * 1000)

    if error or result is None:
        await update.message.reply_text("Sorry, something went wrong. Please try again.")
        telemetry, surfaced_ids = {}, []
    else:
        if not result.text and not result.listings:
            result.text = "I couldn't find anything for that. Try rephrasing, or ask what data I have."
        await _send_results(update, conn, result)
        conv.append(chat_id, text, result.text)
        telemetry = result.telemetry
        surfaced_ids = [r.get("id") for r in result.listings if r]

    outcome = interaction_log.classify_outcome(error, telemetry, surfaced_ids)
    record = interaction_log.build_record(chat_id, input_type, text, telemetry,
                                          surfaced_ids, outcome, error, latency_ms)
    interaction_log.log_interaction(cfg.log_dir, record)
    log.info("answered chat=%s outcome=%s latency_ms=%s tokens=%s",
             chat_id, outcome, latency_ms, telemetry.get("total_tokens", 0))


async def handle_text(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _handle(update, context, update.message.text, "text")


async def handle_voice(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.application.bot_data
    cfg = data["cfg"]
    chat_id = update.effective_chat.id
    t0 = time.time()
    tg_file = await update.message.voice.get_file()
    fd, path = tempfile.mkstemp(suffix=".oga")
    os.close(fd)
    try:
        await tg_file.download_to_drive(path)
        text = transcribe(path, data["client"], cfg.stt_model)
    except Exception as e:
        log.exception("transcription failed")
        await update.message.reply_text("Sorry, I couldn't understand that voice message. Please try again.")
        record = interaction_log.build_record(
            chat_id, "voice", "", {}, [], "error", str(e), int((time.time() - t0) * 1000))
        interaction_log.log_interaction(cfg.log_dir, record)
        return
    finally:
        os.unlink(path)
    await _handle(update, context, text, "voice")


async def cmd_start(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.application.bot_data["conv"].clear(update.effective_chat.id)
    await update.message.reply_text(WELCOME)


async def cmd_clear(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.application.bot_data["conv"].clear(update.effective_chat.id)
    await update.message.reply_text("Conversation reset.")


def main() -> None:
    cfg = load_config()
    rw = database.connect(cfg.db_path)
    database.init_db(rw)              # ensure schema exists
    rw.close()
    ro = database.connect_ro(cfg.db_path)
    app = Application.builder().token(cfg.telegram_bot_token).build()
    app.bot_data.update({
        "cfg": cfg, "conn": ro,
        "client": OpenAI(api_key=cfg.openai_api_key),
        "conv": Conversation(cfg.history_max_turns),
    })
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(tg_filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, handle_text))
    log.info("bot starting (long polling)")
    app.run_polling()


if __name__ == "__main__":
    main()
