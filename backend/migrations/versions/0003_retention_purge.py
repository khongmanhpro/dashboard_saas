"""Hạn lưu dữ liệu: xóa `webhook_events` sau 30 ngày, xóa nội dung tin nhắn sau 180 ngày.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17

- `app_purge_expired_data(webhook_days, message_text_days)` chạy với quyền chủ hàm để job ban đêm
  (tài khoản ứng dụng, bị RLS) xử lý được mọi workspace. Hàm chỉ làm hai việc: xóa dòng
  `webhook_events` cũ, đặt `messages.text = NULL` cho tin cũ. Ngưỡng dưới 30 / 180 ngày bị từ chối.
  Trả về số dòng đã xử lý.
- Chỉ mục một phần `ix_messages_sent_at_with_text` để job không phải quét cả bảng `messages`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.helpers import app_role

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCTION = "app_purge_expired_data(integer, integer)"


def upgrade() -> None:
    op.create_index(
        "ix_messages_sent_at_with_text",
        "messages",
        ["sent_at"],
        unique=False,
        postgresql_where=sa.text("text IS NOT NULL"),
    )
    op.execute(
        """
        CREATE FUNCTION app_purge_expired_data(
            p_webhook_days integer, p_message_text_days integer
        )
        RETURNS TABLE (webhook_events_deleted bigint, message_texts_cleared bigint)
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE
            v_events bigint;
            v_texts bigint;
        BEGIN
            IF p_webhook_days IS NULL OR p_webhook_days < 30 THEN
                RAISE EXCEPTION 'p_webhook_days phải >= 30' USING ERRCODE = '22023';
            END IF;
            IF p_message_text_days IS NULL OR p_message_text_days < 180 THEN
                RAISE EXCEPTION 'p_message_text_days phải >= 180' USING ERRCODE = '22023';
            END IF;

            DELETE FROM public.webhook_events
            WHERE received_at < now() - make_interval(days => p_webhook_days);
            GET DIAGNOSTICS v_events = ROW_COUNT;

            UPDATE public.messages SET text = NULL
            WHERE text IS NOT NULL
              AND sent_at < now() - make_interval(days => p_message_text_days);
            GET DIAGNOSTICS v_texts = ROW_COUNT;

            RETURN QUERY SELECT v_events, v_texts;
        END
        $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {FUNCTION} FROM PUBLIC")
    op.execute(f'GRANT EXECUTE ON FUNCTION {FUNCTION} TO "{app_role()}"')


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {FUNCTION}")
    op.drop_index(
        "ix_messages_sent_at_with_text",
        table_name="messages",
        postgresql_where=sa.text("text IS NOT NULL"),
    )
