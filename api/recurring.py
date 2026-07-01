"""
api/recurring.py — manage recurring transaction rules, called from the dashboard.

GET    /api/recurring        list active rules
POST   /api/recurring        body: {"amount", "category", "note", "type", "day_of_month"}
DELETE /api/recurring?id=5
"""

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import truststore
truststore.inject_into_ssl()

import db


class handler(BaseHTTPRequestHandler):
    def _ok(self, payload=None):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload if payload is not None else {"ok": True}).encode("utf-8"))

    def _error(self, message, status=400):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": False, "error": message}).encode("utf-8"))

    def do_GET(self):
        self._ok({"rules": db.list_recurring()})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        required = {"amount", "category", "day_of_month"}
        if not required.issubset(body):
            self._error("amount, category, and day_of_month are required")
            return
        rule_id = db.add_recurring(
            amount=body["amount"],
            category=body["category"],
            note=body.get("note"),
            day_of_month=int(body["day_of_month"]),
            type=body.get("type", "expense"),
        )
        self._ok({"ok": True, "id": rule_id})

    def do_DELETE(self):
        qs = parse_qs(urlparse(self.path).query)
        try:
            rule_id = int(qs["id"][0])
        except (KeyError, ValueError):
            self._error("missing or invalid id")
            return
        db.delete_recurring(rule_id)
        self._ok()
