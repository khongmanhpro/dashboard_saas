import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { LEAD_EVENT_TYPES, REMINDER_TYPES } from "./leads";

/** Đọc giá trị của một `enum.StrEnum` trong backend/app/models/enums.py. */
function backendEnum(name: string): string[] {
  const source = readFileSync(join(__dirname, "../../../backend/app/models/enums.py"), "utf8");
  const body = new RegExp(`^class ${name}\\(enum\\.StrEnum\\):\\n([\\s\\S]*?)(?=^\\S|$(?![\\s\\S]))`, "m").exec(source)?.[1];
  if (!body) throw new Error(`Không thấy enum ${name}`);
  return [...body.matchAll(/^\s+[A-Z0-9_]+ = "([^"]+)"/gm)].map((m) => m[1] ?? "");
}

// Mục M, N: thiếu loại nào thì dòng thời gian hiện "Cập nhật khác" mà các test khác không biết.
describe("loại sự kiện và loại nhắc việc khớp backend", () => {
  it("LEAD_EVENT_TYPES = LeadEventType", () => {
    expect([...LEAD_EVENT_TYPES].sort()).toEqual(backendEnum("LeadEventType").sort());
  });

  it("REMINDER_TYPES = NotificationType", () => {
    expect([...REMINDER_TYPES].sort()).toEqual(backendEnum("NotificationType").sort());
  });
});
