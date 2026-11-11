# The Gym Buddy server as one container: the API, the rep counter and the dashboard.
# Build and run it with docker compose from the repo root (see docs/deploy.md).
FROM python:3.12-slim

# Python inside a container: no .pyc files, and print straight to the logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GYM_BUDDY_DATA=/data/sets \
    GYM_BUDDY_DB=/data/gymbuddy.db

WORKDIR /srv

# The libraries first, in their own layer: they are only installed again when
# requirements-run.txt changes, not every time the code does.
COPY requirements-run.txt .
RUN pip install --no-cache-dir -r requirements-run.txt

COPY app ./app
COPY scripts/backfill.py ./scripts/backfill.py

# Everything worth keeping lives in /data, which docker compose puts on a volume.
# The app runs as an ordinary user, not root, and that user owns /data.
RUN useradd --create-home buddy && mkdir /data && chown buddy /data
USER buddy
VOLUME /data

EXPOSE 8000

# Docker asks the server "are you up?" every 30 s and marks the container unhealthy if not.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
