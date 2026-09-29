# Zapier: build a Zap with the same contract

Goal: learn triggers, field mapping, Code steps, webhook actions, Paths, and replay. Complete the [local demo](../README.md), keep the API running, and establish an HTTPS tunnel to port 8787. Your account must support the multi-step Zap, Paths, and webhook actions used here; check availability in the editor before starting. No paid account is configured by this repository.

## 1. Capture a sample

Create a Zap. Choose **Webhooks by Zapier → Catch Hook** as the trigger. Leave “Pick Off A Child Key” empty: the payload is a flat object. Copy the hook URL to `ZAPIER_WEBHOOK_URL` in `.env`.

```sh
python3 -m redhawk send standard --platform zapier
```

Test the trigger and select this sample. Capture means Zapier received it, not that your unfinished workflow has produced a ticket.

## 2. Serialize safely, then normalize

Add **Code by Zapier → Run JavaScript**. Paste [zapier-json.js](../snippets/zapier-json.js). In **Input Data**, create four keys and map their values from the trigger: `event_id`, `customer_email`, `message`, and `fail_once`. Key spelling matters. Leave `queue`, `category`, and `priority` out for now.

The code returns a `body` string containing valid JSON, including a real boolean. It escapes quotation marks and newlines in messages. The helper is part of the exercise: a JSON string is not the same thing as an object or a string containing `"false"`.

Add **Webhooks by Zapier → Custom Request**:

- Method: `POST`.
- URL: `YOUR_HTTPS_API_BASE/normalize`.
- Data: map the **entire `body` output** from the Code step. Do not put quotes around that mapping, add a `body` wrapper, or type JSON with interpolated message strings.
- Headers: `Content-Type` = `application/json`; `X-Lab-Key` = your local API key.
- Disable any array wrapping/unflatten behavior if offered; send the exact raw JSON body. Keep ordinary non-2xx failure behavior.

Test. Inspect the parsed response: email should be `alex@example.test`, and the message should have no leading/trailing spaces. Header values in webhook actions may be visible in the step configuration: keep the key out of screenshots and shared exports. For a connection-managed credential, explore API by Zapier after the baseline works.

## 3. Classify the normalized fields

Add another Code step with the same helper. Map the four fields **from Normalize's response**, not from the original trigger. Follow it with another Custom Request configured exactly as above, but URL `/classify` and Data from this new Code step.

The response includes `category`, `priority`, and boolean `needs_review`. If fields do not appear in the mapping picker, test the HTTP step with the standard sample first.

## 4. Branch and create

Add **Paths by Zapier** with mutually exclusive rules using Classify's output:

- Review path: `needs_review` is true.
- Standard path: `needs_review` is false.

Use the boolean comparison offered by the editor. If it presents the value as text, compare exactly to the value shown in your tested response, not “exists”—false is still a present value.

Inside **each path**, add a Code step using the helper again. Map `event_id`, `customer_email`, `message`, `fail_once`, `category`, and `priority` from Classify. Set Input Data `queue` to the literal `review` or `standard` for that path. The helper now includes those fields and the literal source `zapier`.

Follow each Code step with a Custom Request to `/tickets`. Same headers and raw-body mapping. Expect HTTP 201 and `duplicate: false` on a fresh sample. All processing stays inside the selected path; no shared action after Paths is required.

## 5. Publish and check

Publish/enable the Zap. Send fresh cases with the CLI rather than relying only on editor tests; editor tests can reuse old sample IDs. Run the printed check for each:

```sh
python3 -m redhawk send urgent --platform zapier
python3 -m redhawk send ambiguous --platform zapier
python3 -m redhawk send invalid --platform zapier
python3 -m redhawk send retry --platform zapier
python3 -m redhawk send duplicate --platform zapier
```

For `retry`, inspect the failed ticket step in Zap History and replay the failed run when your plan allows. Automatic replay, if available, may take longer than the checker's 30-second wait. The saved fields and event ID must stay unchanged. Check again afterward. Avoid manually substituting a new event ID: that would trigger a new one-time failure.

For `invalid`, the normalizer must visibly reject the request with 422. Do not filter it out before Normalize in this baseline, since the checker needs an observed rejection. For `duplicate`, use the live hook; both deliveries should reach `/tickets`. If only one does, inspect history for trigger deduplication or a paused run—the checker intentionally distinguishes platform receipt from destination behavior.

Done: all six cases pass with source `zapier`. As a stretch exercise, replace the normalization service with Formatter/Code steps, then adapt your validation trace rather than assuming the original invalid-input check still applies.

Official references, checked September 29, 2026: [Catch Hook](https://help.zapier.com/hc/en-us/articles/8496288690317-Trigger-Zap-workflows-from-webhooks), [Custom Request](https://help.zapier.com/hc/en-us/articles/8496326446989-Send-webhooks-in-Zap-workflows), [API request options](https://help.zapier.com/hc/en-us/articles/44391646192397-Ways-to-make-API-requests-in-Zapier), [replay runs](https://help.zapier.com/hc/en-us/articles/8496241726989-Replay-Zap-runs). This is a manual build guide with executable helper code, not a Zapier-importable JSON export.
