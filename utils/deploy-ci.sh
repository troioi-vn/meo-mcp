#!/usr/bin/env bash
set -euo pipefail

deploy_path=${1:?deploy path required}
branch=${2:?branch required}
case "$branch" in
  dev|main) ;;
  *)
    echo "unsupported deploy branch: $branch" >&2
    exit 2
    ;;
esac
cd "$deploy_path"
test -f .env
docker compose build meo-mcp
docker compose run --rm meo-mcp alembic upgrade head
docker compose up -d --remove-orphans
host_port=$(sed -n 's/^MEO_MCP_PORT=//p' .env | tail -n 1)
host_port=${host_port:-8020}
case "$host_port" in
  *[!0-9]*|'')
    echo "MEO_MCP_PORT must be a numeric host port" >&2
    exit 2
    ;;
esac
for attempt in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:${host_port}/health" >/dev/null; then
    exit 0
  fi
  sleep 3
done
docker compose logs --tail=100 meo-mcp >&2
exit 1
