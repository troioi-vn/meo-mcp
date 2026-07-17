#!/usr/bin/env bash
set -euo pipefail

deploy_path=${1:?deploy path required}
branch=${2:?branch required}
test "$branch" = dev
cd "$deploy_path"
test -f .env
docker compose run --rm meo-mcp alembic upgrade head
docker compose up -d --build --remove-orphans
for attempt in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8020/health >/dev/null; then
    exit 0
  fi
  sleep 3
done
docker compose logs --tail=100 meo-mcp >&2
exit 1
