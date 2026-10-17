import { describe, expect, it } from "vitest";

import { LEAD_EVENT_TYPES, REMINDER_TYPES, type LeadDetail, type TimelineItem } from "../../api/leads";
import { t } from "../../i18n";
import { reminderText } from "../../leads/format";
import { timelineRow } from "./LeadDetailPage";

const VN = "Asia/Ho_Chi_Minh";
const lead = {
  page: { id: "p", name: "[Trang]" },
  owner: { id: "m", name: "[Nhân viên 186]" },
  source: "message",
  from_ad: false,
  response_business_seconds: null,
  is_slow: false,
} as unknown as LeadDetail;

function event(type: string, data: Record<string, unknown> | null = null): TimelineItem {
  return {
    kind: "event",
    at: "2026-10-15T08:00:00Z",
    direction: null,
    text: null,
    has_attachments: false,
    is_automated: false,
    is_first_reply: false,
    type,
    actor: null,
    data,
  };
}

describe("dòng thời gian", () => {
  it("không loại sự kiện nào hiện mã thô", () => {
    for (const type of [...LEAD_EVENT_TYPES, "loai_moi_chua_biet"]) {
      const body = timelineRow(event(type, { from: "new", to: "won", types: ["overdue"] }), lead, VN).body;
      expect(body, type).not.toContain(type);
      expect(body, type).not.toMatch(/[a-z]+_[a-z]+/);
    }
  });

  it("mọi loại nhắc việc có chữ tiếng Việt", () => {
    for (const type of REMINDER_TYPES) {
      expect(t.lead.reminderTypes[type], type).toBeTruthy();
    }
  });

  it("nhắc việc gửi cùng lúc hiện trên một dòng", () => {
    expect(reminderText({ types: ["overdue", "phone_not_called"] })).toBe(
      "Đã nhắc: Quá hạn cập nhật kết quả · Có SĐT nhưng chưa gọi.",
    );
    expect(reminderText({ type: "callback_missed" })).toBe("Đã nhắc: Quá giờ hẹn chưa cập nhật.");
    expect(reminderText({ types: ["la_lam"] })).toBe("Đã nhắc: Nhắc việc từ quản lý.");
  });
});
