#!/bin/sh
# Khởi động API. Dev bật --reload; production chạy nhiều worker sau Caddy.
set -eu

if [ "${APP_ENV:-development}" = "development" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --no-access-log
else
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY:-2}" \
    --proxy-headers --forwarded-allow-ips "*" --no-access-log
fi
