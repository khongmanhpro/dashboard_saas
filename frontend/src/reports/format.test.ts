import { describe, expect, it } from "vitest";

import { heatLevel, linePoints, metricDelta, noteText, shortDate, trendOf, weekdayShort } from "./format";

describe("metricDelta", () => {
  it("phần trăm: doanh thu tăng là tốt", () => {
    expect(metricDelta({ value: "1093", previous: "1000" }, "percent", "up")).toEqual({ text: "▲ 9,3%", tone: "good" });
  });
  it("phần trăm: chi phí tăng là xấu", () => {
    expect(metricDelta({ value: "104", previous: "100" }, "percent", "down")?.tone).toBe("bad");
  });
  it("điểm phần trăm cho tỉ lệ", () => {
    expect(metricDelta({ value: "0.1840", previous: "0.1920" }, "points", "up")).toEqual({
      text: "▼ 0,8 điểm",
      tone: "bad",
    });
  });
  it("phút cho thời gian trả lời: giảm là tốt", () => {
    expect(metricDelta({ value: "1440", previous: "1800" }, "minutes", "down")).toEqual({ text: "▼ 6 phút", tone: "good" });
  });
  it("không có kỳ trước thì không so", () => {
    expect(metricDelta({ value: "5", previous: null }, "percent", "up")).toBeNull();
    expect(metricDelta({ value: "5", previous: "0" }, "percent", "up")).toBeNull();
    expect(metricDelta(null, "percent", "up")).toBeNull();
  });
});

describe("biểu đồ", () => {
  it("linePoints co theo min/max và bỏ ngày trống", () => {
    expect(linePoints([0, null, 10], 104, 24)).toBe("2.0,22.0 102.0,2.0");
    expect(linePoints([null, null], 100, 20)).toBe("");
  });
  it("xu hướng so 7 ngày cuối với 7 ngày trước", () => {
    expect(trendOf([...Array(7).fill(10), ...Array(7).fill(5)])).toBe("down");
    expect(trendOf([...Array(7).fill(5), ...Array(7).fill(10)])).toBe("up");
    expect(trendOf([null, null])).toBe("none");
  });
  it("mức màu bảng nhiệt", () => {
    expect(heatLevel(null, 0.07)).toBe(0);
    expect(heatLevel("0.07", 0.07)).toBe(6);
    expect(heatLevel("0.001", 0.07)).toBe(1);
  });
});

describe("ngày và ghi chú", () => {
  it("ngày ngắn và thứ", () => {
    expect(shortDate("2026-10-15")).toBe("15/10");
    expect(weekdayShort("2026-10-12")).toBe("T2");
    expect(weekdayShort("2026-10-18")).toBe("CN");
  });
  it("ghi chú bảng xếp hạng theo tiêu chí", () => {
    const base = { member: { id: "1", name: "x" }, rank: 1, total: "90", tier: "A" as const, page: null };
    expect(noteText({ ...base, note_key: "close_rate", note_value: "0.34" })).toBe("chốt 34%");
    expect(noteText({ ...base, note_key: "response_speed", note_value: "360" })).toBe("trả lời 6 phút");
    expect(noteText({ ...base, note_key: null, note_value: null })).toBeNull();
  });
});
