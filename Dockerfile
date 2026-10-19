FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
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
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
