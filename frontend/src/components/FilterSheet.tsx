import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { format, t } from "../i18n";
import { Icon } from "./Icon";

/** Cùng mốc với CSS: dưới 640px mới có nút "Lọc" và bảng chọn. */
const PHONE = "(max-width: 639px)";
const FOCUSABLE = "button:not([disabled]), select:not([disabled]), input:not([disabled]), [href]";

/**
 * Các ô chọn của bộ lọc (decisions.md mục M, N). Máy tính: hiện thẳng trong thanh lọc như cũ.
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
  const toggleRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Mục N: con trỏ vào bảng và chỉ đi trong bảng, trang sau không cuộn; đóng thì con trỏ về nút "Lọc".
  // Màn hình rộng ra từ 640px (xoay ngang) thì bảng tự đóng.
  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    const toggle = toggleRef.current;
    const focusables = () => Array.from(panel?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []);
    focusables()[0]?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
      if (e.key !== "Tab") return;
      const items = focusables();
      const first = items[0];
      const last = items[items.length - 1];
      if (!first || !last) return;
      const current = document.activeElement;
      if (!panel?.contains(current)) {
        e.preventDefault();
        first.focus();
      } else if (e.shiftKey && current === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && current === last) {
        e.preventDefault();
        first.focus();
      }
    };
    const phone = window.matchMedia?.(PHONE);
    const onResize = () => {
      if (!phone?.matches) setOpen(false);
    };
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKey);
    phone?.addEventListener("change", onResize);
    return () => {
      document.removeEventListener("keydown", onKey);
      phone?.removeEventListener("change", onResize);
      document.body.style.overflow = overflow;
      toggle?.focus();
    };
  }, [open]);

  return (
    <>
      <button
        ref={toggleRef}
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
          ref={panelRef}
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
              {t.filterSheet.done}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
