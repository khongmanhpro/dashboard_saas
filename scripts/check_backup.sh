#!/bin/sh
# Chạy thật cả vòng sao lưu → khôi phục bằng image deploy/backup (decisions.md mục R):
#   sao lưu DB nguồn (mặc định fanpage_simulate_test, có dữ liệu từ `make simulate`), mã hóa age,
#   đẩy lên kho giả (rclone local thay cho R2), dọn bản cũ, khôi phục vào fanpage_restore_test
#   rồi so số dòng từng bảng, chính sách RLS, quyền của tài khoản ứng dụng.
# Chỉ đọc DB nguồn, chỉ ghi vào fanpage_restore_test (xóa khi xong). Cần `make up` (DB đang chạy).
set -eu

SOURCE=${BACKUP_CHECK_SOURCE:-fanpage_simulate_test}
SOURCE_APP_USER=${BACKUP_CHECK_APP_USER:-fanpage_app_sim}
TARGET=fanpage_restore_test
C="docker compose"
WORK=$(mktemp -d)
FAILED=0

psql_in() { # psql_in <db> <sql>
  $C exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$1" -tAc "$2"' _ "$1" "$2"
}
cleanup() {
  psql_in postgres "DROP DATABASE IF EXISTS $TARGET WITH (FORCE)" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

check() { # check <tên> <giá trị thật> <giá trị mong đợi>
  if [ "$2" = "$3" ]; then echo "OK   $1"; else echo "LỖI  $1: nhận '$2', mong đợi '$3'"; FAILED=1; fi
}

[ "$(psql_in postgres "SELECT 1 FROM pg_database WHERE datname = '$SOURCE'")" = "1" ] \
  || { echo "Chưa có DB $SOURCE. Chạy make simulate trước." >&2; exit 1; }

$C --profile tools build -q backup
mkdir -p "$WORK/backups" "$WORK/remote"
chmod 777 "$WORK/backups" "$WORK/remote"

keygen() { $C --profile tools run --rm -T --no-deps backup age-keygen 2>/dev/null; }
keygen > "$WORK/key"
keygen > "$WORK/wrong-key"
chmod 644 "$WORK/key" "$WORK/wrong-key"
PUB=$(sed -n 's/^# public key: //p' "$WORK/key")

# 15 bản cũ trên VPS và 2 bản cũ trên "R2": sau lần sao lưu phải còn 14 bản trên VPS, R2 hết bản cũ.
for d in 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15; do
  : > "$WORK/backups/$SOURCE-202601$d-020000.dump.age"
  touch -t "202601${d}0200" "$WORK/backups/$SOURCE-202601$d-020000.dump.age"
done
for d in 01 02; do
  : > "$WORK/remote/$SOURCE-202601$d-020000.dump.age"
  touch -t "202601${d}0200" "$WORK/remote/$SOURCE-202601$d-020000.dump.age"
done

run() { # run <khóa> <lệnh...>: chạy trong image backup, R2 thay bằng thư mục /remote
  key=$1; shift
  $C --profile tools run --rm -T \
    -v "$WORK/backups:/backups" -v "$WORK/remote:/remote" -v "$WORK/$key:/run/age-key:ro" \
    -e POSTGRES_DB="$SOURCE" -e POSTGRES_APP_USER="$SOURCE_APP_USER" \
    -e BACKUP_AGE_RECIPIENT="$PUB" -e R2_BUCKET=/remote -e RCLONE_CONFIG_R2_TYPE=local \
    backup "$@"
}

run key backup.sh
NAME=$(cd "$WORK/remote" && ls -1t *.dump.age | head -1)
check "bản mới đã lên kho R2" "$(ls "$WORK/remote")" "$NAME"
check "VPS giữ 14 bản" "$(ls "$WORK/backups"/*.dump.age | wc -l | tr -d ' ')" "14"
check "bản mới nằm trên VPS" "$(test -s "$WORK/backups/$NAME" && echo có)" "có"
check "bản sao lưu đã mã hóa age" "$(head -c 21 "$WORK/backups/$NAME")" "age-encryption.org/v1"
check "healthcheck khỏe sau khi xong" "$(run key healthcheck.sh >/dev/null && echo khỏe)" "khỏe"

rm "$WORK/backups/.last-ok"
check "thiếu cấu hình R2 thì báo lỗi" \
  "$(run key sh -c 'unset R2_BUCKET; backup.sh' >/dev/null 2>&1 && echo xong || echo lỗi)" "lỗi"
check "thiếu R2 thì healthcheck không khỏe" "$(run key healthcheck.sh >/dev/null 2>&1 && echo khỏe || echo hỏng)" "hỏng"

run key restore.sh "r2:$NAME" "$TARGET"

SIG="SELECT string_agg(t || '=' || n, ' ' ORDER BY t) FROM (
  SELECT c.relname AS t,
    (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM public.%I', c.relname), false, true, '')))[1]::text AS n
  FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace
  WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p')) x"
POLICIES="SELECT count(*) || ' chính sách, ' || (SELECT count(*) FROM pg_class WHERE relrowsecurity) || ' bảng bật RLS' FROM pg_policies"
GRANTS="SELECT count(*) FROM information_schema.role_table_grants WHERE grantee = '$SOURCE_APP_USER'"
FUNCS="SELECT string_agg(proname || ':' || prosecdef, ' ' ORDER BY proname) FROM pg_proc p JOIN pg_namespace s ON s.oid = p.pronamespace WHERE s.nspname = 'public'"

src_rows=$(psql_in "$SOURCE" "$SIG")
check "số dòng từng bảng khớp" "$(psql_in "$TARGET" "$SIG")" "$src_rows"
check "có dữ liệu để so" "$(echo "$src_rows" | grep -Eq 'leads=[1-9]' && echo có)" "có"
check "chính sách RLS khớp" "$(psql_in "$TARGET" "$POLICIES")" "$(psql_in "$SOURCE" "$POLICIES")"
src_grants=$(psql_in "$SOURCE" "$GRANTS")
check "có quyền của tài khoản ứng dụng để so" "$([ "$src_grants" -gt 0 ] && echo có)" "có"
check "quyền tài khoản ứng dụng khớp" "$(psql_in "$TARGET" "$GRANTS")" "$src_grants"
check "hàm (cả SECURITY DEFINER) khớp" "$(psql_in "$TARGET" "$FUNCS")" "$(psql_in "$SOURCE" "$FUNCS")"
check "tài khoản ứng dụng được CONNECT" \
  "$(psql_in "$TARGET" "SELECT has_database_privilege('$SOURCE_APP_USER', '$TARGET', 'CONNECT')")" "t"

check "DB đích đã có, thiếu --replace thì dừng" \
  "$(run key restore.sh "$NAME" "$TARGET" >/dev/null 2>&1 && echo chạy || echo dừng)" "dừng"
check "sai khóa giải mã thì dừng" \
  "$(run wrong-key restore.sh "$NAME" "$TARGET" --replace >/dev/null 2>&1 && echo chạy || echo dừng)" "dừng"
check "sai khóa không xóa DB đích" "$(psql_in "$TARGET" "$SIG")" "$src_rows"

exit $FAILED
