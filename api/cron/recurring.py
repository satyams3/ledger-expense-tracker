"""
api/cron/recurring.py — daily Vercel Cron job that logs any recurring
transactions due today (see db.run_due_recurring).

Secured with CRON_SECRET: Vercel sends `Authorization: Bearer <CRON_SECRET>`
automatically when the env var is set on the project. See vercel.json for
the schedule.
"""

import json
import os
from http.server import BaseHTTPRequestHandler

import truststore
truststore.inject_into_ssl()

import db


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        cron_secret = os.environ.get("CRON_SECRET")
        auth_header = self.headers.get("Authorization")
        if cron_secret and auth_header != f"Bearer {cron_secret}":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"ok": false}')
            return

        inserted = db.run_due_recurring()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "inserted": inserted}).encode("utf-8"))
