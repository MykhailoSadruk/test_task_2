# Payload cache service

A FastAPI microservice that builds payloads from two lists of strings and caches
the work. Each string is passed through a transformer function (a stand-in for an
external service), and the output is the interleaving of the transformed strings
of both lists. Transformed strings and finished payloads are stored in SQLite.

## API

`POST /payload` takes two lists of the same length and returns `201` with the
payload id. A request with lists of different length is rejected with `422`.

Input limits: each list holds at most 10,000 strings and each string at most
1,000 characters. Requests over a limit are rejected with `422`. Empty lists
are accepted.

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
curl http://localhost:8794/docs
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
| `DATABASE_URL` | `sqlite+aiosqlite:///./cache.db` | async SQLAlchemy database URL |

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

- Concurrent identical requests are safe: inserts of existing rows are ignored
  (`ON CONFLICT DO NOTHING`), so a burst of 30 parallel identical requests (300
  strings per list) against SQLite all returned `201` with the same id. Requests
  that race on the same new string may each call the transformer for it, so the
  "transformed at most once" guarantee holds per request, not across requests.
- The transformer is a simulated uppercase function.
- No cache eviction or TTL.
- SQLite file database; PostgreSQL would be used to run several instances.
- Tables are created at startup, without migrations.
- The concurrency limit is per request, not global.
