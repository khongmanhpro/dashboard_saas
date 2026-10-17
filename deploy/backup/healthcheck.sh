#!/bin/sh
# Khỏe khi lần sao lưu xong gần nhất (đã lên R2) chưa quá 26 giờ.
f="${BACKUP_DIR:-/backups}/.last-ok"
[ -f "$f" ] && [ $(( $(date +%s) - $(cat "$f") )) -lt 93600 ]
