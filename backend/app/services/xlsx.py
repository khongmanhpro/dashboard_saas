"""Ghi file Excel (decisions.md mục O).

Mọi chuỗi ghi ra là ô chữ: tên Trang, họ tên, mật khẩu tạm bắt đầu bằng `=`, `+`, `-`, `@` không
thành công thức khi mở bằng Excel, và giữ nguyên giá trị (không thêm dấu `'`).
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from typing import Any

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet


def append_row(ws: Worksheet, values: Iterable[Any]) -> None:
    ws.append(list(values))
    for cell in ws[ws.max_row]:
        if isinstance(cell.value, str):
            # openpyxl tự coi chuỗi bắt đầu bằng "=" là công thức; ép lại thành chữ.
            cell.data_type = "s"


def to_bytes(wb: Workbook) -> bytes:
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
