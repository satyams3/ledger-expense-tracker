# Ledger — Telegram Expense Tracker

A personal expense tracker. You text a Telegram bot in plain English; every
transaction lands in a Supabase (Postgres) table; an HTML dashboard reads a
generated data file and renders all charts as inline SVG.

---

## Setup in 5 steps

### 1  Get a bot token from BotFather

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts (pick any name and username).
3. Copy the token that looks like `123456789:ABCDefgh...`.

### 2  Edit `config.json`

Open `config.json` and paste your token:

```json
{
  "telegram_token": "123456789:ABCDefgh...",
  "supabase_url": "https://xxxx.supabase.co",
  "supabase_key": "your-anon-key",
  "currency": "₹",
  "monthlyBudget": 40000,
  "budgets": {
    "travel": 4000,
    "food": 6000,
    "groceries": 5000,
    "clothes": 3000,
    "rent": 12000,
    "bills": 3000,
    "luxuries": 3000,
    "investments": 0,
    "health": 2000,
    "education": 2000,
    "other": 2000
  }
}
```

Set `"investments": 0` (or omit the key) to skip that cap.

### 3  Install dependencies

```bash
pip install python-telegram-bot supabase truststore
```

Everything else (`json`, `re`, `pathlib`) is in the Python standard library.
(`truststore` fixes SSL cert issues on some Windows machines by using the
OS cert store instead of the bundled one.)

### 4  Run the bot

```bash
python bot.py
```

The bot will print `Bot starting — Ctrl+C to stop.` and begin polling
Telegram. Leave the terminal open (or run it as a background process /
systemd service if you want it always-on).

### 5  Open the dashboard

Double-click `dashboard.html`.  
No server needed — it loads `data.js` (a plain `<script>` tag, not `fetch`),
so it works from `file://` in any modern browser.  
The dashboard regenerates automatically every time the bot receives a message.

---

## Example messages

| What you send                     | How it's parsed                         |
|-----------------------------------|-----------------------------------------|
| `spent 500 on ola`                | ₹500 · travel                           |
| `swiggy 420 dinner`               | ₹420 · food                             |
| `1.5k myntra shirt`               | ₹1,500 · clothes                        |
| `2l invested in fd`               | ₹2,00,000 · investments                 |
| `got salary 75000`                | ₹75,000 income                          |
| `rs 1,250 electricity bill`       | ₹1,250 · bills                          |
| `₹89 chai`                        | ₹89 · food                              |
| `300rs petrol`                    | ₹300 · travel                           |
| `cashback received 45`            | ₹45 income                              |
| `gym membership 1999`             | ₹1,999 · luxuries                       |
| `blinkit 650 groceries`           | ₹650 · groceries                        |
| `sip 5000 mutual fund`            | ₹5,000 · investments                    |
| `netflix 199`                     | ₹199 · luxuries                         |
| `doctor 800`                      | ₹800 · health                           |

### Amount formats understood

| Input   | Interpreted as      |
|---------|---------------------|
| `500`   | ₹500                |
| `1,250` | ₹1,250              |
| `1.5k`  | ₹1,500              |
| `2l`    | ₹2,00,000           |
| `1.2cr` | ₹1,20,00,000        |
| `rs 500` / `₹500` / `500rs` / `500 inr` | ₹500 |

### Bot commands

| Command   | What it does                                   |
|-----------|------------------------------------------------|
| `/start`  | Welcome message + quick examples               |
| `/help`   | Full usage guide                               |
| `/total`  | This month's spend vs budget with a text bar   |
| `/undo`   | Delete the last entry you logged               |
| `/budget` | Per-category spend vs caps                     |

---

## File layout

```
expense-tracker/
├── bot.py           Telegram bot (run this)
├── parser.py        Plain-English → {amount, category, note, type}
├── db.py            Supabase helpers (add, undo_last, all_rows, month_total)
├── export.py        Supabase → data.js (browser-readable, no server needed)
├── config.json      Your token + Supabase URL/key + budgets
├── dashboard.html   HTML dashboard (double-click to open)
├── data.js          Auto-generated; regenerated after every message
└── README.md        This file
```

---

## Customising categories

All keyword lists live at the top of `parser.py` in `CATEGORY_KEYWORDS`.
Add or remove strings to tune detection. Example — adding "dunzo" to groceries:

```python
"groceries": [
    "blinkit", "zepto", "instamart", "bigbasket", "grocery", "groceries",
    "dmart", "dunzo",   # ← added
    ...
],
```

Restart `bot.py` for changes to take effect. Existing DB entries are not
re-categorised (run a SQL UPDATE if you want to fix old rows).

---

## Changing the currency

In `config.json` set `"currency": "$"` (or any symbol). The dashboard and
bot replies will pick it up automatically.

---

## Deploying to Render (optional)

If your network blocks `api.telegram.org` (corporate proxy, Zscaler, etc.),
run the bot on [Render](https://render.com) instead:

1. Push this repo to GitHub.
2. On Render: **New → Blueprint**, point at the repo (`render.yaml` is
   already set up as a Background Worker).
3. Set the three env vars Render prompts for: `TELEGRAM_TOKEN`,
   `SUPABASE_URL`, `SUPABASE_KEY` (values from your local `config.json`).
4. Deploy. `config.json` isn't committed (see `.gitignore`) — the bot falls
   back to `config.example.json` for non-secret settings (currency, budgets)
   and reads the three secrets from env vars instead.

Note: the dashboard (`dashboard.html` + `data.js`) is only regenerated on
the machine running the bot. If the bot runs on Render, either pull
`data.js` down periodically or run `export.py` locally against the same
Supabase project to refresh it.

## Always-on (optional)

To keep the bot running after you close the terminal, create a systemd unit:

```ini
# /etc/systemd/system/ledger-bot.service
[Unit]
Description=Ledger Telegram Expense Bot

[Service]
ExecStart=/usr/bin/python3 /path/to/expense-tracker/bot.py
WorkingDirectory=/path/to/expense-tracker
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now ledger-bot
```

---

## Privacy

- The bot token and Supabase key live only in `config.json` on your machine.
- `data.js` (the browser file) contains **only** amounts, categories, dates, and
  notes — never the token, never your chat ID, never the Supabase key.
- Transaction data is stored in your own Supabase (Postgres) project.
  `bot.py` talks to Telegram's API (to receive messages) and your Supabase
  project's REST API (to read/write transactions) — no other network calls.
- The dashboard itself makes no network requests; it only reads the
  already-generated `data.js`.
