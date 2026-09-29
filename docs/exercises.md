# Four exercises, three platforms

Work in n8n first, then rebuild the same behavior in Zapier and Make. Use the [API contract](api.md), [samples](../samples), and platform-specific guides. The Python reference demo is an answer key for the service behavior, not a substitute for configuring the platform.

## Connectivity check

Before building a workflow:

1. Start the native API **or** the Compose stack, not both on port 8787.
2. Run `python3 -m redhawk demo` locally. It must pass before you debug a platform.
3. In your platform's HTTP node/module/action, request `GET YOUR_API_BASE/health`. Expect JSON identifying `redhawk-lab`. An HTML page usually indicates a tunnel/login page or a wrong URL.
4. Request `GET YOUR_API_BASE/events/connectivity-test` with `X-Lab-Key`. Expect `ticket: null` and an empty event list. A 401 means the network works but the credentials need fixing.

For native n8n, API base is localhost. In this repo's Compose n8n, it is `http://lab:8787`. For hosted tools, it is your HTTPS tunnel. Keep the CLI's `LAB_BASE_URL` local. If the tunnel URL changes, update all platform API steps. Cloudflare quick tunnels may conflict with an existing `~/.cloudflared/config.yaml`; use your existing named-tunnel setup or consult its official guide rather than modifying unrelated configuration blindly.

## Exercise 1 — transport and mapping

Build just webhook → Normalize. Predict the normalized version of `samples/standard.json`, then send it using `python3 -m redhawk send standard --platform PLATFORM`. Use the event ID in `python3 -m redhawk inspect EVENT_ID` to see a successful normalization event. A full-case `check` should not pass yet: there is no ticket.

Explain: where does the incoming JSON live in the platform? Which fields are strings and which are booleans? What changes when an HTTP step replaces its input with its response?

## Exercise 2 — branches and side effects

Add Classify, complementary review/standard branches, and ticket creation. Run `standard`, `urgent`, and `ambiguous` separately. For each, run the check command printed by `send`.

- Standard: account / normal / standard queue.
- Urgent: incident / high / review queue.
- Ambiguous: unknown / normal / review queue.

Intentionally swap the queue literals and send a fresh case. The checker should fail. Restore the mapping and send a fresh ID; do not mutate an existing idempotent record to conceal the mistake.

Explain why a human-review decision is different from urgency. None of these queue labels sends a message or performs an actual human approval.

## Exercise 3 — invalid input

Run `invalid`. It omits the email. Expect a visible 422 from Normalize and no ticket. Use the checker to confirm the API received and rejected it; a disconnected workflow must not get credit for “creating no ticket.”

Do not add an early platform filter for missing email in this baseline. As a later extension, add an explicit rejection sink and extend the checker so that early validation is observable too.

Explain which errors should be repaired before retrying. How would you distinguish a broken credential from bad customer input?

## Exercise 4 — delivery is not exactly once

Run `retry`. The first ticket write fails with 503; retry the same event ID and body. Depending on platform settings, this is automatic, a manual replay, or completion of an incomplete execution. Check only after it finishes.

Run `duplicate`. The sender delivers the same body twice. Expect exactly one creation and a duplicate response. The API supplies atomic idempotency; the platform supplies routing/retry behavior. Do not claim the platform itself provides exactly-once delivery.

Advanced failure: imagine the server writes successfully but the response is lost. Replay the completed request manually. Why does idempotency still matter even though this lab's injected failure happens before the write?

## Case commands

```sh
python3 -m redhawk sample urgent
python3 -m redhawk send urgent --platform make
# Copy the check command printed by send, including its generated event ID.
python3 -m redhawk inspect YOUR_EVENT_ID
```

`send` generates fresh IDs by default. `--event-id YOUR_ID` lets you deliberately replay an earlier input. The duplicate case sends two deliveries automatically. Use live/published listeners for multi-delivery cases. The CLI never sends `LAB_API_KEY` to platform webhook URLs; that credential belongs on the platform's outbound calls to the practice API.

## Keep a learning log

For each platform, record its version/date, the six case IDs, observed results, a screenshot of the flow with credentials hidden, and one mistake you diagnosed. Compare trigger setup, JSON typing, branch behavior, execution history, and retry controls in your own words. A completed screenshot alone does not establish correct behavior.

## Optional next steps

- Replace the keyword classifier with an LLM while preserving the API response contract. Add evaluation cases for negation, contradictory instructions, malformed output, latency, and cost. Keep the deterministic fixtures as the baseline.
- Add a second business system, such as a local approval log, without sending real customer communications.
- Move normalization into platform-native expressions/Formatter functions; retain explicit error reporting.
- Add scheduled intake and pagination to distinguish polling from webhook triggers.

Reference for the optional tunnel: [Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).
