"""
db.py — Supabase (Postgres via REST API) storage for the expense tracker.

Single table "txns":
    id          bigserial PRIMARY KEY
    date        text      (YYYY-MM-DD, local date the txn was logged)
    category    text
    amount      numeric
    note        text
    type        text      ("expense" | "income")
    chat_id     bigint    (Telegram chat that logged it)
    created_at  text      (ISO timestamp, full precision)

Table lives in the Supabase project configured via supabase_url /
supabase_key in config.json. No local file, no sqlite.
"""

import json
import os
from datetime import datetime, date
from pathlib import Path

import truststore
truststore.inject_into_ssl()  # use Windows/OS cert store — certifi's bundle
                               # is missing an intermediate CA on this machine

from supabase import create_client, Client

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.json"
if not CONFIG_PATH.exists():
    CONFIG_PATH = HERE / "config.example.json"

_client: Client | None = None


def _load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["supabase_url"] = os.environ.get("SUPABASE_URL", config.get("supabase_url"))
    config["supabase_key"] = os.environ.get("SUPABASE_KEY", config.get("supabase_key"))
    return config


def _get_client() -> Client:
    global _client
    if _client is None:
        config = _load_config()
        _client = create_client(config["supabase_url"], config["supabase_key"])
    return _client


def init_db(db_path=None):
    """No-op — table is created once via Supabase migration, not at runtime."""
    pass


def add(amount, category, note, type="expense", chat_id=None,
        txn_date=None, db_path=None):
    """Insert a transaction. Returns the new row's id."""
    txn_date = txn_date or date.today().isoformat()
    created_at = datetime.now().isoformat(timespec="seconds")
    client = _get_client()
    result = client.table("txns").insert({
        "date": txn_date,
        "category": category,
        "amount": amount,
        "note": note,
        "type": type,
        "chat_id": chat_id,
        "created_at": created_at,
    }).execute()
    return result.data[0]["id"]


def update(txn_id, db_path=None, **fields):
    """Patch a transaction's amount/category/note/type/date by id."""
    allowed = {"amount", "category", "note", "type", "date"}
    patch = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not patch:
        return
    client = _get_client()
    client.table("txns").update(patch).eq("id", txn_id).execute()


def delete(txn_id, db_path=None):
    """Delete a transaction by id."""
    client = _get_client()
    client.table("txns").delete().eq("id", txn_id).execute()


def undo_last(chat_id=None, db_path=None):
    """Delete the most recently added row (optionally scoped to a chat).

    Returns the deleted row as a dict, or None if there was nothing to undo.
    """
    client = _get_client()
    query = client.table("txns").select("*")
    if chat_id is not None:
        query = query.eq("chat_id", chat_id)
    result = query.order("id", desc=True).limit(1).execute()

    if not result.data:
        return None

    row = result.data[0]
    client.table("txns").delete().eq("id", row["id"]).execute()
    return row


def all_rows(db_path=None):
    """Return every transaction, oldest first, as a list of dicts."""
    client = _get_client()
    result = client.table("txns").select("*").order("date").order("id").execute()
    return result.data


def month_total(month, db_path=None, type="expense"):
    """Sum of amounts for a given month ('YYYY-MM') and txn type.

    type=None sums both expenses and income together (rarely useful,
    but available).
    """
    client = _get_client()
    query = client.table("txns").select("amount").like("date", f"{month}%")
    if type is not None:
        query = query.eq("type", type)
    result = query.execute()
    return sum(r["amount"] for r in result.data)


def category_totals(month, db_path=None, type="expense"):
    """Dict of {category: total} for a given month."""
    client = _get_client()
    result = (
        client.table("txns")
        .select("category, amount")
        .like("date", f"{month}%")
        .eq("type", type)
        .execute()
    )
    totals = {}
    for r in result.data:
        totals[r["category"]] = totals.get(r["category"], 0) + r["amount"]
    return dict(sorted(totals.items(), key=lambda kv: kv[1], reverse=True))


if __name__ == "__main__":
    add(500, "travel", "Ola", "expense", chat_id=1)
    add(420, "food", "Swiggy Dinner", "expense", chat_id=1)
    add(75000, "other", "Salary", "income", chat_id=1)

    print("All rows:", all_rows())
    this_month = date.today().isoformat()[:7]
    print("Month total (expense):", month_total(this_month))
    print("Category totals:", category_totals(this_month))
    print("Undo:", undo_last(chat_id=1))
    print("All rows after undo:", all_rows())
    print("OK")
