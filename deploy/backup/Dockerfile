# Sao lưu DB (decisions.md mục R): pg_dump cùng bản với Postgres, mã hóa bằng age, đẩy lên R2 bằng rclone.
FROM postgres:16-alpine
RUN apk add --no-cache age rclone tzdata \
    && mkdir -p /backups && chown postgres:postgres /backups
COPY --chmod=755 backup.sh restore.sh run.sh healthcheck.sh /usr/local/bin/
ENV TZ=Asia/Ho_Chi_Minh BACKUP_DIR=/backups
USER postgres
ENTRYPOINT []
CMD ["run.sh"]
