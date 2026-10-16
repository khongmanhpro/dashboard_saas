import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

import { errorMessage, format } from "./index";
import { vi as dict } from "./vi";

const SRC = join(__dirname, "..");
// Ký tự có dấu riêng của tiếng Việt (ngoài bảng ASCII).
const VIETNAMESE = /[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]/i;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

function stripComments(code: string): string {
  return code.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1").replace(/\{\/\*[\s\S]*?\*\/\}/g, "");
}

describe("i18n", () => {
  it("không viết cứng chữ tiếng Việt ngoài src/i18n", () => {
    const offenders = sourceFiles(SRC)
      .filter((file) => !relative(SRC, file).startsWith("i18n"))
      .filter((file) => VIETNAMESE.test(stripComments(readFileSync(file, "utf8"))))
      .map((file) => relative(SRC, file));
    expect(offenders).toEqual([]);
  });

  it("có câu cho mọi mã lỗi xác thực mà backend trả về", () => {
    const backendCodes = [
      "invalid_credentials", "too_many_attempts", "wrong_current_password", "password_too_short",
      "password_too_long", "password_same_as_email", "password_too_common", "password_unchanged",
      "password_change_required", "not_authenticated", "csrf_failed", "origin_not_allowed", "forbidden",
    ];
    for (const code of backendCodes) expect(Object.keys(dict.errors)).toContain(code);
  });

  it("mã lạ thì dùng câu chung", () => {
    expect(errorMessage("ma_chua_biet")).toBe(dict.errors.unknown);
  });

  it("đổi số giây chờ thành phút", () => {
    expect(errorMessage("too_many_attempts", { retry_after: 125 })).toContain("3 phút");
  });

  it("format điền tham số", () => {
    expect(format("Bước {step}", { step: 4 })).toBe("Bước 4");
    expect(format("{x} giữ nguyên")).toBe("{x} giữ nguyên");
  });
});
