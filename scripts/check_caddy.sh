#!/bin/sh
# Kiểm tra deploy/Caddyfile bằng Caddy thật trong Docker (decisions.md mục Q):
#   1. Chế độ thường nghe :443 (tự lo HTTPS), chế độ tunnel nghe :80.
#   2. Qua tunnel: backend nhận đúng CF-Connecting-IP, bỏ X-Forwarded-For khách tự gửi.
#   3. Không qua proxy tin cậy: bỏ cả hai header, backend nhận IP thật của người gọi.
# Backend giả là một Caddy trả lại X-Forwarded-For nó nhận được.
set -eu

IMAGE=caddy:2-alpine
NET=caddycheck-$$
SUBNET=172.31.251.0/28
CADDYFILE="$(cd "$(dirname "$0")/.." && pwd)/deploy/Caddyfile"
FAILED=0

cleanup() {
  docker rm -f "$NET-proxy" "$NET-backend" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

check() { # check <tên> <giá trị thật> <giá trị mong đợi>
  if [ "$2" = "$3" ]; then
    echo "OK   $1"
  else
    echo "LỖI  $1: nhận '$2', mong đợi '$3'"
    FAILED=1
  fi
}

listen_of() { # listen_of <các -e ...>: cổng mà Caddyfile nghe
  docker run --rm "$@" -e APP_DOMAIN=app.test -v "$CADDYFILE:/etc/caddy/Caddyfile:ro" "$IMAGE" \
    caddy adapt --config /etc/caddy/Caddyfile 2>/dev/null \
    | python3 -c "import json,sys; print(*[s['listen'][0] for s in json.load(sys.stdin)['apps']['http']['servers'].values()])"
}

start_proxy() { # start_proxy <TRUSTED_PROXY_CIDR hoặc rỗng>
  docker rm -f "$NET-proxy" >/dev/null 2>&1 || true
  set -- -e CADDY_SITE_PREFIX=http:// -e APP_DOMAIN=app.test ${1:+-e TRUSTED_PROXY_CIDR=$1}
  docker run -d --name "$NET-proxy" --network "$NET" --network-alias app.test "$@" \
    -v "$CADDYFILE:/etc/caddy/Caddyfile:ro" "$IMAGE" >/dev/null
}

call() { # in "<IP người gọi> <X-Forwarded-For backend nhận>"
  docker run --rm --network "$NET" "$IMAGE" sh -c '
    for i in $(seq 1 30); do
      body=$(wget -qO- --header "CF-Connecting-IP: 203.0.113.7" --header "X-Forwarded-For: 6.6.6.6" \
        http://app.test/api/check 2>/dev/null) && break
      sleep 0.5
    done
    echo "$(hostname -i) $body"'
}

check "chế độ thường nghe :443" "$(listen_of)" ":443"
check "chế độ tunnel nghe :80" "$(listen_of -e CADDY_SITE_PREFIX=http://)" ":80"

docker network create --subnet "$SUBNET" "$NET" >/dev/null
docker run -d --name "$NET-backend" --network "$NET" --network-alias backend "$IMAGE" \
  sh -c 'printf ":8000 {\n\trespond \"{header.X-Forwarded-For}\"\n}\n" > /tmp/C && caddy run --config /tmp/C --adapter caddyfile' \
  >/dev/null

start_proxy "$SUBNET"
set -- $(call)
check "qua tunnel: backend nhận IP từ CF-Connecting-IP" "${2:-}" "203.0.113.7"

start_proxy ""
set -- $(call)
check "không qua proxy tin cậy: backend nhận IP người gọi" "${2:-}" "$1"

exit $FAILED
