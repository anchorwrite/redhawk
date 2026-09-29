# n8n: inspect an existing workflow, then rebuild it

Goal: understand nodes, expressions, credentials, branching, test versus production webhooks, and retries. First complete the [local demo](../README.md#start-here--five-minute-local-demo).

Validated September 29, 2026: the starter imported into n8n 2.41.3 and passed all six cases through its live production webhook under the supplied 1 GiB container cap. Credentials were attached locally; the public JSON still contains none. Your own import requires the connection steps below.

## 1. Import and connect

1. Start the optional Docker Compose stack, or use your existing n8n installation.
2. Create a workflow and use the editor's **Import from file** command to load [support-intake.json](../workflows/n8n/support-intake.json). It is inactive and contains no credentials.
3. Create a **Header Auth** credential: header name `X-Lab-Key`, value equal to `LAB_API_KEY` from your local `.env`.
4. Select that credential on **Normalize**, **Classify**, **Review ticket**, and **Standard ticket**. The workflow requests Generic Credential Type → Header Auth.
5. Inspect all four HTTP URLs. The default `http://lab:8787` works with this repo's Compose stack. For n8n running natively beside the Python server, use `http://127.0.0.1:8787`. For n8n Cloud, use your HTTPS tunnel URL. A Docker installation outside this Compose stack requires its own host networking configuration.

Each HTTP node sends JSON and returns the parsed response body. Leave HTTP errors enabled; do not turn on “Never Error.”

## 2. Follow one item

Open **Support request**, choose **Listen for test event**, and copy its Test URL into `N8N_WEBHOOK_URL` in `.env`. Then run:

```sh
python3 -m redhawk send standard --platform n8n
```

Inspect each node's input and output:

- Webhook: the JSON payload is inside `body`.
- Normalize: request body expression `={{ $json.body }}` selects it; the API trims the email/message and lowercases the email.
- Classify: `={{ $json }}` passes the normalized object to the classifier. Its response adds `category`, `priority`, and boolean `needs_review`.
- Needs review?: boolean **is true** routes the current item. True goes to Review ticket; false to Standard ticket.
- Ticket nodes: an object expression copies the classification fields and adds literal `queue` and `source`. The API deliberately does not fix the queue if you wire it incorrectly.

The JSON export stores expression strings with a leading `=`. When entering expressions in the editor, use its expression mode; it may display only the `{{ ... }}` portion.

Run the check command printed by `send`. Expect a standard-queue ticket, normalized email, and source `n8n`. The webhook replies immediately; the checker reads the eventual result separately.

## 3. Turn on both branches

Publish/activate the workflow and replace `N8N_WEBHOOK_URL` with its **Production URL**. Test listeners are temporary and unsuitable for the two-delivery duplicate exercise.

Run `urgent` and `ambiguous`; both go to review, but only urgent has high priority. This demonstrates why branching on `priority == high` is not equivalent to branching on `needs_review`.

Run `invalid`; Normalize should fail with 422 and no ticket should exist. Run the printed check to confirm the rejection reached the API.

## 4. Retry and deduplicate

Both ticket nodes have **Retry On Fail**, three total attempts, and a one-second delay. Send `retry`. The trace must show 503 followed by 201 using the same event ID. Send `duplicate`: it sends the exact same event twice. The trace must show one 201 and at least one 200 returning the same ticket.

The starter retries any error, including permanent errors. As an advanced exercise, replace blanket retries with explicit handling that retries only 429/503, caps attempts, and leaves 401/409/422 visible. Do not turn errors into success just to get a green execution.

For a public n8n webhook, configure Header Auth on the trigger too. Use a separate ingress credential with header `X-Lab-Key` and place its value in `N8N_WEBHOOK_KEY`; the CLI supports it. Do not reuse the API key. The local starter has no trigger authentication and binds the editor to localhost through Compose.

## 5. Rebuild without importing

Create a second workflow with a different webhook path. Rebuild the six nodes from the API contract. Pass all six cases. Explain why there are two outgoing IF connections, why body mapping changes after the Webhook node, and why a duplicate delivery is a success rather than an error.

Official references, checked September 29, 2026: [HTTP Request](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/), [Webhook](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/), [first workflow](https://docs.n8n.io/build-your-first-workflow.md). The starter's node versions are Webhook 2, HTTP Request 4.2, and IF 2.2; JSON structural validation is not a substitute for testing an import in your n8n version.
