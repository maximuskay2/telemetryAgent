# Telemetry Agent

Telemetry Agent is a small observability workbench for streaming application and
device logs, inspecting them in real time, and requesting a structured diagnosis.
The local setup runs without external credentials; Fireworks and Modal
integrations are opt-in.

## Architecture

```text
Log source ──POST /api/logs──▶ FastAPI ingestion API ──WebSocket──▶ Next.js terminal
                                      │
                                      ├──▶ structured diagnosis (Fireworks, optional)
                                      └──▶ isolated runner (Modal, optional)
```

`core/schemas` contains the API event and diagnosis models. `core/infer` holds
the Fireworks-compatible inference client, and `core/sandbox` contains the
optional Modal execution adapter. The API runs locally at `http://localhost:8000`
and the UI at `http://localhost:3000`.

## Requirements

- Python 3.9+
- Node.js 20.9+
- npm

## Run locally

Install Python dependencies and start the API from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn apps.api.main:app --reload
```

In another terminal, install and start the UI:

```bash
npm install
npm run dev
```

Open `http://localhost:3000`. The UI connects to the API WebSocket and displays
events as they arrive. Submit a log line to the API with:

```bash
curl -X POST http://localhost:8000/api/logs \
  -H 'Content-Type: application/json' \
  -d '{"message":"database connection timed out","source":"demo"}'
```

Request a structured diagnosis for a log excerpt with:

```bash
curl -X POST http://localhost:8000/api/diagnose \
  -H 'Content-Type: application/json' \
  -d '{"log_text":"database deadlock detected; transaction rolled back"}'
```

The interactive API documentation is at `http://localhost:8000/docs`.

## Optional integrations

Set `FIREWORKS_API_KEY` to enable remote diagnosis via Fireworks. The optional
`FIREWORKS_MODEL` setting defaults to `accounts/fireworks/models/llama-v3p1-8b-instruct`.
Without a key, diagnosis returns a local, clearly labeled baseline result.

The Modal runner is opt-in. Install the `modal` extra (`pip install -e '.[modal]'`)
and configure Modal credentials before using it. Do not submit untrusted
commands or sensitive log content to remote services.

## Sample logs

The `mocks/` directory includes a database deadlock sample and a UART serial
fault sample. They can be posted as individual log messages to exercise the UI.

## Tests

```bash
python -m unittest discover -s tests
```

## License

MIT; see [LICENSE](./LICENSE).
