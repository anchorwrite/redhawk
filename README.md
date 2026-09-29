# Red Hawk automation lab

Learn **n8n, Zapier, and Make** by building the same support-intake workflow in all three:

```text
Webhook → normalize fields → classify request → branch → create a ticket
                                               ├─ review queue
                                               └─ standard queue
```

The repository supplies a real HTTP practice API, SQLite ticket storage, synthetic requests, failure injection, and an outcome checker. You build the orchestration in each platform. Classification is an intentionally simple keyword-based service, **not an LLM**: learn workflow mechanics without buying API credits, then swap in a model as an extension.

## Start here — five-minute local demo

Requires Python 3.11 or newer. No Python packages to install. Run commands from the repository root.

```sh
git clone https://github.com/anchorwrite/redhawk.git
cd redhawk
python3 -m redhawk init
python3 -m redhawk serve
```

In a second terminal, from the same folder:

```sh
python3 -m redhawk demo
```

Six checks should pass: standard, urgent, ambiguous, invalid, retry, and duplicate. This exercises the API using a Python reference solution; it **does not** run n8n, Zapier, or Make. The next task is to reproduce those outcomes in the platforms.

`init` creates a private, ignored `.env` with a random API key. Read that file locally when setting up platform credentials. It also holds webhook URLs, which should remain private. Existing environment variables take precedence over `.env`.

## Choose your first platform

- [n8n lab](docs/n8n.md): included JSON starter workflow, node inspection, expressions, IF branches, retries. Optional local Docker setup below.
- [Zapier lab](docs/zapier.md): build a Zap using Catch Hook, HTTP actions, and Paths. Includes exact field mapping and replay exercises.
- [Make lab](docs/make.md): build a scenario using Custom webhook, HTTP modules, Router filters, and incomplete executions.
- [Four progressive exercises](docs/exercises.md): predict results, run cases, intentionally break mappings, and explain the failures.
- [API contract](docs/api.md): request/response examples and error behavior.

Zapier and Make run in their hosted editors and require accounts. Feature availability, trials, and usage limits depend on your plan; check your account before building multi-step workflows. This kit does not create subscriptions or send emails/messages.

## Optional: n8n and API together in Docker

After `init`, stop the Python server with Ctrl-C so port 8787 is free. Start Docker Desktop, then:

```sh
docker compose up -d --build
```

Open [local n8n](http://localhost:5678), create its local owner account, and follow the [n8n lab](docs/n8n.md). The imported nodes use `http://lab:8787`, which is reachable inside this Compose network. Your terminal still uses `http://127.0.0.1:8787`.

```sh
docker compose down
```

This preserves named volumes. The Compose API database and the native Python database are separate. Keep one running mode throughout an exercise. The n8n `latest` image tag follows upstream's stable releases; record your actual n8n version with your exercise results. See the [official Docker guide](https://github.com/n8n-io/n8n/blob/master/docker/images/n8n/README.md) for pinning a specific version. `N8N_SECURE_COOKIE=false` is for this localhost-only HTTP editor.

## Connect hosted platforms

Zapier, Make, and n8n Cloud cannot reach your laptop's `localhost`. Keep the lab running and expose **only port 8787** through an HTTPS tunnel you control. For example, if Cloudflare's `cloudflared` CLI is already installed:

```sh
cloudflared tunnel --url http://127.0.0.1:8787
```

Use its HTTPS URL as the API base in the platform's HTTP steps. Keep the CLI checker pointed at the local API. The API requires `X-Lab-Key` on every endpoint except `/health`; supply it through the platform's credential mechanism or HTTP header. Stop the tunnel when finished. Use the synthetic samples, not customer data. See [connectivity troubleshooting](docs/exercises.md#connectivity-check).

## Test your workflow

Put the platform webhook URL into the corresponding variable in `.env`, then:

```sh
python3 -m redhawk send urgent --platform n8n
# The command prints a check command containing its unique event_id. Run that command.
```

Replace `n8n` with `zapier` or `make`. Repeat with `standard`, `ambiguous`, `invalid`, `retry`, and `duplicate`. A webhook acknowledgement only means the platform received the request. `check` verifies persisted fields and the event trace. For long platform retry delays, run the check again after replay rather than assuming a 30-second timeout means permanent failure.

## Development and verification

```sh
python3 -m unittest discover -s tests -v
python3 -m redhawk --help
# Optional local helper test (requires Node.js 18+; no npm packages):
node --test tests/zapier-json.test.cjs
```

Tests exercise real HTTP requests, authentication, field validation, routing checks, persistence, temporary failures, concurrent duplicate deliveries, and conflict detection. The n8n JSON also has structural checks. Live platform acceptance is a separate step: importing or configuring the workflow and passing its six checks. No account-level Zapier/Make execution is implied by a passing Python test suite.

Personal learning notes, API keys, webhook URLs, and local databases are excluded from the public repository.
