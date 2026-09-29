"""Expected outcomes are explicit fixtures, independent of the classifier implementation."""

CASES = {
    "standard": {
        "input": {"customer_email": "  ALEX@example.test  ", "message": "  Please reset my password.  ", "fail_once": False},
        "expected": {"customer_email": "alex@example.test", "message": "Please reset my password.", "category": "account", "priority": "normal", "queue": "standard"},
    },
    "urgent": {
        "input": {"customer_email": "sam@example.test", "message": "Urgent: our checkout is down.", "fail_once": False},
        "expected": {"customer_email": "sam@example.test", "message": "Urgent: our checkout is down.", "category": "incident", "priority": "high", "queue": "review"},
    },
    "ambiguous": {
        "input": {"customer_email": "lee@example.test", "message": "Something seems odd.", "fail_once": False},
        "expected": {"customer_email": "lee@example.test", "message": "Something seems odd.", "category": "unknown", "priority": "normal", "queue": "review"},
    },
    "invalid": {"input": {"message": "Missing email must be rejected.", "fail_once": False}, "expected": None},
}
CASES["retry"] = {"input": {**CASES["standard"]["input"], "fail_once": True}, "expected": CASES["standard"]["expected"]}
CASES["duplicate"] = {"input": dict(CASES["standard"]["input"]), "expected": CASES["standard"]["expected"]}


def assess(snapshot, case, source):
    """Return failures; an empty list is success. A webhook ACK alone never passes."""
    ticket, events = snapshot["ticket"], snapshot["events"]
    expected = CASES[case]["expected"]
    if expected is None:
        failures = ["Invalid input created a ticket"] if ticket else []
        if not any(e["operation"] == "normalize" and e["status"] == 422 for e in events):
            failures.append("No observed normalization rejection yet (missing delivery is not a pass)")
        return failures
    if not ticket:
        return ["No ticket yet; check workflow execution history and API connection"]
    expected = {**expected, "source": source, "fail_once": CASES[case]["input"]["fail_once"]}
    failures = [f"{key}: expected {value!r}, got {ticket.get(key)!r}"
                for key, value in expected.items() if ticket.get(key) != value]
    writes = [e for e in events if e["operation"] == "tickets"]
    if sum(e["status"] == 201 for e in writes) != 1:
        failures.append("Expected exactly one ticket creation")
    if case == "duplicate" and not any(e["status"] == 200 for e in writes):
        failures.append("Second delivery has not returned the existing ticket yet")
    if case == "retry" and not any(e["status"] == 503 for e in writes):
        failures.append("One-time failure was not exercised; check fail_once mapping")
    return failures
