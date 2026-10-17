import { describe, expect, it } from "vitest";

import { quickCallbackTimes } from "./callbackOptions";
import { base64UrlToBytes } from "./push";

const VN = "Asia/Ho_Chi_Minh";

describe("giờ hẹn nhanh", () => {
  it("buổi sáng có đủ ba lựa chọn", () => {
    const now = new Date("2026-10-14T02:00:00Z"); // 09:00 giờ VN
    expect(quickCallbackTimes(now, VN).map((o) => [o.label, o.iso])).toEqual([
      ["Chiều nay 15:00", "2026-10-14T08:00:00.000Z"],
      ["Tối nay 19:00", "2026-10-14T12:00:00.000Z"],
      ["Mai 9:00", "2026-10-15T02:00:00.000Z"],
    ]);
  });

  it("đã qua 15:00 thì bỏ lựa chọn chiều nay", () => {
    const now = new Date("2026-10-14T09:30:00Z"); // 16:30 giờ VN
    expect(quickCallbackTimes(now, VN).map((o) => o.key)).toEqual(["today19", "tomorrow9"]);
  });

  it("tối muộn chỉ còn sáng mai", () => {
    const now = new Date("2026-10-14T16:30:00Z"); // 23:30 giờ VN
    expect(quickCallbackTimes(now, VN)).toEqual([
      { key: "tomorrow9", label: "Mai 9:00", iso: "2026-10-15T02:00:00.000Z" },
    ]);
  });
});

describe("khóa VAPID", () => {
  it("đổi base64url sang bytes", () => {
    expect(Array.from(base64UrlToBytes("AQID_-8"))).toEqual([1, 2, 3, 255, 239]);
  });
});
