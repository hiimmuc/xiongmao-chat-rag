#!/usr/bin/env bash
# Starts or updates the backend on the EC2 server. GitHub Actions runs it through AWS SSM:
#   deploy.sh <api-image-uri>
# Steps: build .env from SSM Parameter Store, log in to ECR, stop the worker, pull images,
# run migrations, start everything, check the API is ready.
set -euo pipefail
export PATH="$PATH:/snap/bin"
IMAGE="$1"
# Written by the server's first-boot script: AWS_REGION, DEPLOY_BUCKET, ECR_REGISTRY, API_DOMAIN, PARAMETER_PATH.
source /etc/xiongmao.env
cd /opt/xiongmao

# The database password is generated once and kept on the data disk, next to the database itself.
PASSWORD_FILE=/data/postgres-password
umask 077
[ -s "$PASSWORD_FILE" ] || openssl rand -hex 24 > "$PASSWORD_FILE"
PASSWORD=$(cat "$PASSWORD_FILE")
install -d -o 10001 -g 10001 /data/storage   # uploads; the API image runs as uid 10001

# Every parameter under PARAMETER_PATH becomes NAME=value in .env.
{
  aws ssm get-parameters-by-path --region "$AWS_REGION" --path "$PARAMETER_PATH" \
    --recursive --with-decryption --query 'Parameters[].[Name,Value]' --output text |
    while IFS=$'\t' read -r name value; do echo "${name##*/}=$value"; done
  echo "POSTGRES_PASSWORD=$PASSWORD"
  echo "DATABASE_URL=postgresql+psycopg://chatbot:$PASSWORD@db:5432/chatbot"
  echo "API_IMAGE=$IMAGE"
  echo "API_DOMAIN=$API_DOMAIN"
} > .env.new
mv .env.new .env

aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "$ECR_REGISTRY"

# Only one worker may run, so stop the old one before migrating.
docker compose stop worker 2>/dev/null || true
docker compose pull --quiet
docker compose up -d --remove-orphans

for _ in $(seq 1 30); do
  if docker compose exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready')" 2>/dev/null; then
    echo "Deployed $IMAGE"
    docker image prune -f >/dev/null
    exit 0
  fi
  sleep 2
done
echo "API did not become ready. Recent logs:" >&2
docker compose logs --tail 80 migrate api >&2
exit 1
