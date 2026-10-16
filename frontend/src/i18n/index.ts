import { vi } from "./vi";

/** Từ điển đang dùng. Khi có thêm ngôn ngữ, chọn theo cài đặt của workspace/người dùng. */
export const t = vi;

/** Điền tham số: format("Sau {minutes} phút", { minutes: 5 }) → "Sau 5 phút". */
export function format(template: string, params: Record<string, string | number> = {}): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in params ? String(params[key]) : match,
  );
}

type ErrorCode = keyof typeof vi.errors;

/** Đổi mã lỗi của backend (`detail.code`) thành câu tiếng Việt. */
export function errorMessage(code: string, detail?: Record<string, unknown>): string {
  if (code === "too_many_attempts") {
    const seconds = Number(detail?.retry_after ?? 60);
    return format(t.errors.too_many_attempts, { minutes: Math.max(1, Math.ceil(seconds / 60)) });
  }
  return code in t.errors ? t.errors[code as ErrorCode] : t.errors.unknown;
}
