// Định dạng số cho màn hình Nhân viên và Cài đặt. Hàm thuần để test được.
import type { Formula, Thresholds, Tier, Weights } from "../api/staff";
import { CRITERIA } from "../api/staff";
import { format, t } from "../i18n";

/** "0.2910" → "29,1%" (dấu phẩy thập phân theo tiếng Việt). */
export function formatPercent(rate: string | number | null): string {
  if (rate === null) return t.staff.hidden;
  const value = Number(rate) * 100;
  const rounded = Math.round(value * 10) / 10;
  return `${String(rounded).replace(".", ",")}%`;
}

/** 61500000 → "61,5 tr"; 850000 → "850 n"; số nhỏ giữ nguyên. */
export function formatCompactVnd(value: number | null): string {
  if (value === null) return t.staff.hidden;
  if (value >= 1_000_000_000) return `${trim(value / 1_000_000_000)} ${t.staff.units.billion}`;
  if (value >= 1_000_000) return `${trim(value / 1_000_000)} ${t.staff.units.million}`;
  if (value >= 1_000) return `${trim(value / 1_000)} ${t.staff.units.thousand}`;
  return String(value);
}

function trim(n: number): string {
  return String(Math.round(n * 10) / 10).replace(".", ",");
}

/** "72.40" → "72,4"; null → "—". */
export function formatScore(value: string | null): string {
  if (value === null) return t.staff.hidden;
  return trim(Number(value));
}

export function formatDelta(value: string | null): { text: string; dir: "up" | "down" | "flat" } | null {
  if (value === null) return null;
  const n = Math.round(Number(value) * 10) / 10;
  if (n === 0) return { text: "–", dir: "flat" };
  return n > 0
    ? { text: `▲${trim(n)}`, dir: "up" }
    : { text: `▼${trim(-n)}`, dir: "down" };
}

export function tierRanges(f: Pick<Formula, "tier_a" | "tier_b" | "tier_c">): Record<Tier, string> {
  const p = { a: f.tier_a, b: f.tier_b, c: f.tier_c, a1: f.tier_a - 1, b1: f.tier_b - 1 };
  return {
    A: format(t.staff.tierRange.A, p),
    B: format(t.staff.tierRange.B, p),
    C: format(t.staff.tierRange.C, p),
    D: format(t.staff.tierRange.D, p),
  };
}

export function weightsTotal(w: Weights): number {
  return CRITERIA.reduce((sum, c) => sum + w[c], 0);
}

export function sameWeights(a: Weights, b: Weights): boolean {
  return CRITERIA.every((c) => a[c] === b[c]);
}

export function sameThresholds(a: Thresholds, b: Thresholds): boolean {
  return (Object.keys(a) as (keyof Thresholds)[]).every((k) => a[k] === b[k]);
}

/** Ngưỡng hợp lệ: số nguyên, "0 điểm" < "100 điểm", tỉ lệ trong 0–100 (cùng kiểm tra với backend). */
export function thresholdsValid(th: Thresholds): boolean {
  const ints = Object.values(th).every((v) => Number.isInteger(v) && v >= 0);
  const rates = (["close_rate", "phone_rate", "on_time"] as const).every(
    (k) => th[`${k}_zero`] < th[`${k}_full`] && th[`${k}_full`] <= 100,
  );
  return ints && rates && th.speed_full_minutes < th.speed_zero_minutes && th.speed_zero_minutes <= 1440 && th.revenue_full_vnd > 0;
}

/** Đổi trọng số theo bước 5, giữ trong 0–100. */
export function stepWeight(w: Weights, key: keyof Weights, delta: number): Weights {
  return { ...w, [key]: Math.max(0, Math.min(100, w[key] + delta)) };
}

/** Nhãn nút Lưu theo tổng trọng số. */
export function saveLabel(total: number, changed: boolean, thresholdsOk = true): { ok: boolean; label: string } {
  if (!thresholdsOk) return { ok: false, label: t.settings.score.thresholdInvalid };
  if (total !== 100) {
    const diff = total < 100 ? format(t.settings.score.missing, { n: 100 - total }) : format(t.settings.score.extra, { n: total - 100 });
    return { ok: false, label: format(t.settings.score.mustBe100, { diff }) };
  }
  if (!changed) return { ok: false, label: t.settings.score.unchanged };
  return { ok: true, label: t.settings.score.save };
}

/** Toạ độ đường điểm theo tuần cho SVG (trục y 0–100). */
export function trendPoints(totals: (number | null)[], width: number, height: number): string {
  const step = totals.length > 1 ? width / (totals.length - 1) : 0;
  return totals
    .map((v, i) => (v === null ? null : `${(i * step).toFixed(1)},${(height - (v / 100) * height).toFixed(1)}`))
    .filter((p): p is string => p !== null)
    .join(" ");
}
