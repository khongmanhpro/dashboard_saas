#!/bin/sh
# Khôi phục một bản sao lưu vào DB <đích> (decisions.md mục R).
#   restore.sh <bản> <đích> [--replace]
# <bản>: tên file trong BACKUP_DIR, đường dẫn, hoặc r2:<tên file> để tải từ R2.
# Khóa giải mã age của chủ sở hữu mount vào AGE_IDENTITY_FILE (mặc định /run/age-key), chỉ lúc khôi phục.
# <đích> đã có thì dừng, trừ khi thêm --replace (xóa DB đó rồi tạo lại). Tắt backend và worker trước.
set -eu
set -o pipefail

[ $# -ge 2 ] || { echo "Cách dùng: restore.sh <bản> <đích> [--replace]" >&2; exit 2; }
src=$1 target=$2 replace=${3:-}
: "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}" "${POSTGRES_APP_USER:?}"
KEY=${AGE_IDENTITY_FILE:-/run/age-key}
DIR=${BACKUP_DIR:-/backups}
export PGHOST=${POSTGRES_HOST:-db} PGPORT=${POSTGRES_PORT:-5432} PGPASSWORD=$POSTGRES_PASSWORD
[ -r "$KEY" ] || { echo "Không đọc được khóa giải mã $KEY" >&2; exit 1; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
case $src in
  r2:*) rclone -q copyto "r2:$R2_BUCKET/${src#r2:}" "$work/backup.age"; file="$work/backup.age" ;;
  */*) file=$src ;;
  *) file="$DIR/$src" ;;
esac

# Giải mã trước khi đụng vào DB: sai khóa hay file hỏng thì DB đích không bị xóa.
age -d -i "$KEY" "$file" > "$work/backup.dump"
pg_restore --list "$work/backup.dump" > /dev/null

exists=$(psql -U "$POSTGRES_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$target'")
if [ "$exists" = "1" ]; then
  [ "$replace" = "--replace" ] || { echo "DB $target đã có. Thêm --replace để xóa và khôi phục đè." >&2; exit 1; }
  dropdb -U "$POSTGRES_USER" --force "$target"
fi
createdb -U "$POSTGRES_USER" -O "$POSTGRES_USER" "$target"
psql -U "$POSTGRES_USER" -d "$target" -v ON_ERROR_STOP=1 -q \
  -c "GRANT CONNECT ON DATABASE \"$target\" TO \"$POSTGRES_APP_USER\""
pg_restore -U "$POSTGRES_USER" -d "$target" --no-owner --exit-on-error "$work/backup.dump"

tables=$(psql -U "$POSTGRES_USER" -d "$target" -tAc "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
version=$(psql -U "$POSTGRES_USER" -d "$target" -tAc "SELECT version_num FROM alembic_version")
echo "Đã khôi phục vào $target: $tables bảng, migration $version."
