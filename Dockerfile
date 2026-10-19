FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    DATABASE_URL=sqlite+aiosqlite:////data/cache.db

RUN useradd --create-home --uid 1000 appuser \
    && mkdir /data \
    && chown appuser:appuser /data

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY cli ./cli
RUN pip install --no-cache-dir .

USER appuser
VOLUME /data
EXPOSE ${APP_PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.environ['APP_PORT'] + '/docs')"

CMD ["python", "-m", "app"]
