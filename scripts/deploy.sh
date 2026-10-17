#!/bin/sh
# Cập nhật bản mới trên VPS (decisions.md mục S): sao lưu ngay → git pull nhánh main → build → up.
# Migration tự chạy (service migrate) trước backend. Chờ backend khỏe rồi in trạng thái.
#   scripts/deploy.sh
# .env có CLOUDFLARE_TUNNEL_TOKEN thì tự chạy qua tunnel (docker-compose.tunnel.yml).
# DEPLOY_SKIP_PULL=1: không git pull (thử trên máy dev). ENV_FILE: file .env khác (mặc định .env).
set -eu
cd "$(dirname "$0")/.."

ENV_FILE=${ENV_FILE:-.env}
export ENV_FILE
[ -f "$ENV_FILE" ] || { echo "Chưa có $ENV_FILE. Chạy make env-prod DOMAIN=<tên miền> trước." >&2; exit 1; }
set -- -f docker-compose.prod.yml
if grep -Eq '^CLOUDFLARE_TUNNEL_TOKEN=[^[:space:]#]' "$ENV_FILE"; then
  set -- "$@" -f docker-compose.tunnel.yml
  echo "Chạy qua Cloudflare Tunnel."
fi

if [ "${DEPLOY_SKIP_PULL:-}" != "1" ]; then
  branch=$(git rev-parse --abbrev-ref HEAD)
  [ "$branch" = "main" ] || { echo "VPS phải ở nhánh main (đang ở $branch)." >&2; exit 1; }
fi

# Sao lưu trước khi đổi bản (migration mới có thể đổi dữ liệu). Lần đầu chưa có container thì bỏ qua.
if [ -n "$(docker compose "$@" --env-file "$ENV_FILE" ps -q --status running backup 2>/dev/null)" ]; then
  echo "Sao lưu trước khi cập nhật..."
  docker compose "$@" --env-file "$ENV_FILE" exec -T backup backup.sh \
    || { echo "Sao lưu lỗi, dừng cập nhật. Xem: docker compose logs backup" >&2; exit 1; }
fi

if [ "${DEPLOY_SKIP_PULL:-}" != "1" ]; then
  git pull --ff-only
fi
echo "Bản: $(git log -1 --format='%h %s')"

docker compose "$@" --env-file "$ENV_FILE" build
docker compose "$@" --env-file "$ENV_FILE" up -d --remove-orphans

echo "Chờ backend khỏe..."
i=0
until [ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose "$@" --env-file "$ENV_FILE" ps -q backend)" 2>/dev/null)" = "healthy" ]; do
  i=$((i + 1))
  if [ $i -gt 60 ]; then
    echo "Backend chưa khỏe sau 5 phút. Xem: docker compose logs backend migrate" >&2
    docker compose "$@" --env-file "$ENV_FILE" ps
    exit 1
  fi
  sleep 5
done

docker compose "$@" --env-file "$ENV_FILE" ps
docker image prune -f >/dev/null
echo "Xong."
