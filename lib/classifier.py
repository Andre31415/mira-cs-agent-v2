"""Rule-based email intent classifier. No LLM calls — uses keyword matching and regex."""

import re
import logging

logger = logging.getLogger(__name__)

# Category definitions with keyword patterns and regex
CATEGORIES = {
    "return": {
        "keywords": ["return", "refund", "money back", "send back", "cancel",
                     "cancellation", "not working", "doesn't work", "won't work",
                     "disappointed", "not satisfied", "want my money"],
        "patterns": [
            r"\breturn\b", r"\brefund\b", r"\bcancel\b", r"\bmoney\s*back\b",
            r"\bsend\s*(it|them)?\s*back\b", r"\bnot\s+(going\s+to\s+)?work\b",
        ],
        "weight": 10,
    },
    "ring_exchange": {
        "keywords": ["ring size", "exchange ring", "wrong size", "ring exchange",
                     "change ring", "swap ring", "different size", "ring doesn't fit",
                     "ring too big", "ring too small", "resize"],
        "patterns": [
            r"\bring\s+size\b", r"\bexchange\s+(the\s+)?ring\b",
            r"\bwrong\s+size\b", r"\bchange\s+(my\s+)?ring\b",
            r"\bring\s+(doesn't|does\s*n't|does\s+not)\s+fit\b",
            r"\bring\s+too\s+(big|small|large|tight|loose)\b",
        ],
        "weight": 10,
    },
    "missing_ring": {
        "keywords": ["missing ring", "no ring", "didn't receive ring",
                     "where is the ring", "ring not included", "without ring",
                     "ring in the box", "ring wasn't", "ring not in"],
        "patterns": [
            r"\bmissing\s+ring\b", r"\bno\s+ring\b",
            r"\b(didn't|did\s*n't|have\s*n't|haven't)\s+(receive|get|see)\s+(the\s+)?ring\b",
            r"\bwhere\s+(is|are)\s+(the\s+|my\s+)?ring\b",
            r"\bring\s+(wasn't|was\s*n't|not)\s+(in|included)\b",
            r"\breceived\s+.*(?:but|without).*ring\b",
            r"\bring\s+.*not\s+.*(?:ship|box|package)\b",
        ],
        "weight": 10,
    },
    "delivery_status": {
        "keywords": ["where is my order", "delivery status", "shipping status",
                     "tracking", "when will", "shipped yet", "order status",
                     "hasn't arrived", "not received", "when does",
                     "delivery date", "estimated delivery"],
        "patterns": [
            r"\bwhere\s+is\s+(my\s+)?order\b",
            r"\b(delivery|shipping|order)\s+status\b",
            r"\btrack(ing)?\b",
            r"\bwhen\s+will\s+(it|my|the)\b",
            r"\bhasn't\s+arrived\b",
            r"\bnot\s+(yet\s+)?received\b",
            r"\bshipped\s+yet\b",
        ],
        "weight": 8,
    },
    "prescription": {
        "keywords": ["prescription", "lenses", "rx", "glasses prescription",
                     "prescription order", "prescription lenses",
                     "submit prescription", "prescription status"],
        "patterns": [
            r"\bprescription\b",
            r"\blenses?\b",
            r"\brx\b",
            r"\bsubmit\s+(my\s+)?prescription\b",
        ],
        "weight": 6,
    },
    "general": {
        "keywords": [],
        "patterns": [],
        "weight": 0,
    },
}

# Patterns that indicate spam/marketing (not real CS emails)
SPAM_PATTERNS = [
    r"\bUGC\b", r"\binfluencer\b", r"\bcollab(oration)?\b",
    r"\bpartnership\b", r"\bsponsored\b", r"\baffiliate\b",
    r"\bbrand\s+ambassador\b", r"\bcontent\s+creator\b",
    r"\bportfolio\b.*\btiktok\b",
]

# Patterns indicating the customer is happy / no action needed
POSITIVE_PATTERNS = [
    r"\b(love|loving|great|awesome|amazing|cool|fantastic)\b.*\b(glasses|product|mira)\b",
    r"\b(glasses|product|mira)\b.*\b(love|great|awesome|amazing|cool|fantastic)\b",
    r"\bthank(s| you)\b.*\b(so much|a lot)\b",
    r"\bno worries\b",
]


