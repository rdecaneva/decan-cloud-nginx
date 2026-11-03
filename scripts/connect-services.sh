#!/bin/sh
# Attach running apps without recreating them; compose files preserve aliases on later deployments.
set -eu
docker network inspect decan-cloud-services >/dev/null 2>&1 || docker network create decan-cloud-services
connect() {
  container=$1 alias=$2
  if ! docker inspect "$container" --format '{{json .NetworkSettings.Networks}}' | grep -q '"decan-cloud-services"'; then
    docker network connect --alias "$alias" decan-cloud-services "$container"
  fi
}
connect mtg-tabletop-app-1 mtg-prod
connect mtg-tabletop-app-dev-1 mtg-dev
connect ti4-turn-tracker-app-1 imperium
connect game-stats-web-1 stats
connect decanid-web-1 tailcoat
