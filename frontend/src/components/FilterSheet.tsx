import { useEffect, useId, useState, type ReactNode } from "react";

import { format, t } from "../i18n";
import { Icon } from "./Icon";

/**
 * Các ô chọn của bộ lọc (decisions.md mục M). Máy tính: hiện thẳng trong thanh lọc như cũ.
 * Điện thoại (< 640px): gom vào nút "Lọc (n)", bấm mở bảng chọn từ dưới lên. Chỉ có một bộ ô chọn,
 * CSS quyết định cách hiện, nên trạng thái lọc luôn là một.
 */
export function FilterSheet({
  active,
  onClear,
  children,
}: {
  /** Số bộ lọc đang khác mặc định. */
  active: number;
  onClear: () => void;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button
        type="button"
        className="btn filter-toggle"
        aria-expanded={open}
        aria-controls={id}
        data-testid="filter-toggle"
        onClick={() => setOpen(true)}
      >
        <Icon name="leads" />
        {active ? format(t.filterSheet.buttonCount, { n: active }) : t.filterSheet.button}
      </button>
      <div className={open ? "filter-sheet filter-sheet--open" : "filter-sheet"}>
        <div className="filter-sheet__backdrop" aria-hidden="true" onClick={() => setOpen(false)} />
        <div
          id={id}
          className="filter-sheet__panel"
          role={open ? "dialog" : undefined}
          aria-modal={open ? true : undefined}
          aria-label={open ? t.filterSheet.title : undefined}
        >
          <div className="filter-sheet__head">
            <b>{t.filterSheet.title}</b>
          </div>
          <div className="filter-sheet__body">{children}</div>
          <div className="filter-sheet__foot">
            <button type="button" className="btn" disabled={!active} onClick={onClear}>
              {t.filterSheet.clear}
            </button>
            <button type="button" className="btn btn--primary" onClick={() => setOpen(false)}>
              {t.filterSheet.apply}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
