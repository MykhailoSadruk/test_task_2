# Payload cache service

A FastAPI microservice that builds payloads from two lists of strings and caches
the work. Each string is passed through a transformer function (a stand-in for an
external service), and the output is the interleaving of the transformed strings
of both lists. Transformed strings and finished payloads are stored in SQLite.

## API

`POST /payload` takes two lists of the same length and returns `201` with the
payload id, or `200` with the same id when that payload already exists. A request
with lists of different length is rejected with `422`.

By default the input has no size limit. `MAX_LIST_ITEMS` limits the number of items
per list and `MAX_BODY_SIZE` limits the request body in bytes (see Configuration);
a request over either limit is rejected with `413`. Empty lists are accepted.

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

`GET /health` returns `{"status": "ok"}` after a test query to the database, or `503`
when the database cannot be reached. The Docker healthcheck uses it.

## Run locally

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install .
cp .env.example .env             # optional, see Configuration
python -m app
```

`python -m app` starts the server on `APP_HOST:APP_PORT` (default
`127.0.0.1:8000`). Plain `uvicorn app.main:get_app --factory` also works but
ignores `APP_HOST` and `APP_PORT`.

## Run with Docker

```bash
docker build -t payload-cache .
docker run -p 8000:8000 -v payload-cache-data:/data payload-cache
```

The image listens on `APP_PORT` (default `8000`). To use another port, pass it
to the container and publish the same port:

```bash
docker run -e APP_PORT=8794 -p 8794:8794 -v payload-cache-data:/data payload-cache
```

Or with Compose, which creates the named volume for you:

```bash
docker compose up --build
```

Compose reads `APP_PORT` from the shell or from a `.env` file next to
`docker-compose.yml` and publishes that port, for example:

```bash
echo "APP_PORT=8794" > .env
docker compose up --build
curl http://localhost:8794/health
```

Compose passes only `APP_PORT` to the container; `DATABASE_URL` from `.env` is
not used there, so the database always stays in the `/data` volume.

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
| `-t`, `--timeout SECONDS` | request timeout, default `600` |
| `-o`, `--output FILE` | output file, `-` for stdout (default) |
| `-h`, `--help` | show help |

Exactly one of `--input` and `--json` is required. Each iteration creates the
payload, reads it back, and writes the `{"output": ...}` JSON as one line.

The assignment lists `-h` for both host and help. The two cannot share a flag, so
`-h` is help and the host short flag is `-H`; `--host` works as specified.

## Configuration

Settings are read from environment variables and from a `.env` file in the
working directory. Real environment variables take precedence over `.env`, and
unknown keys in `.env` are ignored.

| Variable | Default | Meaning |
| --- | --- | --- |
| `APP_HOST` | `127.0.0.1` | interface the server binds to |
| `APP_PORT` | `8000` | server port, 1-65535 |
| `DATABASE_URL` | `sqlite+aiosqlite:///./cache.db` | async SQLite URL; any other database is rejected at startup |
| `MAX_LIST_ITEMS` | unlimited | maximum items per list, `413` above it |
| `MAX_BODY_SIZE` | unlimited | maximum request body in bytes, `413` above it |
| `MAX_TRANSFORMER_CALLS` | `50` | transformer calls allowed at the same time across all requests |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |

```bash
cp .env.example .env
python -m app
```

`.env` is git-ignored; `.env.example` is committed. The Docker image sets
`APP_HOST=0.0.0.0`, `APP_PORT=8000` and
`DATABASE_URL=sqlite+aiosqlite:////data/cache.db`.

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

## Large payloads

Without limits, a request with 1,000,000 pairs (2,000,000 strings, about 490,000
distinct) works. Measured on one Windows machine with the server and SQLite on a
local disk, a 30 MB request body, sent with `cache-cli`:

| Scenario | Time |
| --- | --- |
| 1,000,000 pairs, empty cache | about 15-18 s (three runs) |
| the same request again | about 1.6-1.9 s |

The output has 2,000,000 words and was checked word by word against the uppercase
input. Memory grows with the request size because the body, the output and the
unique strings are held in memory, so the practical limit is the available RAM
and the client timeout (`--timeout`). The numbers will differ on other machines.
Set `MAX_LIST_ITEMS` or `MAX_BODY_SIZE` to cap the request size on a shared server.

## Design decisions

- **Deterministic payload id.** The id is the sha256 of the canonical JSON of both
  lists, so the same input always maps to the same id and a repeated request is
  answered from the stored payload.
- **Cache per string.** Transformed strings are cached individually, so a string
  shared between payloads is never transformed again.
- **Minimal transformer calls.** Only unique strings that are not yet cached are
  transformed, by 10 workers per request that take strings from a shared queue,
  so memory does not grow with the number of strings. All requests together make
  at most `MAX_TRANSFORMER_CALLS` (default 50) transformer calls at the same time.
- **Async SQLAlchemy.** The service uses `AsyncSession` with aiosqlite so
  requests do not block the event loop.

## Logging

The service logs with the standard `logging` module. At `INFO` it reports, per
request, whether the payload already existed and how many strings were cache hits
and how many had to be transformed. Failed transformer attempts are logged as
warnings, and giving up on a string as an error. `DEBUG` adds one line for every
transformer call, every shared call and every batch saved, which is a lot of
output for large requests.

## Known shortcuts

- Concurrent identical requests are safe: inserts of existing rows are ignored
  (`ON CONFLICT DO NOTHING`), so a burst of 30 parallel identical requests (300
  strings per list) against SQLite all returned a success status with the same id.
- Requests that need the same new string while a call for it is running share that
  call (single-flight), so the same string is never transformed twice at the same
  time. A request that reads the cache before another request has saved its result
  can still repeat a call that already finished, so this reduces duplicate calls
  but does not rule them out. It works inside one server process only. If the call
  that others wait for is cancelled, the waiters count it as a failed attempt and
  retry.
- The transformer is a simulated uppercase function.
- No cache eviction or TTL.
- SQLite only: inserts use SQLite's `ON CONFLICT DO NOTHING`, so `DATABASE_URL` must
  start with `sqlite+aiosqlite:` and the app refuses to start with another URL. Another
  database would need its own insert statement.
- Tables are created at startup, without migrations.
