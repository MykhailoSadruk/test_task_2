# Payload cache service

A FastAPI microservice that builds payloads from two lists of strings and caches
the work. Each string is passed through a transformer function (a stand-in for an
external service), and the output is the interleaving of the transformed strings
of both lists. Transformed strings and finished payloads are stored in SQLite.

## API

`POST /payload` takes two lists of the same length and returns `201` with the
payload id. A request with lists of different length is rejected with `422`.

```bash
curl -X POST http://localhost:8000/payload \
  -H "Content-Type: application/json" \
  -d '{"list_1": ["first string", "second string", "third string"],
       "list_2": ["other string", "another string", "last string"]}'
```

```json
{"id": "db1643219a6c379b295897e1daa542e2a58690ab61fa70c673de661c46068a2f", "message": "Payload db1643219a6c379b295897e1daa542e2a58690ab61fa70c673de661c46068a2f is ready"}
```

`GET /payload/{id}` returns the generated payload, or `404` for an unknown id.

```bash
curl http://localhost:8000/payload/db1643219a6c379b295897e1daa542e2a58690ab61fa70c673de661c46068a2f
```

```json
{"output": "FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING, THIRD STRING, LAST STRING"}
```

Interactive docs are served at `http://localhost:8000/docs`.

## Run locally

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install .
uvicorn app.main:app --port 8000
```

## Run with Docker

```bash
docker build -t payload-cache .
docker run -p 8000:8000 -v payload-cache-data:/data payload-cache
```

Or with Compose, which creates the named volume for you:

```bash
docker compose up --build
```

The database lives in the `/data` volume, so the cache survives container
restarts and re-creation as long as the same volume is mounted. The container
runs as a non-root user.

## CLI

`pip install .` registers the `cache-cli` command.

```bash
cache-cli -j '{"list_1": ["a", "b"], "list_2": ["c", "d"]}'
cache-cli -H http://localhost:8000 -r 3 -i payload.json -o result.txt
cat payload.json | cache-cli -i -
```

| Option | Meaning |
| --- | --- |
| `-H`, `--host URL` | server URL, default `http://localhost:8000` |
| `-r`, `--repeat N` | number of iterations, default `1` |
| `-i`, `--input FILE` | JSON input file, `-` for stdin |
| `-j`, `--json JSON` | inline JSON input |
| `-o`, `--output FILE` | output file, `-` for stdout (default) |
| `-h`, `--help` | show help |

Exactly one of `--input` and `--json` is required. Each iteration creates the
payload, reads it back, and writes the `{"output": ...}` JSON as one line.

The assignment lists `-h` for both host and help. The two cannot share a flag, so
`-h` is help and the host short flag is `-H`; `--host` works as specified.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite+aiosqlite:///./cache.db` | async SQLAlchemy database URL |

The Docker image sets it to `sqlite+aiosqlite:////data/cache.db`.

## Development

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install
pytest
black .
flake8 .
mypy .
```

`pre-commit run --all-files` runs black, flake8, mypy, and basic file checks.

## Design decisions

- **Deterministic payload id.** The id is the sha256 of the canonical JSON of both
  lists, so the same input always maps to the same id and a repeated request is
  answered from the stored payload.
- **Cache per string.** Transformed strings are cached individually, so a string
  shared between payloads is never transformed again.
- **Minimal transformer calls.** Only unique strings that are not yet cached are
  transformed, concurrently with `asyncio.gather`, limited by a semaphore of 10
  per request.
- **Async SQLAlchemy.** The service uses `AsyncSession` with aiosqlite so
  requests do not block the event loop.

## Known shortcuts

- No locking: two simultaneous requests with the same new strings or the same new
  payload can race on inserting the same row. In a test burst of 30 parallel
  identical requests (300 strings per list) against the Docker container, 14
  returned `500` with a `UNIQUE constraint failed` error and 16 returned `201`.
- The transformer is a simulated uppercase function.
- No cache eviction or TTL.
- SQLite file database; PostgreSQL would be used to run several instances.
- Tables are created at startup, without migrations.
- The concurrency limit is per request, not global.
