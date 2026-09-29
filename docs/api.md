# Practice API contract

Native base URL: `http://127.0.0.1:8787`. Within the supplied Compose network: `http://lab:8787`. Hosted platforms use your HTTPS tunnel URL.

Every route except `GET /health` requires header `X-Lab-Key: <your local LAB_API_KEY>`. POST requests must use `Content-Type: application/json` and a JSON object, at most 64 KiB. This is a learning server using Python's standard HTTP server, not a production deployment template.

## POST /normalize

Input:

```json
{
  "event_id": "lesson-001",
  "customer_email": "  ALEX@example.test  ",
  "message": "  Please reset my password.  ",
  "fail_once": false
}
```

Response, HTTP 200:

```json
{
  "event_id": "lesson-001",
  "customer_email": "alex@example.test",
  "message": "Please reset my password.",
  "fail_once": false
}
```

Email, message, and event ID are required strings. Event IDs allow letters, digits, hyphens, and underscores, at most 100 characters. Emails have a basic shape check, at most 254 characters; this does not verify deliverability. Messages are at most 4,000 characters. `fail_once` is an optional JSON boolean, default false. `"false"` is a string and is rejected. Unknown fields are dropped. Normalization is idempotent: doing it twice produces the same result.

## POST /classify

Input: the normalized object above. The service revalidates it and returns those fields plus:

```json
{
  "category": "account",
  "priority": "normal",
  "needs_review": false
}
```

This is a deterministic, deliberately limited **keyword classifier**. It checks whole words in this order:

1. `outage`, `urgent`, or `down`: incident, high priority, needs review.
2. `refund`, `invoice`, or `billing`: billing, normal priority, needs review.
3. `password`, `login`, or `account`: account, normal priority, no review.
4. Otherwise: unknown, normal priority, needs review.

It cannot understand negation or nuance. For example, “not urgent” still matches urgent. That limitation is an explicit later exercise, not a claim of intelligent classification.

## POST /tickets

Send the normalized fields, classification, and your platform's routing decision:

```json
{
  "event_id": "lesson-001",
  "customer_email": "alex@example.test",
  "message": "Please reset my password.",
  "fail_once": false,
  "category": "account",
  "priority": "normal",
  "queue": "standard",
  "source": "n8n"
}
```

Allowed queues: `standard`, `review`. Allowed sources: `n8n`, `zapier`, `make`, `reference`. `needs_review` is not stored; the platform uses it to choose `queue`. The server validates allowed values but **does not correct wrong routing or classification**. This lets the checker detect mistakes.

- First write: **201**, `{"duplicate": false, "ticket": {...}}`.
- Identical repeated write: **200**, `{"duplicate": true, "ticket": {...}}`.
- Same event ID with different stored fields: **409**, `{"error": "..."}`. This includes a changed queue, source, message, or `fail_once` value.
- With `fail_once: true`: the first otherwise-valid write returns **503** and `Retry-After: 1`, without creating a ticket. A subsequent unchanged request succeeds. The failure marker survives server restarts. It is per event ID, not per workflow or source.

Keep event IDs stable across retries and repeated deliveries. Generate a new ID for a new experiment, particularly when changing mappings or comparing platforms. Exact duplicate detection operates on the normalized stored fields.

## GET /events/EVENT_ID

Returns `{"ticket": null, "events": []}` for an unseen ID. Once requests arrive, `events` contains ordered entries with operation, status, description, and timestamp. This is how `check` proves that an error was actually handled or a ticket was actually created. Event traces grow with use; start a new native database using `serve --db .lab/another-session.sqlite3` when you want a clean session.

## Error interpretation

- **400**: malformed JSON/request framing; fix the request.
- **401**: missing or incorrect API key; fix credentials.
- **404**: wrong API path; check the URL.
- **409**: reused event ID with different data; inspect what changed.
- **413**: empty or oversized body.
- **415**: wrong Content-Type.
- **422**: invalid fields; fix the mappings/input.
- **503**: intentional transient failure in the retry case; retry unchanged input with a bounded policy.

Only 503 is injected here. A real integration might also retry 429 using its Retry-After guidance. Retrying invalid data indefinitely does not repair it.
