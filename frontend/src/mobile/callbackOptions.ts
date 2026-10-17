// Lựa chọn giờ hẹn nhanh (quyết định Bước 5): "Chiều nay 15:00", "Tối nay 19:00" chỉ hiện khi còn kịp.
import { t } from "../i18n";
import { zonedLocalToIso } from "../leads/format";

export interface QuickTime {
  key: "today15" | "today19" | "tomorrow9";
  label: string;
  iso: string;
}

function localDate(now: Date, timeZone: string, addDays = 0): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(
    new Date(now.getTime() + addDays * 86_400_000),
  );
  return parts; // YYYY-MM-DD
}

export function quickCallbackTimes(now: Date, timeZone: string): QuickTime[] {
  const today = localDate(now, timeZone);
  const tomorrow = localDate(now, timeZone, 1);
  const candidates: [QuickTime["key"], string][] = [
    ["today15", `${today}T15:00`],
    ["today19", `${today}T19:00`],
    ["tomorrow9", `${tomorrow}T09:00`],
  ];
  return candidates
    .map(([key, local]) => ({ key, label: t.mobile.sheet.quick[key], iso: zonedLocalToIso(local, timeZone) ?? "" }))
    .filter((option) => option.iso && Date.parse(option.iso) > now.getTime());
}
