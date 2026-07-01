"""
api/data.py — live read endpoint for the dashboard on Vercel.

The dashboard runs in the browser and never gets Supabase credentials
directly; it calls this endpoint instead, which holds the key server-side
(env vars) and returns the same shape export.py used to write into data.js.
"""

import json
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import truststore
truststore.inject_into_ssl()

import db

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


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        config = load_config()
        rows = db.all_rows()
        safe_rows = [
            {
                "id": r["id"],
                "date": r["date"],
                "category": r["category"],
                "amount": r["amount"],
                "note": r["note"],
                "type": r["type"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
        payload = {
            "data": safe_rows,
            "config": {
                "currency": config.get("currency", "₹"),
                "monthlyBudget": config.get("monthlyBudget", 0),
                "budgets": config.get("budgets", {}),
            },
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)
