// Định dạng hiển thị cho màn hình khách: tiền VND, thời lượng, ngày giờ theo múi giờ workspace,
// nhãn trên thẻ khách. Hàm thuần để test được.
import type { LeadCard, LostReason, ReminderType, ResultBody } from "../api/leads";
import { format, t } from "../i18n";

/** 2450000 → "2.450.000 ₫" (số nguyên VND, không dùng số thực). */
export function formatVnd(value: number): string {
  return `${groupThousands(value)} ${t.lead.result.currency}`;
}

export function groupThousands(value: number): string {
  const digits = String(Math.trunc(Math.abs(value)));
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return value < 0 ? `-${grouped}` : grouped;
}

/** Ô nhập tiền: giữ lại chữ số. "2.450.000" → 2450000; rỗng → null. */
export function parseVndInput(raw: string): number | null {
  const digits = raw.replace(/\D/g, "");
  if (!digits) return null;
  const value = Number(digits);
  return Number.isSafeInteger(value) ? value : null;
}

/** Số giây → "47 phút", "2 giờ 5 phút", "3 ngày". */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return t.duration.lessThanMinute;
  const minutes = Math.floor(s / 60);
  if (minutes < 60) return format(t.duration.minutes, { m: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    const rest = minutes % 60;
    return rest ? format(t.duration.hoursMinutes, { h: hours, m: rest }) : format(t.duration.hours, { h: hours });
  }
  return format(t.duration.days, { d: Math.floor(hours / 24) });
}

