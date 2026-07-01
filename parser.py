"""
parser.py — turn a plain-English Telegram message into a transaction dict.

    parse(message) -> {
        "amount":   float,
        "category": str,
        "note":     str,
        "type":     "expense" | "income",
    }

Returns None if no amount could be found in the message.

Everything that's likely to need editing (category keywords, income
keywords, filler words) lives in plain Python dicts/lists at the top of
the file — no need to touch the regex logic below to retune behaviour.
"""

import re

# --------------------------------------------------------------------------
# 1. CATEGORY KEYWORDS — edit freely. First match wins; order matters only
#    if a word appears in two lists (it shouldn't, but if it does the
#    category listed first in CATEGORY_KEYWORDS takes priority).
# --------------------------------------------------------------------------
CATEGORY_KEYWORDS = {
    "travel": [
        "ola", "uber", "metro", "petrol", "diesel", "fuel", "cab", "taxi",
        "auto", "rapido", "irctc", "train", "flight", "indigo", "parking",
        "toll", "fastag", "bus", "rickshaw", "bike taxi",
    ],
    "food": [
        "swiggy", "zomato", "chai", "coffee", "lunch", "dinner", "breakfast",
        "restaurant", "cafe", "tea", "snack", "food", "dominos", "pizza",
        "starbucks", "dhaba", "biryani", "eatsure", "ccd",
    ],
    "groceries": [
        "blinkit", "zepto", "instamart", "bigbasket", "grocery", "groceries",
        "dmart", "vegetables", "sabzi", "milk", "kirana", "supermarket",
    ],
    "clothes": [
        "myntra", "ajio", "shirt", "tshirt", "t-shirt", "jeans", "shoes",
        "clothes", "clothing", "footwear", "zara", "h&m", "uniqlo",
        "apparel", "dress", "kurta", "sneakers",
    ],
    "rent": [
        "rent", "landlord", "lease", "maintenance", "society maintenance",
        "pg fee", "hostel fee",
    ],
    "bills": [
        "electricity", "wifi", "broadband", "recharge", "mobile bill",
        "phone bill", "gas bill", "water bill", "dth", "jio", "airtel",
        "vi bill", "bill", "emi", "insurance premium",
    ],
    "luxuries": [
        "netflix", "prime video", "hotstar", "spotify", "gym", "movie",
        "pvr", "inox", "bookmyshow", "concert", "party", "club", "bar",
        "alcohol", "beer", "wine", "cigarette", "vacation", "trip",
        "shopping spree", "gadget", "gaming",
    ],
    "investments": [
        "sip", "etf", "stocks", "mutual fund", "mf", "nps", "ppf", "fd",
        "fixed deposit", "rd", "gold", "crypto", "bitcoin", "zerodha",
        "groww", "upstox", "invest",
    ],
    "health": [
        "doctor", "medicine", "pharmacy", "hospital", "clinic", "medical",
        "apollo", "pharmeasy", "1mg", "checkup", "dentist", "health",
        "lab test", "physio",
    ],
    "education": [
        "course", "udemy", "coursera", "tuition", "fees", "books", "exam",
        "school", "college", "education", "class", "workshop",
    ],
}

# Categories not matched by any keyword fall back to this.
DEFAULT_CATEGORY = "other"

# --------------------------------------------------------------------------
# 2. INCOME KEYWORDS — presence of any of these flips type to "income".
# --------------------------------------------------------------------------
INCOME_KEYWORDS = [
    "salary", "refund", "cashback", "received", "credited", "credit",
    "bonus", "payout", "income", "interest credited", "reimbursement",
    "reimbursed", "got paid", "freelance payment", "dividend", "won",
    "gift received",
]

# --------------------------------------------------------------------------
# 3. FILLER WORDS — stripped out of the message when building the note.
# --------------------------------------------------------------------------
FILLER_WORDS = {
    "spent", "on", "for", "rs", "rs.", "inr", "paid", "pay", "of", "got",
    "received", "the", "a", "an", "at", "via", "through", "today", "just",
    "now",
}

# --------------------------------------------------------------------------
# Amount parsing
# --------------------------------------------------------------------------
# Matches things like: 500   1,250   1.5k   2l   rs 500   ₹500   500rs
_AMOUNT_RE = re.compile(
    r"""
    (?:rs\.?\s*|₹\s*|inr\s*)?          # optional currency prefix
    (\d[\d,]*(?:\.\d+)?)               # the number itself (with optional commas/decimal)
    \s*
    (k|l|lakh|lakhs|lac|cr|crore)?     # optional magnitude suffix — MUST be a whole token
    (?![a-zA-Z])                        # NOT followed by another letter (prevents "lunch"→lakh)
    \s*
    (?:rs\.?|₹|inr)?                   # optional currency suffix
    """,
    re.IGNORECASE | re.VERBOSE,
)

_MAGNITUDE = {
    "k": 1_000,
    "l": 100_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "cr": 10_000_000,
    "crore": 10_000_000,
}


def _find_amount(message: str):
    """Find the first plausible amount in the message.

    Returns (amount: float, span: (start, end)) or (None, None).
    """
    best = None
    for m in _AMOUNT_RE.finditer(message):
        number_str = m.group(1)
        suffix = (m.group(2) or "").lower()

        if not number_str:
            continue

        try:
            value = float(number_str.replace(",", ""))
        except ValueError:
            continue

        if suffix in _MAGNITUDE:
            value *= _MAGNITUDE[suffix]

        # Skip zero-width junk like a lone "." that slipped through
        if value <= 0:
            continue

        # Prefer the first valid match (reads left-to-right like a human would)
        best = (value, m.span())
        break

    if best is None:
        return None, None
    return best


def _detect_category(text_lower: str) -> str:
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return category
    return DEFAULT_CATEGORY


def _detect_type(text_lower: str) -> str:
    for kw in INCOME_KEYWORDS:
        if kw in text_lower:
            return "income"
    return "expense"


def _build_note(message: str, amount_span) -> str:
    """Strip the amount substring and filler words to make a short note."""
    if amount_span:
        start, end = amount_span
        stripped = message[:start] + " " + message[end:]
    else:
        stripped = message

    # Tokenize, drop filler words and pure punctuation
    tokens = re.findall(r"[A-Za-z0-9&]+", stripped)
    kept = [t for t in tokens if t.lower() not in FILLER_WORDS]

    note = " ".join(kept).strip()
    if not note:
        note = message.strip()
    return note.title() if note.islower() else note


def parse(message: str):
    """Parse a free-text message into a transaction dict, or None."""
    if not message or not message.strip():
        return None

    text = message.strip()
    text_lower = text.lower()

    amount, span = _find_amount(text)
    if amount is None:
        return None

    category = _detect_category(text_lower)
    txn_type = _detect_type(text_lower)
    # Income entries don't really need a spending category — keep "other"
    # unless it was matched to "investments" (e.g. "dividend from etf").
    if txn_type == "income" and category not in ("investments",):
        category = "other"

    note = _build_note(text, span)

    return {
        "amount": round(amount, 2),
        "category": category,
        "note": note,
        "type": txn_type,
    }


if __name__ == "__main__":
    # Quick manual smoke test — run `python parser.py`
    samples = [
        "spent 500 on ola",
        "swiggy 420 dinner",
        "1.5k myntra shirt",
        "got salary 75000",
        "rs 1,250 electricity bill",
        "2l invested in fd",
        "₹89 chai",
        "300rs petrol",
        "cashback received 45",
        "gym membership 1999",
        "blinkit 650 groceries",
    ]
    for s in samples:
        print(f"{s!r:40} -> {parse(s)}")
