import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { resolve } from "node:path";

import type { E2EAccount, E2ERole } from "./accounts";

const ROOT = resolve(import.meta.dirname, "..", "..");
// Cùng DB / Redis với stack e2e trong docker-compose.yml (profile e2e) và Makefile: không đụng DB dev.
const E2E_DB_ENV = [
  "-e", "POSTGRES_DB=fanpage_e2e_test",
  "-e", "POSTGRES_APP_USER=fanpage_app_e2e",
  "-e", "REDIS_URL=redis://redis:6379/13",
];
const ROLES: Array<[E2ERole, string, string, boolean]> = [
  ["owner", "owner", "[Chủ sở hữu E2E]", false],
  ["manager", "manager", "[Quản lý E2E]", false],
  ["team_lead", "team_lead", "[Trưởng nhóm E2E]", false],
  ["staff", "staff", "[Nhân viên E2E]", false],
  ["viewer", "viewer", "[Chỉ xem E2E]", false],
  ["first_login", "staff", "[Nhân viên mới E2E]", true],
];

/**
 * Tạo (hoặc đặt lại) tài khoản test qua CLI backend. Mật khẩu sinh mới mỗi lần chạy,
 * gửi qua stdin, không xuất hiện trên dòng lệnh hay trong file.
 */
export default function globalSetup(): void {
  const accounts = {} as Record<E2ERole, E2EAccount>;
  // Mỗi lần chạy một mã riêng: khách e2e luôn mới, không phụ thuộc lần chạy trước.
  const run = randomBytes(3).toString("hex");
  const payload = {
    workspace: "E2E Playwright",
    accounts: ROLES.map(([key, role, fullName, mustChange]) => {
      const password = `E2e-${randomBytes(12).toString("base64url")}`;
      const email = `e2e-${key.replace("_", "-")}@example.com`;
      accounts[key] = { email, password };
      return { email, full_name: fullName, role, password, must_change_password: mustChange };
    }),
    // Khách giả trên 2 Trang E2E: Trang 1 của nhân viên, Trang 2 của trưởng nhóm (quyết định #14).
    leads: [
      lead("flow", "e2e-staff@example.com", "100000000000901", "[Trang E2E 1]", run, "0900 000 911"),
      lead("viewer", "e2e-staff@example.com", "100000000000901", "[Trang E2E 1]", run, "0900 000 922"),
      lead("other", "e2e-team-lead@example.com", "100000000000902", "[Trang E2E 2]", run, "0900 000 933"),
      // Khách cho ứng dụng điện thoại (Bước 5).
      lead("mobile_call", "e2e-staff@example.com", "100000000000901", "[Trang E2E 1]", run, "0900 000 966"),
      lead("mobile_later", "e2e-staff@example.com", "100000000000901", "[Trang E2E 1]", run, "0900 000 977"),
      // Đủ 10 khách trong tuần để nhân viên và trưởng nhóm có điểm (Bước 4).
      { ...lead("score_staff", "e2e-staff@example.com", "100000000000901", "[Trang E2E 1]", run, "0900 000 944"), count: 10, reply_seconds: 120 },
      { ...lead("score_lead", "e2e-team-lead@example.com", "100000000000902", "[Trang E2E 2]", run, "0900 000 955"), count: 10, reply_seconds: 3600 },
      // Khách bấm quảng cáo "[E2E - Tin nhắn]" (Bước 7).
      { ...lead("ad_lead", "e2e-staff@example.com", "100000000000901", "[Trang E2E 1]", run, "0900 000 988"), count: 3, reply_seconds: 300, ad_id: "23800000000000901" },
    ],
    // BM giả có tài khoản quảng cáo; e2e-seed đồng bộ chi tiêu ngay (client Graph giả).
    ads_token: "MOCK-BM-E2E-ADS",
  };
  const output = execFileSync(
    "docker",
    ["compose", "run", "--rm", "-T", ...E2E_DB_ENV, "migrate", "python", "-m", "app.cli", "e2e-seed"],
    { cwd: ROOT, input: JSON.stringify(payload), stdio: ["pipe", "pipe", "inherit"], encoding: "utf8" },
  );
  const lastLine = output.trim().split("\n").at(-1) ?? "{}";
  const leads = (JSON.parse(lastLine) as { leads: Record<string, string> }).leads;
  process.env.E2E_ACCOUNTS = JSON.stringify(accounts);
  process.env.E2E_LEADS = JSON.stringify({ run, ids: leads });
}

function lead(key: string, owner: string, fbPageId: string, page: string, run: string, phone: string) {
  return {
    key,
    owner,
    fb_page_id: fbPageId,
    page,
    psid: `e2e-${run}-${key}`,
    name: `[Khách E2E ${run} ${key}]`,
    text: `[Tin nhắn E2E] số em ${phone}`,
  };
}
