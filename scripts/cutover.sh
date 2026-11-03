#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker compose exec -T nginx-a nginx -t
docker compose exec -T nginx-b nginx -t
docker stop mtg-tabletop-web-1
rollback() {
  echo 'Cutover failed; restoring the previous MTG proxy.' >&2
  docker compose stop edge || true
  docker start mtg-tabletop-web-1
}
if ! docker compose up -d --no-deps --no-build edge; then rollback; exit 1; fi
if ! curl --noproxy '*' --fail --silent --show-error --retry 10 --retry-all-errors --retry-connrefused --retry-delay 1 --resolve mtg.decaneva.cloud:443:127.0.0.1 https://mtg.decaneva.cloud/ >/dev/null; then
  rollback
  exit 1
fi
echo 'Shared ingress now serves ports 80 and 443.'
