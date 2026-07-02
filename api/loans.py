"""
api/loans.py — manage loans, called from the dashboard.

GET    /api/loans        list active loans, with remaining balance
POST   /api/loans        body: {"name", "principal", "emi_amount"}
DELETE /api/loans?id=5   close/remove a loan

Loan balances are reduced automatically in db.add() whenever an "emi"
category txn's note mentions the loan's name (see _apply_emi_to_loan).
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
        self._ok({"loans": db.list_loans()})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if "name" not in body or "principal" not in body:
            self._error("name and principal are required")
            return
        loan_id = db.add_loan(
            name=body["name"],
            principal=float(body["principal"]),
            emi_amount=float(body["emi_amount"]) if body.get("emi_amount") else None,
        )
        self._ok({"ok": True, "id": loan_id})

    def do_DELETE(self):
        qs = parse_qs(urlparse(self.path).query)
        try:
            loan_id = int(qs["id"][0])
        except (KeyError, ValueError):
            self._error("missing or invalid id")
            return
        db.delete_loan(loan_id)
        self._ok()
