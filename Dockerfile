FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# socat forwards the hardcoded 127.0.0.1:7687 address to the neo4j service.
RUN apt-get update \
    && apt-get install -y --no-install-recommends socat \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first so this layer is cached between source changes.
COPY requirements.txt .
# Flask-SocketIO's threaded server uses simple-websocket for WebSocket
# support. It is not pulled in by requirements.txt, so install it here.
RUN pip install -r requirements.txt \
    && pip install simple-websocket

# Copy the application (data/ is provided at runtime via a bind mount).
COPY . .

EXPOSE 5000

CMD ["sh", "docker-entrypoint.sh"]