def classify_email(subject: str, body: str, thread_context: list[dict] | None = None) -> dict:
    """
    Classify an email's intent based on subject + body text.

    Returns:
        dict with 'category', 'confidence', 'matched_rules'
    """
    text = f"{subject} {body}".lower()

    # Check for spam/marketing first
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return {
                "category": "spam",
                "confidence": 0.9,
                "matched_rules": ["spam_filter"],
            }

    # Score each category
    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}

    for category, config in CATEGORIES.items():
        if category == "general":
            continue
        score = 0.0
        matches = []

        # Keyword matching
        for kw in config["keywords"]:
            if kw.lower() in text:
                score += 2.0
                matches.append(f"keyword:{kw}")

        # Regex pattern matching
        for pattern in config["patterns"]:
            if re.search(pattern, text, re.IGNORECASE):
                score += 3.0
                matches.append(f"pattern:{pattern}")

        # Subject line boost
        subject_lower = subject.lower()
        for kw in config["keywords"]:
            if kw.lower() in subject_lower:
                score += 2.0

        if score > 0:
            scores[category] = score
            matched[category] = matches

    if not scores:
        # Check for positive/happy responses
        for pattern in POSITIVE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return {
                    "category": "positive_feedback",
                    "confidence": 0.7,
                    "matched_rules": ["positive_feedback"],
                }
        return {
            "category": "general",
            "confidence": 0.5,
            "matched_rules": [],
        }

    # Pick highest scoring category
    best_category = max(scores, key=scores.get)
    best_score = scores[best_category]

    # Confidence = normalized score (capped at 1.0)
    confidence = min(best_score / 15.0, 1.0)

    return {
        "category": best_category,
        "confidence": confidence,
        "matched_rules": matched.get(best_category, []),
    }


def is_inbound_customer_email(email: dict) -> bool:
    """Check if an email is an inbound customer email (not from team@trymira.com)."""
    from_email = ""
    # Handle multiple possible field names: from_, from, from_email, sender
    for key in ["from_", "from", "from_email", "sender"]:
        val = email.get(key, "")
        if isinstance(val, str) and val:
            from_email = val.lower()
            break

    # Skip outbound emails
    if "team@trymira.com" in from_email or "team@halo.so" in from_email:
        return False

    # Skip system/notification emails
    skip_domains = ["shopify.com", "noreply", "no-reply", "mailer-daemon",
                    "postmaster", "auto-reply"]
    for domain in skip_domains:
        if domain in from_email:
            return False

    return True


def extract_email_fields(email: dict) -> dict:
    """Extract standard fields from various email formats."""
    # Handle different email response formats (note: connector uses 'from_' with underscore)
    from_raw = email.get("from_", email.get("from", email.get("sender", "")))
    from_email = ""
    from_name = ""

    if isinstance(from_raw, str):
        # Parse "Name <email>" format
        match = re.match(r'^(.*?)\s*<(.+?)>\s*$', from_raw)
        if match:
            from_name = match.group(1).strip().strip('"')
            from_email = match.group(2).strip()
        elif "@" in from_raw:
            from_email = from_raw.strip()
            from_name = from_raw.split("@")[0]
    elif isinstance(from_raw, dict):
        from_email = from_raw.get("email", "")
        from_name = from_raw.get("name", "")

    subject = email.get("subject", "")
    body = email.get("body", email.get("snippet", email.get("text", "")))
    message_id = email.get("email_id", email.get("id", email.get("message_id", "")))
    thread_id = email.get("thread_id", email.get("threadId", ""))
    received_at = email.get("date", email.get("received_at", email.get("internalDate", "")))
    labels = email.get("labels", email.get("labelIds", []))

    return {
        "from_email": from_email,
        "from_name": from_name,
        "subject": subject,
        "body": body,
        "message_id": message_id,
        "thread_id": thread_id,
        "received_at": received_at,
        "labels": labels,
    }


def extract_order_number(text: str) -> str | None:
    """Try to extract an order number from text."""
    patterns = [
        r'#(\d{3,5})',
        r'order\s*#?\s*(\d{3,5})',
        r'order\s+number\s*:?\s*#?(\d{3,5})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None
