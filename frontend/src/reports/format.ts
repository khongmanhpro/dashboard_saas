// Định dạng cho Tổng quan, Fanpage, Chi tiết Trang, Quảng cáo. Hàm thuần để test được.
import type { BoardRow, Metric } from "../api/reports";
import { format, t } from "../i18n";
import { formatDuration, formatVnd, groupThousands } from "../leads/format";
import { formatCompactVnd, formatPercent } from "../staff/format";

export const DASH = t.staff.hidden;

export function formatNumber(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  return groupThousands(Number(value));
}

export function formatMoney(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  return formatVnd(Number(value));
}

/** 284600000 → "284,6 tr ₫". */
export function formatMoneyShort(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  return `${formatCompactVnd(Number(value))} ${t.lead.result.currency}`;
}

/** Lượt xem: 1204000 → "1,2 tr"; 842000 → "842 N". */
export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  return formatCompactVnd(value);
}

export function formatRate(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  return formatPercent(value);
}

export function formatSeconds(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  return formatDuration(Number(value));
}

function trim1(n: number): string {
  return String(Math.round(n * 10) / 10).replace(".", ",");
}

export type DeltaKind = "percent" | "points" | "minutes";

/**
 * Mức thay đổi so với kỳ trước. `better`: chiều nào là tốt (doanh thu tăng là tốt, chi phí tăng là xấu).
 * - percent: thay đổi tương đối (%), cần kỳ trước > 0.
 * - points: chênh lệch tỉ lệ, tính bằng điểm phần trăm.
 * - minutes: chênh lệch số giây, hiện bằng phút.
 */
export function metricDelta(
  m: Metric | null | undefined,
  kind: DeltaKind,
  better: "up" | "down",
): { text: string; tone: "good" | "bad" | "flat" } | null {
  if (!m || m.value === null || m.previous === null) return null;
  const value = Number(m.value);
  const previous = Number(m.previous);
  let diff: number;
  let template: string;
  if (kind === "percent") {
    if (previous === 0) return null;
    diff = ((value - previous) / previous) * 100;
    template = t.reports.deltaPercent;
  } else if (kind === "points") {
    diff = (value - previous) * 100;
    template = t.reports.deltaPoints;
  } else {
    diff = (value - previous) / 60;
    template = t.reports.deltaMinutes;
  }
  const rounded = Math.round(diff * 10) / 10;
  if (rounded === 0) return { text: format(template, { sign: "", n: "0" }), tone: "flat" };
  const up = rounded > 0;
  return {
    text: format(template, { sign: up ? "▲ " : "▼ ", n: trim1(Math.abs(rounded)) }),
    tone: up === (better === "up") ? "good" : "bad",
  };
}

/** Toạ độ polyline, tự co theo giá trị nhỏ nhất/lớn nhất. Bỏ qua ngày không có số. */
export function linePoints(values: (number | null)[], width: number, height: number, pad = 2): string {
  const present = values.filter((v): v is number => v !== null);
  if (present.length === 0) return "";
  const min = Math.min(...present);
  const max = Math.max(...present);
  const span = max - min || 1;
  const step = values.length > 1 ? (width - pad * 2) / (values.length - 1) : 0;
  return values
    .map((v, i) =>
      v === null ? null : `${(pad + i * step).toFixed(1)},${(height - pad - ((v - min) / span) * (height - pad * 2)).toFixed(1)}`,
    )
    .filter((p): p is string => p !== null)
    .join(" ");
}

/** Xu hướng 7 ngày cuối so với 7 ngày trước đó. */
export function trendOf(values: (number | null)[]): "up" | "down" | "none" {
  const sum = (xs: (number | null)[]) => xs.reduce<number>((a, v) => a + (v ?? 0), 0);
  if (values.every((v) => v === null)) return "none";
  return sum(values.slice(-7)) >= sum(values.slice(-14, -7)) ? "up" : "down";
}

/** Mức màu 0–6 của ô bảng nhiệt theo giá trị lớn nhất. */
export function heatLevel(value: string | null, max: number): number {
  if (value === null || max <= 0) return 0;
  return Math.max(1, Math.min(6, Math.round((Number(value) / max) * 6)));
}

/** "2026-10-15" → "15/10". */
export function shortDate(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

/** Thứ trong tuần theo kiểu Việt Nam ("T2"…"CN") của một ngày "YYYY-MM-DD". */
export function weekdayShort(iso: string): string {
  const day = new Date(`${iso}T00:00:00Z`).getUTCDay();
  return t.pageDetail.weekdays[(day + 6) % 7] ?? "";
}

export function noteText(row: BoardRow): string | null {
  if (!row.note_key || row.note_value === null) return null;
  const key = row.note_key as keyof typeof t.overview.notes;
  const raw = row.note_value;
  const value =
    key === "close_rate" || key === "phone_rate" || key === "on_time"
      ? formatPercent(raw)
      : key === "response_speed"
        ? formatDuration(Number(raw))
        : key === "revenue"
          ? formatMoneyShort(raw)
          : String(Number(raw));
  return key in t.overview.notes ? format(t.overview.notes[key], { v: value }) : null;
}
