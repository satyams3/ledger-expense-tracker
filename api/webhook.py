"""
api/webhook.py — Telegram webhook handler for Vercel.

Telegram POSTs each update here (set once via setWebhook). Replaces
bot.py's polling loop, which can't run on Vercel's serverless functions
(no long-lived process). Talks to Supabase via db.py, same as bot.py.
"""

import json
import os
from datetime import date
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import truststore
truststore.inject_into_ssl()

import requests

import db
from parser import parse

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

HERE = Path(__file__).parent.parent
CONFIG_PATH = HERE / "config.json"
if not CONFIG_PATH.exists():
    CONFIG_PATH = HERE / "config.example.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["supabase_url"] = os.environ.get("SUPABASE_URL", config.get("supabase_url"))
    config["supabase_key"] = os.environ.get("SUPABASE_KEY", config.get("supabase_key"))
    return config


def send_message(chat_id, text):
    requests.post(f"{API_URL}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)


def make_progress_bar(spent, budget, width=12):
    if budget <= 0:
        return "[no budget set]"
    frac = min(spent / budget, 1.0)
    filled = round(frac * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {round(frac * 100)}%"


def handle_update(update):
    message = update.get("message")
    if not message or "text" not in message:
        return
    chat_id = message["chat"]["id"]
    text = message["text"]
    config = load_config()
    currency = config.get("currency", "₹")

    if text.startswith("/start"):
        send_message(chat_id,
            "💸 Expense Tracker Bot\n\n"
            "Just text me what you spent, in plain English:\n"
            "  • spent 500 on ola\n"
            "  • swiggy 420 dinner\n"
            "  • 1.5k myntra shirt\n"
            "  • got salary 75000\n\n"
            "Commands: /total /undo /budget /help")
        return

    if text.startswith("/help"):
        send_message(chat_id,
            "How to log spends\n"
            "Send any plain-English message with an amount in it.\n\n"
            "Commands\n"
            "/total — this month's spend vs budget\n"
            "/undo — delete the last entry you logged\n"
            "/budget — show your per-category caps\n"
            "/help — this message")
        return

    if text.startswith("/total"):
        month = date.today().isoformat()[:7]
        spent = db.month_total(month, type="expense")
        budget = config.get("monthlyBudget", 0)
        remaining = budget - spent
        send_message(chat_id,
            f"This month so far\n"
            f"Spent: {currency}{spent:,.0f} of {currency}{budget:,.0f}\n"
            f"{make_progress_bar(spent, budget)}\n"
            f"{'Remaining' if remaining >= 0 else 'Over by'}: {currency}{abs(remaining):,.0f}")
        return

    if text.startswith("/budget"):
        budgets = config.get("budgets", {})
        month = date.today().isoformat()[:7]
        spent_by_cat = db.category_totals(month, type="expense")
        lines = ["Budgets this month"]
        for cat, cap in budgets.items():
            spent = spent_by_cat.get(cat, 0)
            if cap <= 0:
                lines.append(f"  {cat}: {currency}{spent:,.0f} (no cap)")
                continue
            flag = " ⚠️" if spent > cap else ""
            lines.append(f"  {cat}: {currency}{spent:,.0f} / {currency}{cap:,.0f}{flag}")
        send_message(chat_id, "\n".join(lines))
        return

    if text.startswith("/undo"):
        deleted = db.undo_last(chat_id=chat_id)
        if deleted is None:
            send_message(chat_id, "Nothing to undo.")
            return
        send_message(chat_id,
            f"🗑 Undone: {currency}{deleted['amount']:,.0f} — {deleted['note']} ({deleted['category']})")
        return

    txn = parse(text)
    if txn is None:
        send_message(chat_id,
            "Couldn't find an amount in that message — try something like spent 500 on ola.")
        return

    db.add(
        amount=txn["amount"],
        category=txn["category"],
        note=txn["note"],
        type=txn["type"],
        chat_id=chat_id,
    )

    if txn["type"] == "income":
        send_message(chat_id, f"✅ Logged income: {currency}{txn['amount']:,.0f} — {txn['note']}")
        return

    month = date.today().isoformat()[:7]
    spent = db.month_total(month, type="expense")
    budget = config.get("monthlyBudget", 0)
    send_message(chat_id,
        f"✅ Logged: {currency}{txn['amount']:,.0f} — {txn['note']} ({txn['category']})\n"
        f"Month total: {currency}{spent:,.0f} of {currency}{budget:,.0f}\n"
        f"{make_progress_bar(spent, budget)}")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            handle_update(json.loads(body))
        except Exception as e:
            print(f"webhook error: {e}")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Ledger webhook is live.")
