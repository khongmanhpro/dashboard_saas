from __future__ import annotations

import datetime as dt
import enum
import uuid
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import uuid7

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: dict[Any, Any] = {  # noqa: RUF012
        dt.datetime: DateTime(timezone=True),
    }


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid7)


def created_at_col() -> Mapped[dt.datetime]:
    return mapped_column(server_default=func.now())


def updated_at_col() -> Mapped[dt.datetime]:
    return mapped_column(server_default=func.now(), onupdate=func.now())


def workspace_fk(ondelete: str = "RESTRICT") -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("workspaces.id", ondelete=ondelete), index=True)


def str_enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    """Lưu enum dạng VARCHAR + CHECK: thêm giá trị mới không cần ALTER TYPE."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda cls: [m.value for m in cls],
        validate_strings=True,
    )
