"""
Bot Telegram: YouTube → Portrait.
Invia un link YouTube, il bot scarica il video e lo ritaglia in 9:16 con zoom regolabile (0–30%).
"""

import asyncio
import logging
import os
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from yt_portrait import (
    normalize_youtube_url,
    run_download_and_crop,
    download_for_preview,
    get_downloaded_path,
    extract_preview_frame,
    crop_to_portrait,
    ffmpeg_available,
    ZOOM_PCT_MAX,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Limite Telegram per invio video (circa 50 MB)
TELEGRAM_VIDEO_MAX_BYTES = 49 * 1024 * 1024


def get_zoom_keyboard():
    """Tastiera inline per scegliere lo zoom (0, 7, 15, 30%)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("0%", callback_data="zoom_0"),
            InlineKeyboardButton("7%", callback_data="zoom_7"),
        ],
        [
            InlineKeyboardButton("15%", callback_data="zoom_15"),
            InlineKeyboardButton("30%", callback_data="zoom_30"),
        ],
    ])


def get_confirm_keyboard():
    """Tastiera dopo anteprima: Conferma o Cambia zoom."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Conferma e scarica", callback_data="confirm")],
        [InlineKeyboardButton("🔄 Cambia zoom", callback_data="change_zoom")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Ciao! Sono il bot **YouTube → Portrait**.\n\n"
        "Invia un link YouTube (video o Shorts) e ti restituirò il video ritagliato in formato portrait 9:16.\n\n"
        "• Puoi inviare direttamente il link.\n"
        "• Oppure usa /download <link> [zoom 0-30] (es. /download https://... 7).\n"
        "• Zoom predefinito: 7%.",
        parse_mode="Markdown",
    )


def extract_youtube_url_from_message(message) -> str:
    """Estrae l'URL YouTube dal messaggio. Preferisce l'URL più lungo che sia chiaramente YouTube."""
    text = (message.text or message.caption or "").strip()
    if not text:
        return ""
    candidates = []
    if message.entities:
        for ent in message.entities:
            if ent.type in (MessageEntity.URL, MessageEntity.TEXT_LINK):
                if ent.type == MessageEntity.TEXT_LINK and ent.url:
                    link = ent.url
                else:
                    link = text[ent.offset : ent.offset + ent.length]
                link = (normalize_youtube_url(link) or "").strip()
                if link and ("youtube" in link or "youtu.be" in link) and len(link) >= 20:
                    candidates.append(link)
    # Testo intero come candidato (spesso è l'URL quando l'utente incolla il link)
    full = (normalize_youtube_url(text) or "").strip()
    if full and ("youtube" in full or "youtu.be" in full) and len(full) >= 20:
        candidates.append(full)
    # Scegli l'URL più lungo (di solito il più completo)
    return max(candidates, key=len) if candidates else ""


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = extract_youtube_url_from_message(update.message)
    if not url:
        await update.message.reply_text(
            "Invia un link YouTube valido (es. youtube.com/watch?v=... o youtu.be/...)."
        )
        return
    context.user_data["pending_url"] = url
    context.user_data["pending_zoom"] = 7
    context.user_data.pop("preview_tmpdir", None)
    context.user_data.pop("preview_url", None)
    await update.message.reply_text(
        "Zoom per il ritaglio portrait? (predefinito 7%)",
        reply_markup=get_zoom_keyboard(),
    )


async def handle_download_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = (context.args or [])
    if not args:
        await update.message.reply_text(
            "Uso: /download <link YouTube> [zoom 0-30]\nEsempio: /download https://youtu.be/xxx 7"
        )
        return
    url = normalize_youtube_url(args[0])
    if not url:
        await update.message.reply_text("Link YouTube non valido.")
        return
    zoom_pct = 7
    if len(args) >= 2:
        try:
            z = float(args[1])
            zoom_pct = max(0, min(ZOOM_PCT_MAX, z))
        except ValueError:
            pass
    await run_job(update, context, url, zoom_pct, update.message)


async def callback_zoom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("zoom_"):
        return
    try:
        zoom_pct = int(data.replace("zoom_", ""))
        zoom_pct = max(0, min(ZOOM_PCT_MAX, zoom_pct))
    except ValueError:
        zoom_pct = 7
    url = (context.user_data.get("pending_url") or "").strip()
    if not url or "youtube" not in url and "youtu.be" not in url or len(url) < 20:
        await query.edit_message_text("Sessione scaduta o link non valido. Invia di nuovo il link YouTube.")
        context.user_data.pop("pending_url", None)
        return
    context.user_data["pending_zoom"] = zoom_pct
    await query.edit_message_text("⏳ Preparazione anteprima…")
    chat_id = query.message.chat_id
    preview_tmpdir = context.user_data.get("preview_tmpdir")
    preview_url = context.user_data.get("preview_url")
    if not preview_tmpdir or preview_url != url or not os.path.isdir(preview_tmpdir):
        loop = asyncio.get_event_loop()
        tmpdir, err = await loop.run_in_executor(None, lambda: download_for_preview(url))
        if err or not tmpdir:
            await query.edit_message_text(f"❌ Errore download: {err or 'Impossibile scaricare'}")
            return
        context.user_data["preview_tmpdir"] = tmpdir
        context.user_data["preview_url"] = url
        preview_tmpdir = tmpdir
    input_path = get_downloaded_path(preview_tmpdir, "video")
    if not input_path or not os.path.isfile(input_path):
        await query.edit_message_text("❌ File video non trovato. Riprova con un altro link.")
        return
    if not ffmpeg_available():
        await query.edit_message_text("❌ ffmpeg non disponibile per l'anteprima.")
        return
    preview_png = os.path.join(preview_tmpdir, f"preview_{int(zoom_pct)}.png")
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(
        None,
        lambda: extract_preview_frame(input_path, zoom_pct, preview_png),
    )
    if not ok or not os.path.isfile(preview_png):
        await query.edit_message_text("❌ Impossibile generare l'anteprima.")
        return
    with open(preview_png, "rb") as f:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=f,
            caption=f"Anteprima zoom {zoom_pct}%. Conferma per scaricare il video in portrait 9:16.",
            reply_markup=get_confirm_keyboard(),
        )
    await query.edit_message_text(f"Zoom {zoom_pct}% selezionato. Usa i pulsanti sotto l'anteprima.")


