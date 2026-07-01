"""
bot.py — Telegram bot front-end for the expense tracker.

Plain text message -> parser.parse() -> db.add() -> export.run_export()
-> confirmation reply with the month total vs budget.

Commands:
    /start   welcome + quick examples
    /help    how to log spends, list of commands
    /total   this month's spend vs budget, with a progress bar
    /undo    delete the last entry you logged
    /budget  show per-category caps

Reads the token and budgets from config.json. Nothing here calls any
service other than Telegram's own API (required for the bot to receive
messages at all) — all storage and computation is local.

Setup:
    pip install python-telegram-bot
    python bot.py
"""

import json
import logging
import os
from pathlib import Path
from datetime import date

import truststore
truststore.inject_into_ssl()  # same cert-store fix as db.py

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import db
import export
from parser import parse

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.json"
if not CONFIG_PATH.exists():
    CONFIG_PATH = HERE / "config.example.json"

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("expense-bot")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["telegram_token"] = os.environ.get("TELEGRAM_TOKEN", config.get("telegram_token"))
    config["supabase_url"] = os.environ.get("SUPABASE_URL", config.get("supabase_url"))
    config["supabase_key"] = os.environ.get("SUPABASE_KEY", config.get("supabase_key"))
    return config


def make_progress_bar(spent, budget, width=12):
    if budget <= 0:
        return "[no budget set]"
    frac = min(spent / budget, 1.0)
    filled = round(frac * width)
    bar = "█" * filled + "░" * (width - filled)
    pct = round(frac * 100)
    return f"[{bar}] {pct}%"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "💸 *Expense Tracker Bot*\n\n"
        "Just text me what you spent, in plain English:\n"
        "  • `spent 500 on ola`\n"
        "  • `swiggy 420 dinner`\n"
        "  • `1.5k myntra shirt`\n"
        "  • `got salary 75000`\n\n"
        "Commands: /total /undo /budget /help"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "*How to log spends*\n"
        "Send any plain-English message with an amount in it. Examples:\n"
        "  • `spent 500 on ola` → travel\n"
        "  • `swiggy 420 dinner` → food\n"
        "  • `1.5k myntra shirt` → clothes (1.5k = 1500)\n"
        "  • `2l invested in fd` → investments (2l = 2,00,000)\n"
        "  • `rs 1250 electricity bill` → bills\n"
        "  • `got salary 75000` → income\n\n"
        "*Commands*\n"
        "/total — this month's spend vs budget\n"
        "/undo — delete the last entry you logged\n"
        "/budget — show your per-category caps\n"
        "/help — this message"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def total_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    month = date.today().isoformat()[:7]
    spent = db.month_total(month, type="expense")
    budget = config.get("monthlyBudget", 0)
    currency = config.get("currency", "₹")
    bar = make_progress_bar(spent, budget)
    remaining = budget - spent
    msg = (
        f"*This month so far*\n"
        f"Spent: {currency}{spent:,.0f} of {currency}{budget:,.0f}\n"
        f"{bar}\n"
        f"{'Remaining' if remaining >= 0 else 'Over by'}: "
        f"{currency}{abs(remaining):,.0f}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def budget_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = load_config()
    currency = config.get("currency", "₹")
    budgets = config.get("budgets", {})
    month = date.today().isoformat()[:7]
    spent_by_cat = db.category_totals(month, type="expense")

    lines = ["*Budgets this month*"]
    for cat, cap in budgets.items():
        spent = spent_by_cat.get(cat, 0)
        if cap <= 0:
            lines.append(f"  {cat}: {currency}{spent:,.0f} (no cap)")
            continue
        flag = " ⚠️" if spent > cap else ""
        lines.append(f"  {cat}: {currency}{spent:,.0f} / {currency}{cap:,.0f}{flag}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def undo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    deleted = db.undo_last(chat_id=chat_id)
    export.run_export()
    if deleted is None:
        await update.message.reply_text("Nothing to undo.")
        return
    currency = load_config().get("currency", "₹")
    await update.message.reply_text(
        f"🗑 Undone: {currency}{deleted['amount']:,.0f} — {deleted['note']} "
        f"({deleted['category']})"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    txn = parse(text)

    if txn is None:
        await update.message.reply_text(
            "Couldn't find an amount in that message — try something like "
            "`spent 500 on ola`.",
            parse_mode="Markdown",
        )
        return

    chat_id = update.effective_chat.id
    db.add(
        amount=txn["amount"],
        category=txn["category"],
        note=txn["note"],
        type=txn["type"],
        chat_id=chat_id,
    )
    export.run_export()

    config = load_config()
    currency = config.get("currency", "₹")

    if txn["type"] == "income":
        reply = (
            f"✅ Logged income: {currency}{txn['amount']:,.0f} — {txn['note']}"
        )
        await update.message.reply_text(reply)
        return

    month = date.today().isoformat()[:7]
    spent = db.month_total(month, type="expense")
    budget = config.get("monthlyBudget", 0)
    bar = make_progress_bar(spent, budget)

    reply = (
        f"✅ Logged: {currency}{txn['amount']:,.0f} — {txn['note']} "
        f"({txn['category']})\n"
        f"Month total: {currency}{spent:,.0f} of {currency}{budget:,.0f}\n"
        f"{bar}"
    )
    await update.message.reply_text(reply)


def main():
    config = load_config()
    token = config.get("telegram_token", "")
    if not token or token == "PASTE_YOUR_BOTFATHER_TOKEN_HERE":
        raise SystemExit(
            "Set telegram_token in config.json first — get one from @BotFather "
            "in Telegram (see README.md)."
        )

    db.init_db()
    export.run_export()  # make sure data.js exists even before the first message

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("total", total_cmd))
    app.add_handler(CommandHandler("undo", undo_cmd))
    app.add_handler(CommandHandler("budget", budget_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot starting — Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
