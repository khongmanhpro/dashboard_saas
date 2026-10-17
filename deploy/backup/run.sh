#!/bin/sh
# Chạy sao lưu mỗi ngày lúc BACKUP_AT (giờ TZ, mặc định 02:00). Khởi động mà 26 giờ chưa có lần
# xong thì sao lưu ngay. Lỗi không làm dừng container: healthcheck báo unhealthy.
set -u
AT=${BACKUP_AT:-02:00}
echo "Sao lưu mỗi ngày lúc $AT ($TZ)."
healthcheck.sh || backup.sh || echo "Sao lưu LỖI" >&2
last=""
while true; do
  now=$(date +%H:%M) today=$(date +%F)
  if [ "$now" = "$AT" ] && [ "$last" != "$today" ]; then
    last=$today
    backup.sh || echo "Sao lưu LỖI" >&2
  fi
  sleep 20
done