async def callback_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    preview_tmpdir = context.user_data.get("preview_tmpdir")
    zoom_pct = context.user_data.get("pending_zoom", 7)
    if not preview_tmpdir or not os.path.isdir(preview_tmpdir):
        await query.edit_message_caption(caption="❌ Sessione scaduta. Invia di nuovo il link.")
        _clear_preview_data(context)
        return
    input_path = get_downloaded_path(preview_tmpdir, "video")
    if not input_path or not os.path.isfile(input_path):
        await query.edit_message_caption(caption="❌ File non trovato. Riprova.")
        _clear_preview_data(context)
        return
    chat_id = query.message.chat_id
    try:
        await query.edit_message_caption(caption="⏳ Ritaglio e invio in corso…")
    except Exception:
        await context.bot.send_message(chat_id, "⏳ Ritaglio e invio in corso…")
    portrait_path = os.path.join(preview_tmpdir, "portrait.mp4")
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(
        None,
        lambda: crop_to_portrait(input_path, portrait_path, zoom_pct=zoom_pct),
    )
    if not ok or not os.path.isfile(portrait_path):
        await context.bot.send_message(chat_id, "❌ Errore durante il ritaglio.")
        _clear_preview_data(context)
        return
    size = os.path.getsize(portrait_path)
    if size <= TELEGRAM_VIDEO_MAX_BYTES:
        with open(portrait_path, "rb") as f:
            await context.bot.send_video(
                chat_id=chat_id,
                video=f,
                filename="video_portrait.mp4",
                caption="Portrait 9:16",
            )
    else:
        with open(portrait_path, "rb") as f:
            await context.bot.send_document(
                chat_id=chat_id,
                document=f,
                filename="video_portrait.mp4",
                caption="Video >50MB inviato come documento.",
            )
    try:
        await query.message.delete()
    except Exception:
        pass
    _clear_preview_data(context)
    _cleanup_tmpdir(preview_tmpdir)


async def callback_change_zoom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    try:
        await query.edit_message_caption(
            caption="Scegli un altro zoom:",
            reply_markup=get_zoom_keyboard(),
        )
    except Exception:
        await query.edit_message_text(
            "Scegli un altro zoom:",
            reply_markup=get_zoom_keyboard(),
        )


def _clear_preview_data(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("preview_tmpdir", None)
    context.user_data.pop("preview_url", None)
    context.user_data.pop("pending_zoom", None)
    context.user_data.pop("pending_url", None)


def _cleanup_tmpdir(tmpdir: str) -> None:
    if not tmpdir or not os.path.isdir(tmpdir):
        return
    try:
        for f in Path(tmpdir).iterdir():
            f.unlink(missing_ok=True)
        os.rmdir(tmpdir)
    except OSError:
        pass


async def run_job(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str, zoom_pct: float, message):
    url = (url or "").strip()
    if not url or "youtube" not in url and "youtu.be" not in url or len(url) < 20:
        await context.bot.send_message(
            message.chat_id,
            "❌ Link non valido. Invia un link YouTube completo (es. youtube.com/watch?v=...).",
        )
        return
    chat_id = message.chat_id
    status_msg = await context.bot.send_message(chat_id, "⏳ Download in corso…")

    def progress(stage: str, pct: float):
        # Aggiornamento sincrono; in produzione si può usare run_coroutine_threadsafe
        pass

    loop = asyncio.get_event_loop()
    ok, err, path = await loop.run_in_executor(
        None,
        lambda: run_download_and_crop(url, zoom_pct=zoom_pct, progress_callback=progress),
    )

    try:
        if not ok:
            await status_msg.edit_text(f"❌ Errore: {err}")
            return
        if not path or not os.path.isfile(path):
            await status_msg.edit_text("❌ File non disponibile.")
            return
        size = os.path.getsize(path)
        await status_msg.edit_text("📤 Invio video…")
        if size <= TELEGRAM_VIDEO_MAX_BYTES:
            with open(path, "rb") as f:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=f,
                    filename="video_portrait.mp4",
                    caption="Portrait 9:16",
                )
        else:
            with open(path, "rb") as f:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename="video_portrait.mp4",
                    caption="Video >50MB inviato come documento.",
                )
        await status_msg.delete()
    finally:
        if path and os.path.isfile(path):
            _cleanup_tmpdir(str(Path(path).parent))


def main() -> None:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        token_path = Path(__file__).resolve().parent / "token.txt"
        if token_path.is_file():
            token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        logger.error("Imposta TELEGRAM_BOT_TOKEN (variabile d'ambiente o file token.txt nella cartella del bot).")
        return
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("download", handle_download_command))
    app.add_handler(CallbackQueryHandler(callback_zoom, pattern="^zoom_"))
    app.add_handler(CallbackQueryHandler(callback_confirm, pattern="^confirm$"))
    app.add_handler(CallbackQueryHandler(callback_change_zoom, pattern="^change_zoom$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot avviato.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
