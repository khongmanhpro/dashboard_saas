import { describe, expect, it } from "vitest";

import type { LeadCard } from "../api/leads";
import {
  cardTimer,
  displayName,
  EMPTY_RESULT_FORM,
  formatDateTime,
  formatDuration,
  formatVnd,
  initials,
  isoToZonedLocal,
  parseVndInput,
  sourceLabel,
  validateResultForm,
  zonedLocalToIso,
} from "./format";

const VN = "Asia/Ho_Chi_Minh";

function card(overrides: Partial<LeadCard> = {}): LeadCard {
  return {
    id: "1",
    display_name: null,
    short_ref: "1234",
    page: { id: "p", name: "[Trang]" },
    owner: null,
    source: "message",
    from_ad: false,
    fb_ad_id: null,
    status: "new",
    first_inbound_at: "2026-10-15T02:00:00Z",
    first_reply_at: null,
    response_business_seconds: null,
    waiting_business_seconds: 47 * 60,
    is_slow: true,
    result_due_at: "2026-10-17T02:00:00Z",
    result_at: null,
    overdue: false,
    callback_at: null,
    won_value_vnd: null,
    lost_reason: null,
    phone: null,
    phone_masked: false,
    called_at: null,
    ...overrides,
  };
}

describe("tiền VND", () => {
  it("định dạng có dấu chấm ngăn nghìn", () => {
    expect(formatVnd(2_450_000)).toBe("2.450.000 ₫");
    expect(formatVnd(0)).toBe("0 ₫");
    expect(formatVnd(999)).toBe("999 ₫");
  });

  it("đọc ô nhập, bỏ ký tự không phải số", () => {
    expect(parseVndInput("2.450.000")).toBe(2_450_000);
    expect(parseVndInput("2,450,000 ₫")).toBe(2_450_000);
    expect(parseVndInput("")).toBeNull();
    expect(parseVndInput("abc")).toBeNull();
    expect(parseVndInput("9".repeat(20))).toBeNull();
  });
});

describe("thời lượng và ngày giờ", () => {
  it("thời lượng", () => {
    expect(formatDuration(30)).toBe("dưới 1 phút");
    expect(formatDuration(47 * 60)).toBe("47 phút");
    expect(formatDuration(2 * 3600)).toBe("2 giờ");
    expect(formatDuration(2 * 3600 + 5 * 60)).toBe("2 giờ 5 phút");
    expect(formatDuration(3 * 86400 + 10)).toBe("3 ngày");
  });

  it("ngày giờ theo múi giờ workspace", () => {
    expect(formatDateTime("2026-10-15T02:12:00Z", VN)).toBe("15/10 09:12");
    expect(formatDateTime("2026-10-15T17:30:00Z", VN)).toBe("16/10 00:30");
  });

  it("ô datetime-local hiểu theo giờ Việt Nam", () => {
    expect(zonedLocalToIso("2026-10-18T10:00", VN)).toBe("2026-10-18T03:00:00.000Z");
    expect(zonedLocalToIso("không hợp lệ", VN)).toBeNull();
    expect(isoToZonedLocal("2026-10-18T03:00:00Z", VN)).toBe("2026-10-18T10:00");
  });
});

describe("thẻ khách", () => {
  const now = new Date("2026-10-15T08:00:00Z");

  it("tên và chữ viết tắt", () => {
    expect(displayName(card())).toBe("Khách ···1234");
    expect(displayName(card({ display_name: "[Khách 1042]" }))).toBe("[Khách 1042]");
    expect(initials("Vũ Ngọc Mai")).toBe("NM");
    expect(initials("[Nhân viên 186]")).toBe("V1");
  });

  it("nhãn thời gian theo trạng thái", () => {
    expect(cardTimer(card(), now, VN)).toEqual({ text: "chờ 47 phút", hot: true });
    expect(cardTimer(card({ overdue: true }), now, VN)).toEqual({ text: "quá 48 giờ", hot: true });
    expect(cardTimer(card({ status: "won", won_value_vnd: 850_000 }), now, VN).text).toBe("850.000 ₫");
    expect(cardTimer(card({ status: "callback", callback_at: "2026-10-18T03:00:00Z" }), now, VN).text).toBe(
      "hẹn 18/10 10:00",
    );
    const contacted = card({ status: "contacted", waiting_business_seconds: null, first_reply_at: "2026-10-15T02:00:00Z" });
    expect(cardTimer(contacted, now, VN)).toEqual({ text: "6 giờ trước", hot: false });
  });

  it("nguồn khách", () => {
    expect(sourceLabel(card())).toBe("Tin nhắn · không từ quảng cáo");
    expect(sourceLabel(card({ from_ad: true }))).toBe("Tin nhắn · từ quảng cáo");
    expect(sourceLabel(card({ source: "leadgen" }))).toBe("Form khách hàng tiềm năng");
    expect(sourceLabel(card({ status: "lost", lost_reason: "price" }))).toBe("Lý do: giá cao");
  });
});

describe("form kết quả", () => {
  it("bắt buộc chọn kết quả và nhập đủ", () => {
    expect(validateResultForm(EMPTY_RESULT_FORM, VN)).toEqual({ ok: false, label: "Chọn kết quả để lưu" });
    expect(validateResultForm({ ...EMPTY_RESULT_FORM, status: "won" }, VN)).toMatchObject({ ok: false });
    expect(validateResultForm({ ...EMPTY_RESULT_FORM, status: "won", wonValue: "0" }, VN)).toMatchObject({ ok: false });
    expect(validateResultForm({ ...EMPTY_RESULT_FORM, status: "lost" }, VN)).toEqual({
      ok: false,
      label: "Chọn lý do hủy để lưu",
    });
    expect(validateResultForm({ ...EMPTY_RESULT_FORM, status: "lost", lostReason: "other" }, VN)).toMatchObject({
      ok: false,
    });
    expect(validateResultForm({ ...EMPTY_RESULT_FORM, status: "callback" }, VN)).toMatchObject({ ok: false });
  });

  it("tạo body đúng cho API", () => {
    expect(validateResultForm({ ...EMPTY_RESULT_FORM, status: "won", wonValue: "2.450.000", note: " " }, VN)).toEqual({
      ok: true,
      body: { status: "won", won_value_vnd: 2_450_000, note: undefined },
    });
    expect(
      validateResultForm({ ...EMPTY_RESULT_FORM, status: "callback", callbackLocal: "2026-10-18T10:00" }, VN),
    ).toEqual({ ok: true, body: { status: "callback", callback_at: "2026-10-18T03:00:00.000Z", note: undefined } });
    expect(
      validateResultForm({ ...EMPTY_RESULT_FORM, status: "lost", lostReason: "other", note: "[lý do]" }, VN),
    ).toEqual({ ok: true, body: { status: "lost", lost_reason: "other", note: "[lý do]" } });
  });
});
