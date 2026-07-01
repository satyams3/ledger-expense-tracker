"""
api/txn.py — edit / delete a single transaction, called from the dashboard.

PATCH /api/txn?id=5   body: {"amount": 600, "category": "food", "note": "..."}
DELETE /api/txn?id=5
"""

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import truststore
truststore.inject_into_ssl()

import db


class handler(BaseHTTPRequestHandler):
    def _txn_id(self):
        qs = parse_qs(urlparse(self.path).query)
        return int(qs["id"][0])

    def _ok(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def _error(self, message, status=400):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": False, "error": message}).encode("utf-8"))

    def do_PATCH(self):
        try:
            txn_id = self._txn_id()
        except (KeyError, ValueError):
            self._error("missing or invalid id")
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        db.update(txn_id, **body)
        self._ok()

    def do_DELETE(self):
        try:
            txn_id = self._txn_id()
        except (KeyError, ValueError):
            self._error("missing or invalid id")
            return
        db.delete(txn_id)
        self._ok()
