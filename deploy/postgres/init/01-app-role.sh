#!/bin/sh
# Chạy MỘT LẦN khi volume Postgres còn trống (cơ chế docker-entrypoint-initdb.d).
# Tạo tài khoản ứng dụng: không phải superuser, không có BYPASSRLS, nên bị Row-Level Security giới hạn.
# Quyền trên từng bảng do migration cấp.
set -eu

if [ -z "${POSTGRES_APP_PASSWORD:-}" ]; then
  echo "POSTGRES_APP_PASSWORD đang trống, dừng khởi tạo." >&2
  exit 1
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_user="$POSTGRES_APP_USER" -v app_password="$POSTGRES_APP_PASSWORD" -v db="$POSTGRES_DB" <<'SQL'
CREATE ROLE :"app_user" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'app_password';
GRANT CONNECT ON DATABASE :"db" TO :"app_user";
GRANT USAGE ON SCHEMA public TO :"app_user";
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL
