"""Telegram bot: capture layer for Idea Vault.

Long-polling (no inbound webhook), so no public HTTPS endpoint is needed --
runs entirely outbound. Every text/URL/photo message becomes a row in the
shared SQLite DB, then gets run through headless Claude Code (claude_client)
for a summary + category before replying back to the user.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from claude_client import ClaudeProcessingError, ensure_workspace_trusted, process_entry
from db import IMAGES_DIR, distinct_categories, get_connection
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("idea-vault-bot")

WELCOME = (
    "Send me any idea, link, or screenshot and I'll file it away -- I'll research it, "
    "summarize it, and categorize it automatically. Check the dashboard to browse everything "
    "you've captured."
)


def _insert_entry(source_type: str, raw_content: str | None, image_path: str | None) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO entries (source_type, raw_content, image_path, created_at, status) "
            "VALUES (?, ?, ?, ?, 'pending')",
            (source_type, raw_content, image_path, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _mark_processed(entry_id: int, summary: str, category: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE entries SET status = 'processed', summary = ?, category = ? WHERE id = ?",
            (summary, category, entry_id),
        )
        conn.commit()
    finally:
        conn.close()


def _mark_error(entry_id: int, error_message: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE entries SET status = 'error', error_message = ? WHERE id = ?",
            (error_message, entry_id),
        )
        conn.commit()
    finally:
        conn.close()


def _existing_categories() -> list[str]:
    conn = get_connection()
    try:
        return distinct_categories(conn)
    finally:
        conn.close()


async def _process_and_reply(
    update: Update, entry_id: int, raw_content: str | None, image_path: Path | None
) -> None:
    try:
        result = await process_entry(raw_content, image_path, _existing_categories())
    except ClaudeProcessingError:
        logger.exception("Failed to process entry %s", entry_id)
        _mark_error(entry_id, "processing failed -- see bot logs")
        await update.message.reply_text(
            "Saved, but I couldn't process it just now (it's still in your dashboard, just "
            "unsummarized). Nothing is lost."
        )
        return

    _mark_processed(entry_id, result["summary"], result["category"])
    await update.message.reply_text(f"[{result['category']}] {result['summary']}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    source_type = "url" if text.startswith(("http://", "https://")) else "text"
    entry_id = _insert_entry(source_type, text, None)
    await update.message.reply_text("Got it -- researching…")
    await _process_and_reply(update, entry_id, text, None)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    photo = update.message.photo[-1]  # largest available size
    file = await photo.get_file()
    filename = f"{uuid.uuid4().hex}.jpg"
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    dest = IMAGES_DIR / filename
    await file.download_to_drive(custom_path=str(dest))

    caption = update.message.caption
    entry_id = _insert_entry("screenshot", caption, filename)
    await update.message.reply_text("Got it -- researching…")
    await _process_and_reply(update, entry_id, caption, dest)


def main() -> None:
    ensure_workspace_trusted()

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Idea Vault bot starting (long polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
