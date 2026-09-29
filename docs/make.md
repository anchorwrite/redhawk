# Make: build a scenario with explicit routes

Goal: learn bundles, typed mappings, HTTP modules, Router filters, and incomplete executions. Complete the [local demo](../README.md), keep the API running, and expose port 8787 using your HTTPS tunnel.

## 1. Receive a bundle

Create a scenario and add **Webhooks → Custom webhook**. Create a webhook, copy its URL into `MAKE_WEBHOOK_URL` in `.env`, and choose **Run once**.

```sh
python3 -m redhawk send standard --platform make
```

Inspect the captured bundle: `event_id`, `customer_email`, `message`, and `fail_once`. If those fields are missing, redetermine the webhook's data structure while sending another sample. Keep the webhook fields optional in the learned structure so the `invalid` exercise can reach the API's validation rather than being rejected by Make itself.

## 2. Normalize with an HTTP request

Add **HTTP → Make a request**:

- URL: `YOUR_HTTPS_API_BASE/normalize`.
- Method: `POST`.
- Authentication: use an API-key credential if the HTTP app offers one, with header name `X-Lab-Key`; otherwise add that header explicitly. Value: local `LAB_API_KEY`.
- Body content type: `application/json`.
- Body input method: **Data structure**, with `event_id`, `customer_email`, and `message` as Text and `fail_once` as Boolean. Leave fields non-required in the mapper so the missing-email case reaches the API.
- Map each field from the webhook bundle. Do not put quotation marks around a mapped boolean. Let the JSON serializer escape message text.
- Parse response: Yes. Leave non-success HTTP responses treated as errors.

If using an older HTTP module without typed body construction, add **JSON → Create JSON** with this same data structure and map its entire output into the HTTP module's raw JSON body. Do not hand-build JSON around unescaped messages.

Test and inspect the normalized response. Depending on HTTP app version, fields may appear under `Data`; select them from the mapping picker after the first successful run.

## 3. Classify and route

Add a second HTTP module with the same body structure and authentication, URL `/classify`. Map the four fields from Normalize's parsed response.

After Classify, add a **Router** with two routes:

- Review: filter Classify's `needs_review` with Boolean **equal to true**.
- Standard: filter the same field with Boolean **equal to false**.

Make routers can run multiple matching routes; they are not inherently if/else. These complementary filters make the routes mutually exclusive. Do not leave either route unfiltered.

On each route, add an HTTP module that posts to `/tickets`. Create a body structure with:

- `event_id`, `customer_email`, `message`: Text, mapped from Classify.
- `fail_once`: Boolean, mapped from Classify.
- `category`, `priority`: Text, mapped from Classify.
- `queue`: Text, literal `review` or `standard` according to the route.
- `source`: Text, literal `make`.

Use the same API-key/header configuration and response parsing. Expect 201 on the first write. There is no need to merge routes or create a Webhook response module: the CLI checks the API for the eventual result, independently of Make's acknowledgement.

## 4. Run live cases

Save the scenario and enable immediate webhook processing. A one-off listener is fine for capturing a sample; the duplicate exercise needs both requests processed.

Run all six cases with `python3 -m redhawk send CASE --platform make`, then use each printed check command. `standard` should take one route; `urgent` and `ambiguous` should take the other. The ambiguous case is normal priority but still needs review.

## 5. Recover an intentional failure

Enable **Store incomplete executions** in scenario settings. Add a **Retry** error handler to each ticket-writing module. Start with manual completion to inspect the saved failed bundle. Then experiment with bounded automatic retries and an interval your account supports.

Send `retry`: the API returns 503 once, before creating a ticket. Resume/retry the incomplete execution with the same input and event ID. Run the checker again after completion; platform retry intervals may be longer than 30 seconds. Avoid a Skip or Resume handler that simply pretends a ticket was created.

Send `duplicate`: two requests should yield one ticket creation and one successful duplicate response. If both routes accidentally execute, the second route's different queue causes a 409. That conflict is deliberate feedback about the filters, not an error to ignore.

Send `invalid`: Normalize should return 422 and no ticket should exist. Inspect the failure and resolve/discard that test execution as appropriate before proceeding. Do not configure unlimited retries for validation errors.

Done: all six cases pass with source `make`. Export your own scenario blueprint as a learning artifact after removing connections, webhook URLs, keys, and sample payloads that should not be shared. This repository intentionally provides a build guide instead of an untested account-specific blueprint.

Official references, checked September 29, 2026: [Webhooks](https://help.make.com/webhooks), [HTTP app](https://apps.make.com/http), [Retry handler](https://help.make.com/retry-error-handler), [blueprints](https://help.make.com/blueprints). Editor labels and available features can vary by module version and account.
