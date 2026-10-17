#!/bin/sh
# Một lần sao lưu: pg_dump -Fc → mã hóa age → ghi BACKUP_DIR → đẩy lên R2 → dọn bản cũ.
# Chỉ ghi $BACKUP_DIR/.last-ok khi xong cả ba bước (healthcheck dựa vào file này).
set -eu
set -o pipefail

: "${POSTGRES_DB:?}" "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}"
: "${BACKUP_AGE_RECIPIENT:?Thiếu BACKUP_AGE_RECIPIENT (khóa công khai age)}"
DIR=${BACKUP_DIR:-/backups}
KEEP=${BACKUP_KEEP:-14}
export PGHOST=${POSTGRES_HOST:-db} PGPORT=${POSTGRES_PORT:-5432} PGPASSWORD=$POSTGRES_PASSWORD

name="$POSTGRES_DB-$(date +%Y%m%d-%H%M%S).dump.age"
tmp="$DIR/.$name.part"
trap 'rm -f "$tmp"' EXIT

pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc | age -r "$BACKUP_AGE_RECIPIENT" > "$tmp"
mv "$tmp" "$DIR/$name"
echo "Sao lưu: $name ($(du -h "$DIR/$name" | cut -f1))"

# Giữ $KEEP bản mới nhất trên VPS.
ls -1t "$DIR"/*.dump.age | tail -n +"$((KEEP + 1))" | while read -r old; do
  rm -f "$old" && echo "Xóa bản cũ: $(basename "$old")"
done

if [ -z "${R2_BUCKET:-}" ] || [ -z "${RCLONE_CONFIG_R2_TYPE:-}" ]; then
  echo "LỖI: chưa cấu hình R2, bản sao lưu chỉ nằm trên VPS." >&2
  exit 1
fi
rclone -q copyto --no-check-dest "$DIR/$name" "r2:$R2_BUCKET/$name"
rclone -q delete --min-age "${KEEP}d" --include '*.dump.age' "r2:$R2_BUCKET"
echo "Đã đẩy lên R2: $name"

date +%s > "$DIR/.last-ok"
