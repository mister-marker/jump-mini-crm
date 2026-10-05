"""MVP business rules: case-insensitive substring matching, no email filtering."""

SPAM_WORDS = ("spam", "test", "игнор", "ignore", "null", "undefined")


def is_spam(request_text: str | None) -> bool:
    text = (request_text or "").strip().lower()
    return not text or any(word in text for word in SPAM_WORDS)
