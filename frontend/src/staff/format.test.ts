import { describe, expect, it } from "vitest";

import { DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS } from "../api/staff";
import {
  formatCompactVnd,
  formatDelta,
  formatPercent,
  formatScore,
  saveLabel,
  sameThresholds,
  sameWeights,
  thresholdsValid,
  stepWeight,
  tierRanges,
  trendPoints,
  weightsTotal,
} from "./format";

describe("định dạng số", () => {
  it("phần trăm và điểm dùng dấu phẩy", () => {
    expect(formatPercent("0.2910")).toBe("29,1%");
    expect(formatPercent("1.0000")).toBe("100%");
    expect(formatPercent(null)).toBe("—");
    expect(formatScore("72.40")).toBe("72,4");
    expect(formatScore("100.00")).toBe("100");
  });

  it("tiền rút gọn", () => {
    expect(formatCompactVnd(61_500_000)).toBe("61,5 tr");
    expect(formatCompactVnd(850_000)).toBe("850 n");
    expect(formatCompactVnd(2_000_000_000)).toBe("2 tỷ");
    expect(formatCompactVnd(0)).toBe("0");
  });

  it("chênh lệch so với tuần trước", () => {
    expect(formatDelta("3.00")).toEqual({ text: "▲3", dir: "up" });
    expect(formatDelta("-4.50")).toEqual({ text: "▼4,5", dir: "down" });
    expect(formatDelta("0.00")).toEqual({ text: "–", dir: "flat" });
    expect(formatDelta(null)).toBeNull();
  });

  it("khoảng điểm của hạng", () => {
    expect(tierRanges({ tier_a: 85, tier_b: 70, tier_c: 50 })).toEqual({
      A: "≥ 85 điểm",
      B: "70–84",
      C: "50–69",
      D: "< 50",
    });
  });
});

describe("trọng số công thức", () => {
  it("tổng và bước 5", () => {
    expect(weightsTotal(DEFAULT_WEIGHTS)).toBe(100);
    const up = stepWeight(DEFAULT_WEIGHTS, "close_rate", 5);
    expect(up.close_rate).toBe(35);
    expect(weightsTotal(up)).toBe(105);
    expect(stepWeight(DEFAULT_WEIGHTS, "on_time", -10).on_time).toBe(0);
    expect(sameWeights(DEFAULT_WEIGHTS, { ...DEFAULT_WEIGHTS })).toBe(true);
    expect(sameWeights(DEFAULT_WEIGHTS, up)).toBe(false);
  });

  it("nhãn nút lưu", () => {
    expect(saveLabel(105, true)).toEqual({ ok: false, label: "Tổng phải bằng 100% (còn thừa 5%)" });
    expect(saveLabel(95, true)).toEqual({ ok: false, label: "Tổng phải bằng 100% (còn thiếu 5%)" });
    expect(saveLabel(100, false)).toEqual({ ok: false, label: "Chưa đổi công thức" });
    expect(saveLabel(100, true)).toEqual({ ok: true, label: "Lưu công thức" });
  });

  it("toạ độ đường điểm", () => {
    expect(trendPoints([100, 50, 0], 100, 100)).toBe("0.0,0.0 50.0,50.0 100.0,100.0");
    expect(trendPoints([null, 80], 100, 100)).toBe("100.0,20.0");
  });
});

describe("ngưỡng chấm điểm", () => {
  it("mặc định hợp lệ, so sánh được", () => {
    expect(thresholdsValid(DEFAULT_THRESHOLDS)).toBe(true);
    expect(sameThresholds(DEFAULT_THRESHOLDS, { ...DEFAULT_THRESHOLDS })).toBe(true);
    expect(sameThresholds(DEFAULT_THRESHOLDS, { ...DEFAULT_THRESHOLDS, close_rate_full: 40 })).toBe(false);
  });
  it("chặn ngưỡng ngược hoặc ngoài khoảng", () => {
    expect(thresholdsValid({ ...DEFAULT_THRESHOLDS, close_rate_zero: 30 })).toBe(false);
    expect(thresholdsValid({ ...DEFAULT_THRESHOLDS, phone_rate_full: 120 })).toBe(false);
    expect(thresholdsValid({ ...DEFAULT_THRESHOLDS, speed_full_minutes: 130 })).toBe(false);
    expect(thresholdsValid({ ...DEFAULT_THRESHOLDS, revenue_full_vnd: 0 })).toBe(false);
    expect(thresholdsValid({ ...DEFAULT_THRESHOLDS, on_time_zero: 2.5 })).toBe(false);
  });
  it("nút Lưu báo ngưỡng sai trước", () => {
    expect(saveLabel(100, true, false).ok).toBe(false);
    expect(saveLabel(100, true, true).ok).toBe(true);
  });
});
