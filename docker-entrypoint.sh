#!/bin/sh
set -eu

# src/app.py hardcodes bolt://127.0.0.1:7687. Inside this container the Neo4j
# service is at neo4j:7687, so forward the hardcoded address over raw TCP.
socat TCP-LISTEN:7687,fork,reuseaddr,bind=127.0.0.1 TCP:neo4j:7687 &

exec python container_entrypoint.py
