FROM python:3.12-slim

# AkamaiRequests writes akamai_requests.log + a requests_cache sqlite file under $HOME,
# so HOME must be writable by the non-root user this container runs as.
ENV HOME=/home/appuser \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --home-dir /home/appuser --uid 10001 appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Single worker process (shared in-memory job registry) with multiple threads:
# some threads run background jobs, others serve HTTP/SSE requests concurrently.
# --worker-class gthread is required, --threads is a no-op on the default sync worker.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--worker-class", "gthread", "--workers", "1", "--threads", "12", "--timeout", "120", "app:app"]
