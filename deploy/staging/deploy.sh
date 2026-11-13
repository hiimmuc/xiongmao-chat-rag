#!/usr/bin/env bash
# Starts or updates staging on the GCP VM, as the `deploy` user. GitHub Actions uploads a release
# to /opt/xiongmao/incoming (config, API image, web build, app.env) and runs:
#   bash /opt/xiongmao/incoming/staging/deploy.sh <release>
# Roll back to a release that is still on the VM (the last 3 are kept):
#   bash /opt/xiongmao/staging/deploy.sh <older-release>
set -euo pipefail
RELEASE="$1"
IMAGE="xiongmao-api:$RELEASE"
cd /opt/xiongmao
umask 077

# 1. Unpack a new upload, if there is one.
if [ -d incoming ]; then
  cp incoming/compose.yaml compose.yaml
  mkdir -p staging web/releases
  cp incoming/staging/* staging/
  gunzip -c incoming/api.tar.gz | docker load --quiet
  rm -rf "web/releases/$RELEASE"
  mv incoming/site "web/releases/$RELEASE"
  chmod -R a+rX "web/releases/$RELEASE"
  mv incoming/app.env app.env # settings and secrets from GitHub, kept for rollbacks
  rm -rf incoming
fi
docker image inspect "$IMAGE" >/dev/null || { echo "No image $IMAGE on this server" >&2; exit 1; }
[ -d "web/releases/$RELEASE" ] || { echo "No web release $RELEASE on this server" >&2; exit 1; }

# 2. Build .env: the GitHub settings plus what only the server knows.
DOMAIN=$(sed -n 's/^DOMAIN=//p' app.env)
[ -n "$DOMAIN" ] || { echo "DOMAIN missing from app.env" >&2; exit 1; }
PASSWORD_FILE=/data/postgres-password # generated once, kept next to the database
[ -s "$PASSWORD_FILE" ] || openssl rand -hex 24 > "$PASSWORD_FILE"
PASSWORD=$(cat "$PASSWORD_FILE")
{
  grep -v '^DOMAIN=' app.env
  echo "APP_ENV=production" # staging behaves exactly like production
  echo "CORS_ORIGINS=https://$DOMAIN"
  echo "POSTGRES_PASSWORD=$PASSWORD"
  echo "DATABASE_URL=postgresql+psycopg://chatbot:$PASSWORD@db:5432/chatbot"
  echo "API_IMAGE=$IMAGE"
  echo "API_DOMAIN=$DOMAIN"
  echo "COMPOSE_FILE=compose.yaml:staging/compose.yaml" # so plain `docker compose ...` works here
} > .env.new
mv .env.new .env

# 3. Backend first. Only one worker may run, so stop the old one before migrating.
docker compose stop worker 2>/dev/null || true
docker compose up -d --remove-orphans
ready=""
for _ in $(seq 1 30); do
  if docker compose exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready')" 2>/dev/null; then
    ready=1
    break
  fi
  sleep 2
done
if [ -z "$ready" ]; then
  echo "API did not become ready; the web app was not switched. Recent logs:" >&2
  docker compose logs --tail 80 migrate api >&2
  exit 1
fi

# 4. Then the web app: switch the `current` link in one step, so visitors never see a half-copied build.
ln -sfn "releases/$RELEASE" web/current.new
mv -T web/current.new web/current

# 5. Keep the active release plus the two newest others (images and web builds) for rollbacks.
ls -1t web/releases | { grep -vx "$RELEASE" || true; } | tail -n +3 | while read -r old; do rm -rf "web/releases/$old"; done
docker images xiongmao-api --format '{{.Tag}}' | { grep -vx "$RELEASE" || true; } | tail -n +3 |
  while read -r tag; do docker rmi "xiongmao-api:$tag" >/dev/null 2>&1 || true; done
docker image prune -f >/dev/null
echo "Deployed release $RELEASE to https://$DOMAIN"
