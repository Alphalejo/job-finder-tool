import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, ContextTypes


logging.basicConfig(
    filename="./App_log/tlg_bot.log",
    level=logging.INFO,
)
load_dotenv()

try:
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    logging.info("Environment variables loaded.")
except Exception as e:
    logging.critical("Failed loading enviorenment variables: ", e)

MATCH_THRESHOLD = 65
logging.info("set match threshold to: %d", MATCH_THRESHOLD)

BASE_DIR = os.path.dirname(__file__)
JOBS_PATH = os.path.abspath(os.path.join(BASE_DIR, "../Data/compressed_jobs.json"))
APPROVED_PATH = os.path.abspath(os.path.join(BASE_DIR, "../Data/approved_jobs.json"))

#--------------------------------------------------------------------------------------------------------------

def load_pending_jobs() -> list[dict]:
    """Loads jobs from Phase 3 output and keeps only those above the match threshold."""
    with open(JOBS_PATH, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    pending = [job for job in jobs if job["match"] >= MATCH_THRESHOLD]
    logging.info(f"[Telegram] {len(pending)} of {len(jobs)} jobs passed the {MATCH_THRESHOLD}% threshold.")
    return pending

#--------------------------------------------------------------------------------------------------------------

async def send_job_notification(app: Application, job_index: int, job: dict) -> None:
    """
    Sends a single job as a Telegram message with two inline buttons.
    callback_data carries the action ('approve'/'reject') and the job's index,
    so the callback handler in Part 3 knows which job the button belongs to.
    """
    text = (
        f"*{job['role']}* @ {job['company']}\n"
        f"Match: {job['match']}%\n"
        f"{job['link']}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{job_index}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{job_index}"),
        ]
    ])

    await app.bot.send_message(
        chat_id=CHAT_ID,
        text=text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )

#--------------------------------------------------------------------------------------------------------------

async def handle_button_press(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Fires every time a user taps Approve/Reject.
    update.callback_query.data is the exact string we set in callback_data
    (e.g. "approve:3"), so we split it back into action + job_index.
    """
    query = update.callback_query
    await query.answer()  # acknowledges the tap so Telegram stops the loading spinner

    action, index_str = query.data.split(":")
    job_index = int(index_str)

    jobs_map = context.application.bot_data["jobs_map"]
    results = context.application.bot_data["results"]
    job = jobs_map[job_index]

    job["status"] = "approved" if action == "approve" else "rejected"
    job["checked_time"] = datetime.now(timezone.utc).isoformat()
    results.append(job)

    # Edit the original message: swap the buttons for a plain status line
    status_label = "✅ Approved" if action == "approve" else "❌ Rejected"
    await query.edit_message_text(
        text=f"{query.message.text}\n\n*{status_label}*",
        parse_mode="Markdown",
    )

    context.application.bot_data["pending_count"] -= 1
    if context.application.bot_data["pending_count"] == 0:
        context.application.bot_data["done_event"].set()

#--------------------------------------------------------------------------------------------------------------

async def main() -> None:
    """
    Wires everything together:
    1. Builds the bot application and registers the button handler.
    2. Starts polling (listening for button taps in the background).
    3. Sends one notification per pending job.
    4. Waits until every job has been answered.
    5. Saves approved jobs and stops the bot cleanly.
    """
    logging.info("Loading pending jobs")
    pending_jobs = load_pending_jobs()
    if not pending_jobs:
        logging.warning("[Telegram] No jobs to notify. Exiting.")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(handle_button_press))

    # Shared state read/written by handle_button_press (Part 3)
    app.bot_data["jobs_map"] = {i: job for i, job in enumerate(pending_jobs)}
    app.bot_data["results"] = []
    app.bot_data["pending_count"] = len(pending_jobs)
    app.bot_data["done_event"] = asyncio.Event()

    async with app:
        await app.start()
        await app.updater.start_polling()

        for i, job in app.bot_data["jobs_map"].items():
            await send_job_notification(app, i, job)

        logging.info("[Telegram] Notifications sent. Waiting for approvals...")
        await app.bot_data["done_event"].wait()

        await app.updater.stop()
        await app.stop()

    results = app.bot_data["results"]
    approved = [job for job in results if job["status"] == "approved"]

    with open(APPROVED_PATH, "w", encoding="utf-8") as f:
        json.dump(approved, f, indent=2, ensure_ascii=False)

    logging.info(f"[Telegram] Done. {len(approved)} approved job(s) saved to {APPROVED_PATH}")

#--------------------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(main())