/** "15/10 09:12" theo múi giờ của workspace. */
export function formatDateTime(iso: string, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("day")}/${get("month")} ${get("hour")}:${get("minute")}`;
}

function zoneOffsetMinutes(utcMillis: number, timeZone: string): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(utcMillis));
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value);
  const asUtc = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"), get("second"));
  return Math.round((asUtc - utcMillis) / 60_000);
}

/** Giá trị ô datetime-local ("2026-10-18T10:00") hiểu theo múi giờ workspace → ISO có múi giờ. */
export function zonedLocalToIso(value: string, timeZone: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!m) return null;
  const n = (i: number) => Number(m[i]);
  const guess = Date.UTC(n(1), n(2) - 1, n(3), n(4), n(5));
  const offset = zoneOffsetMinutes(guess - zoneOffsetMinutes(guess, timeZone) * 60_000, timeZone);
  return new Date(guess - offset * 60_000).toISOString();
}

/** ISO → giá trị cho ô datetime-local theo múi giờ workspace. */
export function isoToZonedLocal(iso: string, timeZone: string): string {
  const utc = new Date(iso).getTime();
  const local = new Date(utc + zoneOffsetMinutes(utc, timeZone) * 60_000);
  return local.toISOString().slice(0, 16);
}

export function displayName(lead: Pick<LeadCard, "display_name" | "short_ref">): string {
  return lead.display_name ?? format(t.leads.unnamed, { ref: lead.short_ref });
}

/** "Vũ Ngọc Mai" → "NM"; "[Nhân viên 186]" → "V1". */
export function initials(name: string): string {
  const words = name.replace(/[[\]]/g, "").trim().split(/\s+/).filter(Boolean);
  return words
    .slice(-2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

export function sourceLabel(lead: Pick<LeadCard, "source" | "from_ad" | "status" | "lost_reason">): string {
  if (lead.status === "lost" && lead.lost_reason) {
    return format(t.leads.lostReasonLine, { reason: t.leads.lostReasons[lead.lost_reason].toLowerCase() });
  }
  if (lead.source === "leadgen") return t.leads.sourceForm;
  return lead.from_ad ? t.leads.sourceAd : t.leads.sourceOrganic;
}

/** Nhắc việc đã gửi (backend gộp các nhắc cùng lúc vào `types`): "Quá hạn cập nhật kết quả · Có SĐT nhưng chưa gọi". */
export function reminderText(data: Record<string, unknown> | null): string {
  const raw = data?.types ?? (data?.type ? [data.type] : []);
  const labels = (Array.isArray(raw) ? raw : [])
    .filter((x): x is string => typeof x === "string")
    .map((x) => (x in t.lead.reminderTypes ? t.lead.reminderTypes[x as ReminderType] : t.lead.reminderTypes.manual));
  return format(t.lead.events.reminder_sent, { what: [...new Set(labels)].join(" · ") || t.lead.reminderTypes.manual });
}

export interface Timer {
  text: string;
  hot: boolean;
  /** Hiện thành nhãn đỏ (hẹn gọi lại đã qua). */
  badge?: boolean;
}

export function timerClass(timer: Timer): string {
  if (timer.badge) return "timer timer--badge";
  return timer.hot ? "timer timer--hot" : "timer";
}

/** "Quá hẹn 2 ngày" (dưới 1 ngày: giờ, dưới 1 giờ: phút), hoặc null khi chưa tới giờ hẹn (decisions.md mục M). */
export function callbackOverdue(callbackAt: string, now: Date): string | null {
  const ms = now.getTime() - Date.parse(callbackAt);
  if (ms <= 0) return null;
  const days = Math.floor(ms / 86_400_000);
  if (days >= 1) return format(t.leads.callbackOverdueDays, { n: days });
  const hours = Math.floor(ms / 3_600_000);
  if (hours >= 1) return format(t.leads.callbackOverdueHours, { n: hours });
  return format(t.leads.callbackOverdueMinutes, { n: Math.max(1, Math.floor(ms / 60_000)) });
}

/** Chữ góc phải của thẻ khách, theo thiết kế Leads.dc.html. */
export function cardTimer(lead: LeadCard, now: Date, timeZone: string): Timer {
  if (lead.status === "won" && lead.won_value_vnd !== null) return { text: formatVnd(lead.won_value_vnd), hot: false };
  if (lead.status === "lost") return { text: "", hot: false };
  if (lead.status === "callback" && lead.callback_at) {
    const late = callbackOverdue(lead.callback_at, now);
    if (late) return { text: late, hot: true, badge: true };
    return { text: format(t.leads.callbackAt, { time: formatDateTime(lead.callback_at, timeZone) }), hot: false };
  }
  if (lead.overdue) {
    const hours = Math.round((Date.parse(lead.result_due_at) - Date.parse(lead.first_inbound_at)) / 3_600_000);
    return { text: format(t.leads.overdue, { hours }), hot: true };
  }
  if (lead.waiting_business_seconds !== null) {
    return { text: format(t.leads.waiting, { time: formatDuration(lead.waiting_business_seconds) }), hot: lead.is_slow };
  }
  const since = lead.first_reply_at ?? lead.first_inbound_at;
  return { text: format(t.leads.ago, { time: formatDuration((now.getTime() - Date.parse(since)) / 1000) }), hot: false };
}

// ---------------------------------------------------------------- form kết quả

export interface ResultForm {
  status: ResultBody["status"] | null;
  wonValue: string;
  callbackLocal: string;
  lostReason: LostReason | null;
  note: string;
}

export const EMPTY_RESULT_FORM: ResultForm = {
  status: null,
  wonValue: "",
  callbackLocal: "",
  lostReason: null,
  note: "",
};

/** Kiểm tra form trước khi gửi. Backend vẫn kiểm tra lại. */
export function validateResultForm(
  form: ResultForm,
  timeZone: string,
): { ok: true; body: ResultBody } | { ok: false; label: string } {
  const note = form.note.trim() || undefined;
  if (form.status === null) return { ok: false, label: t.lead.result.pickResult };
  if (form.status === "won") {
    const value = parseVndInput(form.wonValue);
    if (!value) return { ok: false, label: t.lead.result.enterValue };
    return { ok: true, body: { status: "won", won_value_vnd: value, note } };
  }
  if (form.status === "callback") {
    const iso = zonedLocalToIso(form.callbackLocal, timeZone);
    if (!iso) return { ok: false, label: t.lead.result.pickTime };
    return { ok: true, body: { status: "callback", callback_at: iso, note } };
  }
  if (!form.lostReason) return { ok: false, label: t.lead.result.pickReason };
  if (form.lostReason === "other" && !note) return { ok: false, label: t.lead.result.noteRequired };
  return { ok: true, body: { status: "lost", lost_reason: form.lostReason, note } };
}
