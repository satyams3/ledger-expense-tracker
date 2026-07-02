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
    if category == "emi" and type == "expense":
        _apply_emi_to_loan(note, amount)
    return result.data[0]["id"]


def _apply_emi_to_loan(note, amount):
    """Best-effort: if an emi txn's note mentions an active loan by name,
    reduce that loan's remaining balance. Silently does nothing if no
    loan matches — the txn is still logged either way.
    """
    note_lower = (note or "").lower()
    if not note_lower:
        return
    for loan in list_loans():
        if loan["name"].lower() in note_lower:
            new_remaining = max(0, loan["remaining"] - amount)
            client = _get_client()
            client.table("loans").update({
                "remaining": new_remaining,
                "active": new_remaining > 0,
            }).eq("id", loan["id"]).execute()
            break


def add_loan(name, principal, emi_amount=None, chat_id=None):
    """Register a new loan. Returns the new loan's id."""
    client = _get_client()
    result = client.table("loans").insert({
        "name": name,
        "principal": principal,
        "remaining": principal,
        "emi_amount": emi_amount,
        "chat_id": chat_id,
        "active": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }).execute()
    return result.data[0]["id"]


def list_loans(include_closed=False):
    """All loans, active ones first (or all, if include_closed)."""
    client = _get_client()
    query = client.table("loans").select("*")
    if not include_closed:
        query = query.eq("active", True)
    result = query.order("created_at").execute()
    return result.data


def delete_loan(loan_id):
    client = _get_client()
    client.table("loans").delete().eq("id", loan_id).execute()


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


def add_recurring(amount, category, note, day_of_month, type="expense", chat_id=None):
    """Register a recurring transaction. Returns the new rule's id."""
    client = _get_client()
    result = client.table("recurring").insert({
        "amount": amount,
        "category": category,
        "note": note,
        "type": type,
        "day_of_month": day_of_month,
        "chat_id": chat_id,
        "active": True,
    }).execute()
    return result.data[0]["id"]


def list_recurring():
    """All active recurring rules."""
    client = _get_client()
    result = (
        client.table("recurring")
        .select("*")
        .eq("active", True)
        .order("day_of_month")
        .execute()
    )
    return result.data


def delete_recurring(rule_id):
    client = _get_client()
    client.table("recurring").delete().eq("id", rule_id).execute()


def run_due_recurring(today=None):
    """Insert a txn for every active rule due today that hasn't already run
    this month. Returns the list of txns inserted. Safe to call more than
    once a day — last_run prevents double-logging.
    """
    today = today or date.today()
    this_month = today.isoformat()[:7]
    inserted = []
    for rule in list_recurring():
        if rule["day_of_month"] != today.day:
            continue
        if rule.get("last_run") == this_month:
            continue
        txn_id = add(
            amount=rule["amount"],
            category=rule["category"],
            note=rule["note"],
            type=rule["type"],
            chat_id=rule["chat_id"],
            txn_date=today.isoformat(),
        )
        client = _get_client()
        client.table("recurring").update({"last_run": this_month}).eq("id", rule["id"]).execute()
        inserted.append({"txn_id": txn_id, "rule_id": rule["id"], "amount": rule["amount"], "category": rule["category"]})
    return inserted


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
