#!/usr/bin/env bash
# Run only against an isolated, already-started M0 test stack. This script applies
# Alembic migrations and restarts PostgreSQL; it never removes data or volumes.
# Set COMPOSE_PROJECT_NAME to the same explicit project used for `compose up`.
set -euo pipefail

: "${COMPOSE_PROJECT_NAME:?Set COMPOSE_PROJECT_NAME to your isolated test project.}"

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_directory/.."

for required_command in docker python3; do
  if ! command -v "$required_command" >/dev/null 2>&1; then
    printf 'Required command is unavailable: %s\n' "$required_command" >&2
    exit 1
  fi
done

printf 'Checking isolated project %s; migrations and a PostgreSQL restart follow.\n' \
  "$COMPOSE_PROJECT_NAME"
docker compose --profile worker config --quiet

web_address="$(docker compose port web 80)"
if [[ ! "$web_address" =~ ^127\.0\.0\.1:[0-9]+$ ]]; then
  printf 'Expected the test web service to bind to 127.0.0.1, got: %s\n' \
    "$web_address" >&2
  exit 1
fi
base_url="http://$web_address"

check_web() {
  python3 - "$base_url" <<'PY'
import json
import sys
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.request import urlopen

base_url = sys.argv[1]


def fetch(path):
    with urlopen(base_url + path, timeout=10) as response:
        return response.headers.get_content_type(), response.read()


content_type, health = fetch("/api/v1/health")
assert content_type == "application/json", "Health must return JSON through Caddy"
assert json.loads(health) == {"status": "ok"}, "Unexpected health payload"

content_type, homepage = fetch("/")
assert content_type == "text/html", "Home page must return HTML"
assert b"LifeArchive" in homepage, "Home page must include the application brand"
assert b'id="root"' in homepage, "Home page must contain the React root"


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        path = attrs.get("src") if tag == "script" else attrs.get("href")
        if path and path.startswith("/assets/") and path.endswith((".js", ".css")):
            self.paths.append(path)


assets = Assets()
assets.feed(homepage.decode())
assert any(path.endswith(".js") for path in assets.paths), "No compiled JavaScript found"
assert any(path.endswith(".css") for path in assets.paths), "No compiled stylesheet found"
for path in assets.paths:
    content_type, body = fetch(path)
    allowed_types = (
        {"text/javascript", "application/javascript"}
        if path.endswith(".js")
        else {"text/css"}
    )
    assert content_type in allowed_types and body, f"Invalid static asset: {path}"

_, fallback = fetch("/m0-smoke-client-route")
assert fallback == homepage, "Client routes must resolve to the SPA entry point"

try:
    fetch("/api/v1/m0-smoke-unknown-route")
except HTTPError as error:
    assert error.code == 404, "Unknown API routes must return HTTP 404"
    assert error.headers.get_content_type() == "application/json", (
        "Unknown API routes must not fall back to the SPA"
    )
    assert json.loads(error.read()) == {"detail": "Not Found"}
else:
    raise AssertionError("Unknown API route unexpectedly succeeded")

print("PASS: Caddy API proxy, home page, compiled assets and SPA routing")
PY
}

read_revision() {
  docker compose exec -T postgres sh -c \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -Atc "SELECT version_num FROM alembic_version ORDER BY version_num"'
}

check_web

postgres_id="$(docker compose ps -q postgres)"
postgres_volumes="$(docker inspect --format \
  '{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}{{println}}{{end}}{{end}}' \
  "$postgres_id")"
if [[ "$postgres_volumes" != *"${COMPOSE_PROJECT_NAME}_pgdata"* ]]; then
  printf 'PostgreSQL must mount the project pgdata named volume.\n' >&2
  exit 1
fi

docker compose exec -T api alembic upgrade head
revision_before="$(read_revision)"
if [[ -z "$revision_before" ]]; then
  printf 'The smoke migration did not record an Alembic revision.\n' >&2
  exit 1
fi
docker compose exec -T api alembic upgrade head
if [[ "$(read_revision)" != "$revision_before" ]]; then
  printf 'Repeated migration changed the Alembic revision unexpectedly.\n' >&2
  exit 1
fi
docker compose exec -T api alembic current
printf 'PASS: migration applies and repeated upgrade is safe (%s)\n' "$revision_before"

docker compose restart postgres
postgres_ready=false
for ((attempt = 0; attempt < 30; attempt++)); do
  if docker compose exec -T postgres sh -c \
    'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
    postgres_ready=true
    break
  fi
  sleep 1
done
if [[ "$postgres_ready" != true ]]; then
  printf 'PostgreSQL did not become ready within 30 attempts.\n' >&2
  exit 1
fi
if [[ "$(read_revision)" != "$revision_before" ]]; then
  printf 'Alembic revision was not preserved across the PostgreSQL restart.\n' >&2
  exit 1
fi
docker compose exec -T api alembic current
printf 'PASS: pgdata preserves the migration revision after PostgreSQL restart\n'

if ! worker_output="$(docker compose --profile worker run --rm --no-deps -T worker 2>&1)"; then
  printf '%s\n' "$worker_output" >&2
  printf 'Worker placeholder did not exit successfully.\n' >&2
  exit 1
fi
printf '%s\n' "$worker_output"
if [[ "$worker_output" != *"M0 worker placeholder: no jobs or scheduler configured; exiting."* ]]; then
  printf 'Worker did not report the expected M0 placeholder exit.\n' >&2
  exit 1
fi
printf 'PASS: worker placeholder exits successfully without starting a scheduler\n'
check_web
printf 'PASS: all M0 Compose smoke checks completed\n'
