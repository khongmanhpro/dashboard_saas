import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { t } from "../i18n";
import { FilterSheet } from "./FilterSheet";

/** jsdom không có matchMedia: giả một màn hình điện thoại đổi được độ rộng. */
function fakeScreen() {
  const listeners = new Set<() => void>();
  const media = {
    matches: true,
    addEventListener: (_: string, fn: () => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
  };
  vi.stubGlobal("matchMedia", () => media);
  return {
    widen() {
      media.matches = false;
      listeners.forEach((fn) => fn());
    },
  };
}

function renderSheet() {
  render(
    <FilterSheet active={0} onClear={() => undefined}>
      <label>
        A
        <select defaultValue="">
          <option value="">-</option>
        </select>
      </label>
    </FilterSheet>,
  );
  return { toggle: screen.getByTestId("filter-toggle"), open: () => fireEvent.click(screen.getByTestId("filter-toggle")) };
}

const dialog = () => screen.queryByRole("dialog", { name: t.filterSheet.title });

let screenSize: ReturnType<typeof fakeScreen>;
beforeEach(() => {
  screenSize = fakeScreen();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("bảng Lọc trên điện thoại", () => {
  it("mở thì con trỏ vào bảng và trang sau không cuộn; Esc đóng, con trỏ về nút Lọc", () => {
    const { toggle, open } = renderSheet();
    open();
    expect(dialog()?.contains(document.activeElement)).toBe(true);
    expect(document.body.style.overflow).toBe("hidden");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(dialog()).toBeNull();
    expect(document.activeElement).toBe(toggle);
    expect(document.body.style.overflow).toBe("");
  });

  it("Tab chỉ đi vòng trong bảng", () => {
    const { open } = renderSheet();
    open();
    const done = screen.getByRole("button", { name: t.filterSheet.done });
    const select = screen.getByRole("combobox");
    done.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(select);
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(done);
  });

  it("màn hình rộng ra từ 640px thì bảng tự đóng", () => {
    const { open } = renderSheet();
    open();
    expect(dialog()).not.toBeNull();
    act(() => screenSize.widen());
    expect(dialog()).toBeNull();
  });
});
