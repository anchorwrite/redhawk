"""Small, deliberately deterministic stand-ins for business services, not AI."""

import re


class LabError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def text(data, field, limit=4000):
    value = data.get(field)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise LabError(422, f"{field} must be nonempty text, at most {limit} characters")
    return value.strip()


def normalize(data):
    event_id = text(data, "event_id", 100)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", event_id):
        raise LabError(422, "event_id must contain only letters, digits, underscores, or hyphens")
    email = text(data, "customer_email", 254).lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise LabError(422, "customer_email must look like an email address")
    fail_once = data.get("fail_once", False)
    if not isinstance(fail_once, bool):
        raise LabError(422, "fail_once must be a JSON boolean, not text")
    return {
        "event_id": event_id,
        "customer_email": email,
        "message": text(data, "message"),
        "fail_once": fail_once,
    }


def classify(data):
    result = normalize(data)
    message = result["message"].lower()
    if re.search(r"\b(outage|urgent|down)\b", message):
        category, priority, review = "incident", "high", True
    elif re.search(r"\b(refund|invoice|billing)\b", message):
        category, priority, review = "billing", "normal", True
    elif re.search(r"\b(password|login|account)\b", message):
        category, priority, review = "account", "normal", False
    else:
        category, priority, review = "unknown", "normal", True
    return {**result, "category": category, "priority": priority, "needs_review": review}


def ticket_payload(data):
    result = normalize(data)
    for field, choices in {
        "category": {"incident", "billing", "account", "unknown"},
        "priority": {"high", "normal"},
        "queue": {"review", "standard"},
        "source": {"n8n", "zapier", "make", "reference"},
    }.items():
        value = data.get(field)
        if not isinstance(value, str) or value not in choices:
            raise LabError(422, f"{field} must be one of: {', '.join(sorted(choices))}")
        result[field] = value
    # Do not correct routing here: the checker must catch incorrect platform mappings.
    return result
