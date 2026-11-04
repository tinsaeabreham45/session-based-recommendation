# Docker setup

This adds a two-service Docker Compose stack:

- `neo4j` - Neo4j 5.26 Community, with persistent named volumes.
- `app` - the existing Flask/Socket.IO application.

No application code was changed.

## Quick start

```bash
docker compose up --build -d
```

Open:

- Application: http://localhost:5000
- Neo4j Browser: http://localhost:7474

Neo4j credentials (must match the values hardcoded in `src/app.py`):

```text
username: neo4j
password: 12345678
```

The LLM pages read `GEMINI_API_KEY` from the existing `.env` file through
Compose variable interpolation. You can also override it in your shell:

```bash
GEMINI_API_KEY=your-key docker compose up --build -d
```

## Useful commands

```bash
docker compose ps                 # status
docker compose logs -f app        # application logs
docker compose logs -f neo4j      # database logs
docker compose stop               # stop without deleting data
docker compose down               # remove containers; Neo4j data is kept
docker compose down -v            # remove containers AND Neo4j data
docker compose up -d --build app  # rebuild/restart only the app
```

To run only Neo4j in Docker and run the app on your host:

```bash
docker compose up -d neo4j
python container_entrypoint.py
```

## How the app reaches Neo4j without code changes

`src/app.py` hardcodes:

```python
URI = "bolt://127.0.0.1:7687"
AUTH = ("neo4j", "12345678")
```

Inside a normal bridge-network container, `127.0.0.1` means the app container
itself, not the Neo4j container. Since the source cannot be edited,
`docker-entrypoint.sh` starts a small `socat` TCP forwarder:

```text
app container 127.0.0.1:7687  ->  neo4j:7687
```

The Neo4j driver therefore connects to the hardcoded address unchanged, while
the actual database runs in the separate `neo4j` service. The forwarder is
started automatically by the app container; no manual step is needed.

If you later make the Neo4j URI configurable in the application code, the
forwarder can be removed from `docker-entrypoint.sh` and the Dockerfile.

## Data

The RetailRocket CSV files (or a Neo4j dump) are **not included in this
repository**. The `data/` directory is bind-mounted read-only at `/app/data`,
so put the dataset files there before loading them into Neo4j. The prediction,
patterns, and graph pages will be empty until the graph is populated.

Neo4j data is stored in the `neo4j_data` Docker volume, so it survives
`docker compose down` and container restarts. Use `docker compose down -v`
only when you intentionally want to wipe the database.

## Memory

The default Neo4j settings are conservative:

```text
heap initial: 512m
heap max:     1G
page cache:   512m
```

Adjust `NEO4J_server_memory_heap_*` and
`NEO4J_server_memory_pagecache_size` in `docker-compose.yml` if the machine
has more memory and you load the full dataset.

## Troubleshooting

- **`permission denied` on `/var/run/docker.sock`**: add your user to the
  `docker` group and log out/in, or run Docker commands with sudo.
- **Port already in use**: stop the local process using port `5000`, `7474`,
  or `7687`, or change the host side of the mapping.
- **Neo4j password errors**: the volume remembers the password created on the
  first start. If you change `NEO4J_AUTH`, either use the old password or reset
  with `docker compose down -v` (this deletes all graph data).
- **The app starts before Neo4j is healthy**: `depends_on` with the Neo4j
  healthcheck should prevent this; check `docker compose ps` and the Neo4j
  logs if it does not.
